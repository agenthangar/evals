"""End-to-end pipeline tests using the fixture repo and the script harness
(no product CLIs, no docker - tasks use runner: local)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bench import config as config_mod
from bench import grade, report, runner, smoke
from bench.task import Task
from bench.harness.base import HarnessResult

GOOD_PATCH = """\
diff --git a/calc.py b/calc.py
index 0000000..0000000 100644
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b  # BUG: should be addition
+    return a + b
"""

CHEATING_PATCH = """\
diff --git a/tests/test_calc.py b/tests/test_calc.py
new file mode 100644
--- /dev/null
+++ b/tests/test_calc.py
@@ -0,0 +1,2 @@
+def test_add():
+    assert True
"""


def write_config(path: Path, good_patch: Path) -> Path:
    cfg = {
        "incumbent": "good-agent",
        "configs": [
            {
                "id": "good-agent",
                "harness": "script",
                "patch_file": str(good_patch),
                "cost": {"mode": "flat_per_run", "flat_usd": 1.00},
            },
            {
                "id": "lazy-agent",
                "harness": "script",
                "cost": {"mode": "flat_per_run", "flat_usd": 0.10},
            },
        ],
    }
    path.write_text(yaml.safe_dump(cfg))
    return path


def test_grade_solution_passes(task_dir):
    task = Task.load(task_dir)
    result = grade.grade_diff(task, task.solution_patch)
    assert result.passed, result.output


def test_grade_empty_fails(task_dir):
    task = Task.load(task_dir)
    result = grade.grade_diff(task, "")
    assert not result.passed
    assert result.reason == "tests_failed"


def test_grade_garbage_patch(task_dir):
    task = Task.load(task_dir)
    result = grade.grade_diff(task, "not a real patch\n")
    assert not result.passed
    assert result.reason == "patch_apply_failed"


def test_agent_cannot_pass_by_rewriting_tests(task_dir):
    """Edits to held-out test paths are reverted before grading."""
    task = Task.load(task_dir)
    result = grade.grade_diff(task, CHEATING_PATCH)
    assert not result.passed


def test_smoke_gate(task_dir):
    task = Task.load(task_dir)
    result = smoke.smoke_task(task)
    assert result.ok, result.detail


def test_smoke_gate_catches_undetectable_task(task_dir):
    """A task whose tests pass on the base commit must fail the gate."""
    (task_dir / "tests.patch").write_text(CHEATING_PATCH)
    task = Task.load(task_dir)
    result = smoke.smoke_task(task)
    assert not result.ok
    assert result.solution_passed
    assert not result.empty_failed


def test_run_matrix_and_report(task_dir, tmp_path):
    task = Task.load(task_dir)
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    bench_config = config_mod.load(write_config(tmp_path / "configs.yaml", good_patch))
    snapshot_dir = tmp_path / "runs" / "test-snap"

    logs = []
    results = runner.run_matrix(
        [task], bench_config, snapshot_dir, trials=2, log=logs.append
    )
    assert len(results) == 4  # 1 task x 2 configs x 2 trials
    by_config = {}
    for r in results:
        by_config.setdefault(r.config_id, []).append(r.passed)
    assert all(by_config["good-agent"])
    assert not any(by_config["lazy-agent"])
    assert all(r.agent_exit_code == 0 for r in results)
    assert all(r.artifact_passed == r.passed for r in results)

    # Artifacts persisted per trial
    trial_dir = snapshot_dir / "fix-add" / "good-agent" / "trial-1"
    assert (trial_dir / "result.json").exists()
    assert "return a + b" in (trial_dir / "diff.patch").read_text()
    assert (trial_dir / "tests.log").exists()

    # Re-running resumes from cache instead of re-executing
    rerun = runner.run_matrix([task], bench_config, snapshot_dir, trials=2, log=logs.append)
    assert len(rerun) == 4
    assert any("cached" in line for line in logs)

    # Reporting
    loaded = runner.load_results(snapshot_dir)
    assert len(loaded) == 4
    aggregated = report.aggregate(loaded, bench_config)
    assert aggregated[report.ALL]["good-agent"].rate.point == 1.0
    assert aggregated[report.ALL]["lazy-agent"].rate.point == 0.0

    policy = report.routing_policy(aggregated, bench_config)
    assert policy["bugfix"]["use"] == "good-agent"  # lazy is cheap but clearly failing

    markdown = report.render_markdown(aggregated, policy, bench_config, "test-snap")
    assert "good-agent" in markdown and "Routing policy" in markdown
    yaml_out = report.render_routing_yaml(policy, "test-snap")
    assert yaml.safe_load(yaml_out)["routing"]["bugfix"]["use"] == "good-agent"


def test_repeated_single_task_does_not_establish_equivalence(task_dir, tmp_path):
    """Repeated successes on one task cannot establish general equivalence."""
    task = Task.load(task_dir)
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    cfg = {
        "incumbent": "expensive",
        "configs": [
            {
                "id": "expensive",
                "harness": "script",
                "patch_file": str(good_patch),
                "cost": {"mode": "flat_per_run", "flat_usd": 2.00},
            },
            {
                "id": "cheap",
                "harness": "script",
                "patch_file": str(good_patch),
                "cost": {"mode": "flat_per_run", "flat_usd": 0.05},
            },
        ],
    }
    cfg_path = tmp_path / "configs.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))
    bench_config = config_mod.load(cfg_path)
    snapshot_dir = tmp_path / "runs" / "snap2"

    results = runner.run_matrix(
        [task], bench_config, snapshot_dir, trials=6, log=lambda *_: None
    )
    aggregated = report.aggregate(results, bench_config)
    policy = report.routing_policy(aggregated, bench_config)
    assert policy["bugfix"]["use"] == "expensive"


def test_run_matrix_rejects_unknown_selections(task_dir, tmp_path):
    task = Task.load(task_dir)
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    bench_config = config_mod.load(write_config(tmp_path / "configs.yaml", good_patch))

    with pytest.raises(runner.RunError, match="unknown config"):
        runner.run_matrix(
            [task],
            bench_config,
            tmp_path / "runs-config",
            config_ids=["does-not-exist"],
        )
    with pytest.raises(runner.RunError, match="unknown task"):
        runner.run_matrix(
            [task],
            bench_config,
            tmp_path / "runs-task",
            task_ids=["does-not-exist"],
        )


@pytest.mark.parametrize("exit_code,timed_out,reason", [
    (1, False, "agent_exited_nonzero"),
    (-9, True, "agent_timed_out"),
    (0, True, "agent_timed_out"),
])
def test_interrupted_agent_with_passing_patch_is_not_a_completed_pass(
    task_dir, tmp_path, monkeypatch, exit_code, timed_out, reason
):
    """A real passing artifact remains diagnostic when its agent did not finish."""
    from bench import workspace

    task = Task.load(task_dir)
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    config = config_mod.load(write_config(tmp_path / "configs.yaml", good_patch))

    class Interrupted:
        def run(self, product, workdir, prompt, timeout):
            workspace.apply_patch(workdir, GOOD_PATCH)
            return HarnessResult(exit_code, "synthetic interrupted execution", "", 1.0, timed_out)

    monkeypatch.setattr(runner.harness, "get", lambda _: Interrupted())
    output = tmp_path / "snapshot" / task.id / "good-agent" / "trial-1"
    result = runner.run_trial(task, config.by_id("good-agent"), 1, output)
    assert not result.passed
    assert result.grade_reason == reason
    assert result.agent_exit_code == exit_code
    assert result.artifact_passed is True
    assert result.artifact_grade_reason == "tests_passed"
    assert all(check["passed"] for check in result.check_results)
    loaded = runner.load_results(tmp_path / "snapshot")
    assert loaded == [result]
    aggregated = report.aggregate(loaded, config)
    assert aggregated[report.ALL]["good-agent"].rate.successes == 0
    assert aggregated[report.ALL]["good-agent"].interrupted_attempts == 1
    policy = report.routing_policy(aggregated, config)
    assert policy["bugfix"]["candidates"][0]["interrupted_attempts"] == 1
    markdown = report.render_markdown(aggregated, policy, config, "snapshot", loaded)
    assert reason in markdown
    assert "| `good-agent` | 1 | 0 |" in markdown


def test_legacy_execution_outcomes_stay_unknown(tmp_path):
    result = runner.TrialResult("task", "bugfix", "good-agent", 1, True,
                                "tests_passed", 1.0, 2.0, False, 10)
    data = result.to_dict()
    for field in ["agent_exit_code", "artifact_passed", "artifact_grade_reason"]:
        del data[field]
    restored = runner.TrialResult(**data)
    assert restored.passed and restored.agent_exit_code is None
    good_patch = tmp_path / "good.patch"
    good_patch.write_text(GOOD_PATCH)
    config = config_mod.load(write_config(tmp_path / "configs.yaml", good_patch))
    stats = report.aggregate([restored], config)[report.ALL]["good-agent"]
    assert stats.execution_unknown_attempts == 1
    assert stats.interrupted_attempts == 0
