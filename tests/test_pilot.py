import dataclasses
import json

import pytest

from bench import config, pilot, runner
from bench.cli import main
from bench.task import Task
from tests.test_pipeline_e2e import GOOD_PATCH, write_config


def snapshot(tmp_path, outcomes):
    root = tmp_path / 'pilot'
    root.mkdir()
    manifest = {'tasks': [{'id': 'work'}], 'configs': [{'id': 'a'}, {'id': 'b'}], 'trials': 1}
    (root / 'manifest.json').write_text(json.dumps(manifest))
    for name, overrides in zip(('a', 'b'), outcomes):
        result = runner.TrialResult('work', 'bugfix', name, 1, True, 'tests_passed', 1, 1, False, 20,
                                    agent_exit_code=0, artifact_passed=True, artifact_grade_reason='tests_passed')
        data = dataclasses.asdict(result)
        data.update(overrides)
        path = root / 'work' / name / 'trial-1'
        path.mkdir(parents=True)
        (path / 'result.json').write_text(json.dumps(data))
    return root


def test_saturated_pilot_stops_optional_signal_gate(tmp_path, capsys):
    root = snapshot(tmp_path, [{}, {}])
    result = pilot.review(root)
    assert result['tasks'][0]['status'] == 'saturated'
    assert not result['observed_between_config_signal']
    assert len(result['result_sha256']) == 2
    assert main(['--runs', str(tmp_path), 'pilot-review', '--snapshot', 'pilot', '--require-signal', '--json']) == 2
    assert json.loads(capsys.readouterr().out)['attempt_count'] == 2


@pytest.mark.parametrize('overrides', [
    {'agent_exit_code': None}, {'agent_exit_code': 1}, {'agent_timed_out': True},
    {'passed': False, 'artifact_passed': False, 'grade_reason': 'environment_error'},
    {'passed': False, 'artifact_passed': False, 'grade_reason': 'patch_apply_failed'},
])
def test_unresolved_execution_or_grading_is_not_difficulty(tmp_path, overrides):
    result = pilot.review(snapshot(tmp_path, [{}, overrides]))
    assert result['tasks'][0]['status'] == 'needs_execution_or_grader_review'
    assert not result['observed_between_config_signal']


def test_universal_failure_requires_contract_review(tmp_path):
    failure = {'passed': False, 'artifact_passed': False, 'grade_reason': 'tests_failed'}
    result = pilot.review(snapshot(tmp_path, [failure, failure]))
    assert result['tasks'][0]['status'] == 'all_failed_review_contract_and_environment'
    assert not result['observed_between_config_signal']


def test_pilot_requires_complete_matched_manifest_and_correct_paths(tmp_path):
    root = snapshot(tmp_path, [{}, {}])
    file = root / 'work/b/trial-1/result.json'
    saved = file.read_text()
    file.unlink()
    with pytest.raises(runner.RunError, match='incomplete'):
        pilot.review(root)
    file.write_text(saved)
    wrong = root / 'wrong/b/trial-1'
    wrong.mkdir(parents=True)
    file.rename(wrong / 'result.json')
    with pytest.raises(runner.RunError, match='outside'):
        pilot.review(root)
    (root / 'manifest.json').unlink()
    with pytest.raises(runner.RunError, match='frozen manifest'):
        pilot.review(root)


def test_real_script_harness_pilot_finds_observed_grade_variation(task_dir, tmp_path):
    patch = tmp_path / 'good.patch'
    patch.write_text(GOOD_PATCH)
    settings = config.load(write_config(tmp_path / 'config.yaml', patch))
    root = tmp_path / 'real-pilot'
    runner.run_matrix([Task.load(task_dir)], settings, root, trials=1, log=lambda _: None)
    result = pilot.review(root)
    assert result['observed_between_config_signal']
    assert result['tasks'][0]['status'] == 'observed_separation'
    assert result['tasks'][0]['configs']['good-agent'] == {'passed': 1}
    assert result['tasks'][0]['configs']['lazy-agent'] == {'completed_check_failure': 1}


def test_equal_mixed_repetitions_are_not_between_config_separation(tmp_path):
    root = snapshot(tmp_path, [{}, {}])
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['trials'] = 2
    manifest_path.write_text(json.dumps(manifest))
    for name in ('a', 'b'):
        data = json.loads((root / 'work' / name / 'trial-1/result.json').read_text())
        data.update(trial=2, passed=False, artifact_passed=False, grade_reason='tests_failed')
        path = root / 'work' / name / 'trial-2'
        path.mkdir()
        (path / 'result.json').write_text(json.dumps(data))
    result = pilot.review(root)
    assert result['attempt_count'] == 4
    assert result['tasks'][0]['status'] == 'within_config_variation_only'
    assert not result['observed_between_config_signal']
