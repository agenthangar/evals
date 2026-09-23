"""Behavioral tests for grader calibration, answer leakage and honest reporting."""
import dataclasses
import json
from pathlib import Path
import pytest
import yaml
from bench import grade, quality, report, runner, smoke, workspace
from bench.config import BenchConfig, ProductConfig, CostModel
from bench.stats import INCONCLUSIVE, INSUFFICIENT_DATA
from bench.task import Task, TaskError
from tests.conftest import git


def contract(task_dir):
    meta = yaml.safe_load((task_dir / 'task.yaml').read_text())
    meta['evaluation'] = {
        'criteria': [{'id': 'sum', 'description': 'Adds arbitrary inputs', 'check': 'tests'}],
        'negative_controls': [{'id': 'subtract', 'patch_file': 'wrong.patch',
                               'reason': 'Still subtracts inputs', 'fails': ['tests']}],
        'limitations': ['Arithmetic only, not a representative workload.'],
    }
    meta['provenance'] = {'source': 'synthetic fixture', 'why_this_task': 'Exercise calibration.'}
    wrong = (task_dir / 'solution.patch').read_text().replace('+    return a + b', '+    return a - b')
    (task_dir / 'wrong.patch').write_text(wrong)
    (task_dir / 'task.yaml').write_text(yaml.safe_dump(meta))
    return Task.load(task_dir)


def test_calibration_rejects_wrong_solution_and_accepts_reference(task_dir):
    task = contract(task_dir)
    assert quality.audit(task) == []
    result = smoke.smoke_task(task, repeats=2)
    assert result.ok, result.detail
    assert len(result.controls) == 2 and all(c['detected'] for c in result.controls)


def test_passing_negative_control_blocks_smoke(task_dir):
    task = contract(task_dir)
    task.negative_controls[0].patch = task.solution_patch
    result = smoke.smoke_task(task)
    assert not result.ok and 'subtract' in result.detail


def test_invalid_control_patch_is_not_evidence_of_detection(task_dir):
    task = contract(task_dir)
    task.negative_controls[0].patch = 'invalid diff'
    result = smoke.smoke_task(task)
    assert not result.ok and result.controls[0]['reason'] == 'patch_apply_failed'


def test_timeout_does_not_calibrate_a_grader(task_dir, monkeypatch):
    task = Task.load(task_dir)
    monkeypatch.setattr(grade, 'grade_diff', lambda t, p: grade.GradeResult(bool(p), 'tests_passed' if p else 'test_timeout', None, ''))
    assert not smoke.smoke_task(task).ok


def test_named_checks_all_run_and_preserve_evidence(task_dir):
    task = contract(task_dir)
    from bench.task import Check
    task.checks = [Check('bad', 'exit 1'), Check('good', 'echo observed')]
    result = grade.grade_diff(task, task.solution_patch)
    assert not result.passed
    assert [(c['id'],c['passed']) for c in result.checks] == [('bad',False),('good',True)]
    assert 'observed' in result.output


@pytest.mark.parametrize('mutation', [
    lambda m: m.update(repo=[]),
    lambda m: m['tests'].update(timeout_seconds=-1),
    lambda m: m['tests'].update(patch_file='../outside.patch'),
    lambda m: m['repo'].update(base_commit='main'),
    lambda m: m.update(evaluation={'criteria': [{'id': 'x', 'description': 'behavior', 'check': 'missing'}]}),
])
def test_bad_contracts_fail_cleanly(task_dir, mutation):
    meta = yaml.safe_load((task_dir/'task.yaml').read_text());mutation(meta)
    (task_dir/'task.yaml').write_text(yaml.safe_dump(meta))
    with pytest.raises(TaskError): Task.load(task_dir)


def test_agent_sees_no_fix_history_or_remote(fixture_repo, tmp_path):
    workdir, base = workspace.agent_checkout(str(fixture_repo['repo']), fixture_repo['base'], tmp_path/'agent')
    assert git(workdir,'rev-list','--count','--all') == '1'
    assert git(workdir,'remote','-v') == ''
    assert 'a - b' in (workdir/'calc.py').read_text()
    with pytest.raises(Exception): git(workdir,'show',fixture_repo['fix'])
    assert not workspace.capture_diff(workdir,base)


def test_changed_contract_cannot_reuse_snapshot(task_dir, tmp_path):
    task=Task.load(task_dir)
    config=BenchConfig('noop',[ProductConfig('noop','script')])
    root=tmp_path/'snapshot'
    runner.run_matrix([task],config,root,trials=1,log=lambda *_:None)
    task.prompt+=' Another requirement.'
    with pytest.raises(runner.RunError,match='inputs changed'):
        runner.run_matrix([task],config,root,trials=1,log=lambda *_:None)


def test_grading_uses_fresh_checkout(task_dir,tmp_path,monkeypatch):
    task=Task.load(task_dir)
    seen=[]
    real=grade.grade_diff
    def fresh(t,diff):
        seen.append(diff)
        return real(t,diff)
    monkeypatch.setattr(grade,'grade_diff',fresh)
    runner.run_trial(task,ProductConfig('noop','script'),1,tmp_path/'out')
    assert seen == ['']


def results(n=100, missing=False, partial=False):
    out=[]
    for i in range(n):
        for name,cost in [('baseline',2.0),('cheap',0.2)]:
            if partial and name=='cheap' and i==0:continue
            out.append(runner.TrialResult(str(i),'bugfix',name,1,True,'tests_passed',None if missing and name=='cheap' and i==0 else cost,1,False,10,agent_exit_code=0))
    return out


def test_equivalent_distinct_tasks_can_route_to_cheaper_model():
    cfg=BenchConfig('baseline',[ProductConfig('baseline','script'),ProductConfig('cheap','script')])
    aggregated=report.aggregate(results(),cfg)
    assert report.routing_policy(aggregated,cfg)['bugfix']['use']=='cheap'


def test_missing_cost_is_not_free_and_partial_coverage_is_not_equivalence():
    cfg=BenchConfig('baseline',[ProductConfig('baseline','script'),ProductConfig('cheap','script')])
    aggregated=report.aggregate(results(missing=True),cfg)
    assert aggregated['bugfix']['cheap'].total_cost_usd is None
    assert report.routing_policy(aggregated,cfg)['bugfix']['use']=='baseline'
    partial=report.aggregate(results(partial=True),cfg)
    assert partial['bugfix']['cheap'].comparison.bucket==INSUFFICIENT_DATA


def test_legacy_unknown_execution_cannot_establish_a_routing_comparison():
    cfg=BenchConfig('baseline',[ProductConfig('baseline','script'),ProductConfig('cheap','script')])
    attempts=results()
    attempts[0].agent_exit_code=None
    aggregated=report.aggregate(attempts,cfg)
    assert aggregated['bugfix']['baseline'].rate.successes==100
    assert aggregated['bugfix']['cheap'].comparison.bucket==INSUFFICIENT_DATA
    assert report.routing_policy(aggregated,cfg)['bugfix']['use']=='baseline'


def test_public_quality_tasks_calibrate():
    from bench.task import load_all
    tasks=load_all(Path(__file__).parents[1]/'examples/quality-tasks')
    assert len(tasks)==2
    for task in tasks:
        assert quality.audit(task)==[]
        result=smoke.smoke_task(task)
        assert result.ok,result.detail


def test_incomplete_matrix_and_changed_report_config_are_rejected(task_dir,tmp_path):
    task=Task.load(task_dir)
    cfg=BenchConfig('noop',[ProductConfig('noop','script')])
    root=tmp_path/'snapshot'
    runner.run_matrix([task],cfg,root,trials=1,log=lambda *_:None)
    runner.verify_report_config(root,cfg)
    cfg.configs[0].model='different-model'
    with pytest.raises(runner.RunError,match='configuration differs'):
        runner.verify_report_config(root,cfg)
    (root/task.id/'noop'/'trial-1'/'result.json').unlink()
    with pytest.raises(runner.RunError,match='incomplete'):
        runner.load_results(root)
