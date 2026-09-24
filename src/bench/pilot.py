"""Inspect a small frozen matrix before spending on more repetitions of the same tasks."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from bench import runner


def _outcome(result: runner.TrialResult) -> str:
    if result.agent_exit_code is None:
        return 'execution_unknown'
    if result.agent_timed_out:
        return 'agent_timeout'
    if result.agent_exit_code != 0:
        return 'agent_error'
    if result.passed and result.artifact_passed is not False:
        return 'passed'
    if not result.passed and result.artifact_passed is not True and result.grade_reason == 'tests_failed':
        return 'completed_check_failure'
    return 'grade_needs_review'


def review(snapshot: Path) -> dict:
    snapshot = Path(snapshot)
    manifest_file = snapshot / 'manifest.json'
    if not manifest_file.is_file():
        raise runner.RunError('pilot review requires a frozen manifest and complete matched matrix')
    try:
        manifest = json.loads(manifest_file.read_text())
        results = runner.load_results(snapshot)
        configs = [c['id'] for c in manifest['configs']]
        task_ids = [t['id'] for t in manifest['tasks']]
        if (not results or len(configs) < 2 or len(configs) != len(set(configs))
                or not task_ids or len(task_ids) != len(set(task_ids))
                or not isinstance(manifest['trials'], int) or isinstance(manifest['trials'], bool)
                or manifest['trials'] < 1):
            raise ValueError('at least two distinct configs and a nonempty matched matrix are required')
    except (KeyError, TypeError, ValueError) as exc:
        raise runner.RunError(f'invalid pilot snapshot: {exc}') from exc
    artifacts = {}
    for path in snapshot.glob('*/*/trial-*/result.json'):
        data = json.loads(path.read_text())
        expected = snapshot / data['task_id'] / data['config_id'] / f"trial-{data['trial']}" / 'result.json'
        if path != expected:
            raise runner.RunError(f'result is stored outside its declared matrix cell: {path}')
        artifacts[str(path.relative_to(snapshot))] = hashlib.sha256(path.read_bytes()).hexdigest()
    tasks = []
    for task_id in task_ids:
        rows = [r for r in results if r.task_id == task_id]
        by_config = {c: Counter(_outcome(r) for r in rows if r.config_id == c) for c in configs}
        outcomes = Counter(_outcome(r) for r in rows)
        if set(outcomes) - {'passed', 'completed_check_failure'}:
            status = 'needs_execution_or_grader_review'
        elif outcomes['passed'] == len(rows):
            status = 'saturated'
        elif outcomes['completed_check_failure'] == len(rows):
            status = 'all_failed_review_contract_and_environment'
        elif len({x['passed'] for x in by_config.values()}) > 1:
            status = 'observed_separation'
        else:
            status = 'within_config_variation_only'
        tasks.append({'task_id': task_id, 'status': status,
                      'outcomes': dict(outcomes), 'configs': {c: dict(x) for c, x in by_config.items()}})
    counts = Counter(t['status'] for t in tasks)
    signal = bool(counts['observed_separation']) and not counts['needs_execution_or_grader_review']
    if counts['needs_execution_or_grader_review']:
        next_step = 'Review execution, artifact and grader evidence before interpreting difficulty.'
    elif counts['saturated'] == len(tasks):
        next_step = 'Audit grader escape cases and capture independent incidents; more repetitions of these tasks do not address the ceiling.'
    elif counts['all_failed_review_contract_and_environment'] == len(tasks):
        next_step = 'Check reference validity, environment, scope and budgets before treating universal failure as hardness.'
    else:
        next_step = 'Review each failed check and extraction loss, then freeze fresh incident holdouts before a final comparison.'
    return {'schema': 1, 'snapshot': str(snapshot),
            'manifest_sha256': hashlib.sha256(manifest_file.read_bytes()).hexdigest(),
            'result_sha256': artifacts, 'task_count': len(tasks), 'attempt_count': len(results),
            'observed_between_config_signal': signal, 'tasks': tasks, 'next_step': next_step,
            'limitations': ['This is a pilot diagnostic, not a quality ranking, significance test or automatic admission approval.',
                            'A completed failed check may expose a bad grader or environment; inspect its evidence.',
                            'Passing selected negative controls does not establish grader completeness. Audit realistic escaped mistakes.',
                            'Keep routine tasks and all discovery exclusions visible; do not claim workload-wide performance from a challenge-only set.',
                            'Use independent incident families for holdout; repeated trials and follow-up commits are not independent work samples.']}
