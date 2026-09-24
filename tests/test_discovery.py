import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from bench.cli import main
from bench.mine import incidents, struggles
from bench.mine.git_history import MineError
from tests.conftest import git


def commit(repo, files, message):
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', message)
    return git(repo, 'rev-parse', 'HEAD')


def test_incidents_keep_broad_untested_work_and_precise_links(fixture_repo):
    repo = fixture_repo['repo']
    first = commit(repo, {f'src/module_{i}.py': 'broken\n' for i in range(25)}, 'Add worker scheduling')
    second = commit(repo, {'src/module_0.py': 'fixed\n'}, 'Fix worker restart race')
    inventory = incidents.discover(repo)
    lead = next(c for c in inventory['candidates'] if c['latest_revision_candidate'] == second)
    assert [c['sha'] for c in lead['commits']] == [first, second]
    assert len(lead['commits'][0]['source_files']) == 25
    assert all(not c['test_files'] for c in lead['commits'])
    assert lead['links'][0]['shared_source_paths'] == ['src/module_0.py']
    assert lead['starting_revision_candidate'] == fixture_repo['fix']
    assert lead['difficulty'] == 'unmeasured'
    assert lead['admission'] == 'discovery_only'
    assert inventory['commits_scanned'] == 4
    assert {c['sha'] for c in inventory['unlinked_commits']} == {fixture_repo['base'], fixture_repo['fix']}


def test_docs_lockfiles_and_unrelated_fixes_do_not_link(fixture_repo):
    repo = fixture_repo['repo']
    commit(repo, {'docs/note.md': 'one', 'package-lock.json': '{}', 'one.py': 'one'}, 'Add first feature')
    commit(repo, {'docs/note.md': 'two', 'package-lock.json': '[]', 'two.py': 'two'}, 'Fix second feature')
    assert not incidents.discover(repo)['candidates']


def test_scan_boundaries_and_worktree_are_preserved(fixture_repo):
    repo = fixture_repo['repo']
    commit(repo, {'calc.py': 'bad\n'}, 'Improve addition')
    commit(repo, {'calc.py': 'good\n'}, 'Repair addition')
    (repo / 'calc.py').write_text('UNCOMMITTED\n')
    before = git(repo, 'status', '--porcelain')
    assert not incidents.discover(repo, limit=1)['candidates']
    assert not incidents.discover(repo, since='2099-01-01')['candidates']
    assert incidents.discover(repo)['candidates']
    assert git(repo, 'status', '--porcelain') == before
    assert (repo / 'calc.py').read_text() == 'UNCOMMITTED\n'
    with pytest.raises(MineError, match='positive'):
        incidents.discover(repo, window_days=0)


def test_transitive_links_do_not_create_unbounded_episodes(fixture_repo):
    repo = fixture_repo['repo']
    for day in (1, 8, 15, 22, 29):
        (repo / 'worker.py').write_text(str(day))
        git(repo, 'add', 'worker.py')
        stamp = f'2026-01-{day:02d}T12:00:00+00:00'
        subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'Fix worker retry'], check=True,
                       env={**os.environ, 'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp})
    result = incidents.discover(repo, window_days=14)
    for candidate in result['candidates']:
        times = [datetime.fromisoformat(c['timestamp'].replace('Z', '+00:00')) for c in candidate['commits']]
        assert (max(times) - min(times)).days <= 14
    assert result['cross_episode_links']
    assert sum(len(c['commits']) for c in result['candidates']) + len(result['unlinked_commits']) == result['commits_scanned']


def session_file(directory, name='session.jsonl', cwd='/code/sample', origin='Codex Desktop', timestamp='2026-01-01T00:00:00Z'):
    records = [{'type': 'session_meta', 'payload': {'id': name, 'cwd': cwd, 'originator': origin, 'timestamp': timestamp}}]
    for role, text in [('user', 'Fix the PRIVATE_FIXTURE_VALUE worker.'), ('assistant', 'PRIVATE_ASSISTANT_TEXT'),
                       ('user', 'Still not working'), ('user', 'Still not working'),
                       ('assistant', 'Done'), ('user', 'No regressions now'),
                       ('user', '<system-reminder>Still broken</system-reminder>')]:
        records.append({'type': 'response_item', 'payload': {'type': 'message', 'role': role,
                       'content': [{'type': 'input_text' if role == 'user' else 'output_text', 'text': text}]}})
    path = directory / name
    path.write_text('\n'.join(json.dumps(r) for r in records) + '\n')
    return path


def test_struggles_use_user_evidence_without_exporting_text(tmp_path):
    session_file(tmp_path)
    result = struggles.discover(tmp_path)
    assert len(result['candidates']) == 1
    candidate = result['candidates'][0]
    assert len(candidate['evidence']) == 1
    assert candidate['evidence'][0]['signals'] == ['reported_unresolved']
    assert candidate['evidence'][0]['message_index'] == 2
    assert 'PRIVATE_' not in json.dumps(result)
    assert candidate['difficulty'] == 'unmeasured'
    excerpts = struggles.discover(tmp_path, include_excerpts=True)
    assert 'PRIVATE_FIXTURE_VALUE' in json.dumps(excerpts)
    assert 'PRIVATE_ASSISTANT_TEXT' not in json.dumps(excerpts)


def test_struggles_exclude_benchmarks_automation_unknown_dates_and_other_repos(tmp_path):
    session_file(tmp_path, 'interactive.jsonl')
    session_file(tmp_path, 'benchmark.jsonl', cwd='/tmp/bench-run-fixture/repo')
    session_file(tmp_path, 'automatic.jsonl', origin='codex_exec')
    session_file(tmp_path, 'unknown-date.jsonl', timestamp=None)
    result = struggles.discover(tmp_path, since='2025-12-01', repo=Path('/code/sample'))
    assert len(result['candidates']) == 1
    assert result['counts']['excluded_benchmark'] == 1
    assert result['counts']['excluded_mode'] == 1
    assert result['counts']['excluded_unknown_date'] == 1
    assert len(struggles.discover(tmp_path, mode='all')['candidates']) == 3
    assert not struggles.discover(tmp_path, repo=Path('/code/unrelated'))['candidates']
    assert not struggles.discover(tmp_path, source='claude')['candidates']
    with pytest.raises(MineError, match='ISO date'):
        struggles.discover(tmp_path, since='yesterday')


def test_first_request_and_assistant_claims_alone_are_not_friction(tmp_path):
    (tmp_path / 'generic.jsonl').write_text('\n'.join(json.dumps(r) for r in [
        {'role': 'user', 'content': 'Still broken; fix this'},
        {'role': 'assistant', 'content': 'I tried five approaches. Still broken.'}]))
    assert not struggles.discover(tmp_path, mode='all')['candidates']


def test_regression_check_request_is_not_a_report_but_real_correction_survives(tmp_path):
    path = tmp_path / 'generic.jsonl'
    records = [{'role': 'user', 'content': 'Implement the feature'},
               {'role': 'assistant', 'content': 'Implemented.'},
               {'role': 'user', 'content': 'Run end-to-end tests and see nothing regressed.'}]
    path.write_text('\n'.join(json.dumps(r) for r in records))
    assert not struggles.discover(tmp_path, mode='all')['candidates']
    records.append({'role': 'user', 'content': 'The editor has regressed. It is still broken.'})
    path.write_text('\n'.join(json.dumps(r) for r in records))
    evidence = struggles.discover(tmp_path, mode='all')['candidates'][0]['evidence']
    assert len(evidence) == 1
    assert evidence[0]['signals'] == ['reported_unresolved', 'reported_regression']


def test_quoted_approval_history_is_not_a_new_user_correction(tmp_path):
    records = [{'role': 'user', 'content': 'Implement a feature'},
               {'role': 'assistant', 'content': 'Implemented.'},
               {'role': 'user', 'content': 'The following is the Codex agent history whose request action you are assessing.\n>>> TRANSCRIPT START\nUser: still broken, try again'}]
    (tmp_path / 'approval.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
    assert not struggles.discover(tmp_path, mode='all')['candidates']


def test_approval_wrapper_and_quoted_history_in_separate_blocks(tmp_path):
    def message(role, content):
        return {'type': 'response_item', 'payload': {'type': 'message', 'role': role, 'content': content}}
    records = [message('user', [{'type': 'input_text', 'text': 'Implement a feature'}]),
               message('assistant', [{'type': 'output_text', 'text': 'Implemented'}]),
               message('user', [
                   {'type': 'input_text', 'text': 'The following is the Codex agent history whose request action you are assessing.'},
                   {'type': 'input_text', 'text': '>>> TRANSCRIPT START\n[1] user: Still broken. Try again.'}])]
    (tmp_path / 'split-approval.jsonl').write_text('\n'.join(json.dumps(r) for r in records))
    assert not struggles.discover(tmp_path, mode='all')['candidates']


def test_discovery_cli_returns_private_evidence_inventory(fixture_repo, tmp_path, capsys):
    assert main(['mine', 'incidents', str(fixture_repo['repo']), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['privacy'] == 'local_private_inventory'
    session_file(tmp_path)
    assert main(['mine', 'struggles', str(tmp_path), '--json']) == 0
    assert len(json.loads(capsys.readouterr().out)['candidates']) == 1
    assert main(['mine', 'struggles', str(tmp_path / 'missing')]) == 1
    assert 'not found' in capsys.readouterr().err
