"""Read-only leads for multi-commit incidents, without claiming measured difficulty."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from bench import patches
from bench.mine.git_history import _git, MineError

REPAIR = re.compile(r"\b(fix(?:es|ed)?|repair|correct|regression|revert|restore|prevent|harden|stabili[sz]e)\b", re.I)
_NO_LINK_SUFFIXES = {'.md', '.rst', '.txt', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.mp4', '.lock'}
_NO_LINK_NAMES = {'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'Package.resolved', 'Podfile.lock'}


def _link_path(name: str) -> bool:
    path = Path(name)
    return (not patches.is_test_path(name) and path.name not in _NO_LINK_NAMES
            and path.suffix.lower() not in _NO_LINK_SUFFIXES)


def discover(repo: Path, limit: int = 200, lookback: int = 30,
             window_days: int = 14, since: str | None = None) -> dict:
    """Group nearby first-parent commits linked by a later repair on shared source.

    Shared paths and repair words are retrieval heuristics. They do not prove
    earlier work failed, that the commits solve one incident, or that it is hard.
    There is no source-file-count ceiling or test-presence admission filter.
    """
    if min(limit, lookback, window_days) < 1:
        raise MineError('limit, lookback and window_days must be positive')
    repo = Path(repo).expanduser().resolve()
    log = _git(repo, ['log', '--first-parent', '--no-merges', f'-{limit}',
                     '--format=%H%x00%P%x00%cI%x00%s',
                     *([f'--since={since}'] if since else [])])
    commits = []
    for line in reversed(log.splitlines()):
        sha, parents, timestamp, subject = line.split('\0', 3)
        names = _git(repo, ['diff-tree', '--root', '--no-commit-id', '--name-only', '-r', '-z', sha])
        files = [p for p in names.split('\0') if p]
        commits.append({'sha': sha, 'parent': parents.split()[0] if parents else None,
                        'timestamp': timestamp, 'subject': subject,
                        'source_files': [p for p in files if not patches.is_test_path(p)],
                        'test_files': [p for p in files if patches.is_test_path(p)],
                        'link_paths': sorted(p for p in files if _link_path(p))})
    parent = list(range(len(commits)))
    # Recent Git versions emit Z for UTC; Python 3.10 requires an explicit offset.
    times = [datetime.fromisoformat(c['timestamp'].replace('Z', '+00:00')) for c in commits]
    bounds = [(stamp, stamp, i, i) for i, stamp in enumerate(times)]

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    edges = []
    for later, current in enumerate(commits):
        trigger = REPAIR.search(current['subject'])
        if not trigger:
            continue
        for earlier in range(max(0, later - lookback), later):
            previous = commits[earlier]
            if previous['parent'] is None:
                continue  # Initial repository creation would link every later repair.
            gap = (times[later] - times[earlier]).total_seconds()
            if gap < 0 or gap > window_days * 86400:
                continue
            shared = sorted(set(current['link_paths']) & set(previous['link_paths']))
            if not shared:
                continue
            edges.append({'earlier': previous['sha'], 'later': current['sha'],
                          'shared_source_paths': shared, 'repair_word': trigger.group().lower(),
                          'elapsed_days': round(gap / 86400, 3)})
            left, right = root(earlier), root(later)
            if left == right:
                continue
            start, end = min(bounds[left][0], bounds[right][0]), max(bounds[left][1], bounds[right][1])
            first, last = min(bounds[left][2], bounds[right][2]), max(bounds[left][3], bounds[right][3])
            if (end - start).total_seconds() > window_days * 86400 or last - first > lookback:
                continue  # A chain of local links must not silently become a months-long incident.
            parent[right] = left
            bounds[left] = (start, end, first, last)
    groups = {}
    for i, commit in enumerate(commits):
        groups.setdefault(root(i), []).append(commit)
    candidates = []
    for group in groups.values():
        if len(group) < 2:
            continue
        shas = {c['sha'] for c in group}
        candidates.append({'id': f"incident-{group[0]['sha'][:12]}-{group[-1]['sha'][:12]}",
                           'starting_revision_candidate': group[0]['parent'],
                           'latest_revision_candidate': group[-1]['sha'],
                           'commits': group,
                           'links': [e for e in edges if e['earlier'] in shas and e['later'] in shas],
                           'review_required': ['confirm_one_incident_and_original_request',
                                               'verify_actual_failed_attempts_from_diffs_or_reports',
                                               'retain_original_context_and_record_extraction_losses',
                                               'review_grader_escape_cases_before_a_model_pilot'],
                           'difficulty': 'unmeasured', 'admission': 'discovery_only'})
    candidates.reverse()  # Recency, not a fabricated difficulty score.
    grouped_shas = {c['sha'] for group in groups.values() if len(group) > 1 for c in group}
    group_ids = {c['sha']: key for key, group in groups.items() for c in group}
    return {'schema': 1, 'repository': str(repo), 'privacy': 'local_private_inventory',
            'history': 'current HEAD first-parent non-merge commits',
            'parameters': {'limit': limit, 'lookback': lookback, 'window_days': window_days, 'since': since},
            'commits_scanned': len(commits), 'commits_without_tests': sum(not c['test_files'] for c in commits),
            'unlinked_commits': [c for c in commits if c['sha'] not in grouped_shas],
            'cross_episode_links': [e for e in edges if group_ids[e['earlier']] != group_ids[e['later']]],
            'candidates': candidates,
            'limitations': ['Linked repairs may be unrelated; manually inspect every proposed incident.',
                            'Merged side-branch detail, uncommitted attempts and history outside the scan window are not included.',
                            'Episode bounds can split a real incident. Review cross-episode links; missing repair words or renamed files can hide work.',
                            'Initial repository creation is not used to link every subsequent repair. Retain routine and manually nominated work too.',
                            'Commit count, elapsed time, file count and test presence do not measure model difficulty.']}
