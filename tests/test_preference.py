from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bench import config as config_mod
from bench import grade, preference, report, runner, smoke, workspace
from bench.task import Task


def answer_patch(text: str) -> str:
    lines = text.splitlines()
    added = "\n".join(f"+{line}" for line in lines)
    return (
        "diff --git a/answer.md b/answer.md\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/answer.md\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{added}\n"
    )


def preference_config(path: Path, first_patch: Path, second_patch: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "incumbent": "model-one",
                "configs": [
                    {
                        "id": "model-one",
                        "harness": "script",
                        "patch_file": str(first_patch),
                        "cost": {"mode": "flat_per_run", "flat_usd": 0.2},
                    },
                    {
                        "id": "model-two",
                        "harness": "script",
                        "patch_file": str(second_patch),
                        "cost": {"mode": "flat_per_run", "flat_usd": 0.1},
                    },
                ],
            }
        )
    )
    return path


def run_preference_fixture(preference_task_dir: Path, tmp_path: Path):
    first_patch = tmp_path / "first.patch"
    first_patch.write_text(answer_patch("A long generic answer.\nMore filler."))
    second_patch = tmp_path / "second.patch"
    second_patch.write_text(answer_patch("A concise, grounded answer."))
    config = config_mod.load(
        preference_config(tmp_path / "configs.yaml", first_patch, second_patch)
    )
    task = Task.load(preference_task_dir)
    snapshot_dir = tmp_path / "runs" / "preference-snap"
    results = runner.run_matrix(
        [task], config, snapshot_dir, trials=1, log=lambda *_: None
    )
    return task, config, snapshot_dir, results


def test_preference_artifact_capture_requires_nonempty_file(
    preference_task_dir, tmp_path
):
    task = Task.load(preference_task_dir)
    workdir = workspace.checkout(task.repo_url, task.base_commit, tmp_path / "checkout")

    missing = grade.capture_preference_artifact(task, workdir)
    assert not missing.passed
    assert missing.reason == "artifact_missing"

    (workdir / "answer.md").write_text("\n")
    empty = grade.capture_preference_artifact(task, workdir)
    assert not empty.passed
    assert empty.reason == "artifact_empty"

    (workdir / "answer.md").write_text("Grounded answer.\n")
    ready = grade.capture_preference_artifact(task, workdir)
    assert ready.passed
    assert ready.reason == "preference_ready"
    assert ready.output == "Grounded answer.\n"


def test_preference_artifact_cannot_escape_through_a_symlink(
    preference_task_dir, tmp_path
):
    task = Task.load(preference_task_dir)
    workdir = workspace.checkout(task.repo_url, task.base_commit, tmp_path / "checkout")
    private_file = tmp_path / "private.txt"
    private_file.write_text("do not capture me\n")
    (workdir / "answer.md").symlink_to(private_file)

    result = grade.capture_preference_artifact(task, workdir)

    assert not result.passed
    assert result.reason == "artifact_unsafe"
    assert "do not capture me" not in result.output


def test_preference_smoke_checks_that_base_has_no_answer(preference_task_dir):
    result = smoke.smoke_task(Task.load(preference_task_dir))

    assert result.ok
    assert "manual pairwise review" in result.detail


def test_runner_captures_preference_artifacts_without_binary_grading(
    preference_task_dir, tmp_path
):
    _, _, snapshot_dir, results = run_preference_fixture(preference_task_dir, tmp_path)

    assert len(results) == 2
    assert all(result.grader_type == "preference" for result in results)
    assert all(result.passed is None for result in results)
    assert all(result.grade_reason == "preference_ready" for result in results)
    assert all(result.artifact_file == "artifact.md" for result in results)
    assert report.aggregate(results, config_mod.BenchConfig("model-one", [])) == {}

    first_dir = snapshot_dir / "write-brief" / "model-one" / "trial-1"
    assert (first_dir / "artifact.md").read_text() == "A long generic answer.\nMore filler.\n"
    assert (first_dir / "grade.log").exists()
    persisted = json.loads((first_dir / "result.json").read_text())
    assert persisted["grader_type"] == "preference"
    assert persisted["passed"] is None


def test_trial_result_loads_objective_results_from_older_snapshots():
    old_result = {
        "task_id": "legacy-task",
        "category": "bugfix",
        "config_id": "legacy-config",
        "trial": 1,
        "passed": True,
        "grade_reason": "tests_passed",
        "cost_usd": 0.1,
        "agent_duration_seconds": 2.5,
        "agent_timed_out": False,
        "diff_bytes": 42,
    }

    loaded = runner.TrialResult.from_dict(old_result)

    assert loaded.grader_type == "tests"
    assert loaded.artifact_file is None
    assert loaded.passed is True


def test_preference_review_is_blinded_and_report_resolves_the_winner(
    preference_task_dir, tmp_path
):
    task, _, snapshot_dir, results = run_preference_fixture(
        preference_task_dir, tmp_path
    )

    count = preference.prepare_review(
        [task], results, snapshot_dir, ["model-one", "model-two"]
    )

    assert count == 1
    review_dir = snapshot_dir / "preference-review" / "write-brief" / "trial-1"
    assert (review_dir / "prompt.md").read_text() == task.prompt
    assert (review_dir / "rubric.md").read_text() == task.preference_rubric
    candidates = {
        "A": (review_dir / "candidate-a.md").read_text(),
        "B": (review_dir / "candidate-b.md").read_text(),
    }
    assert set(candidates.values()) == {
        "A long generic answer.\nMore filler.\n",
        "A concise, grounded answer.\n",
    }
    visible = "\n".join(
        path.read_text()
        for path in review_dir.iterdir()
        if path.is_file()
    )
    assert "model-one" not in visible
    assert "model-two" not in visible

    winner = next(label for label, text in candidates.items() if "grounded" in text)
    judgment_path = review_dir / "judgment.yaml"
    judgment_path.write_text(
        yaml.safe_dump({"winner": winner, "rationale": "More concise and grounded."})
    )

    data = preference.build_report(snapshot_dir, results, "preference-snap")
    assert data["pending"] == 0
    assert data["summary"]["model-two"]["wins"] == 1
    assert data["summary"]["model-one"]["losses"] == 1
    assert data["judgments"][0]["winner_config"] == "model-two"
    markdown = preference.render_markdown(data)
    assert "Blinded pairwise preference" in markdown
    assert "model-two" in markdown
    assert "More concise and grounded" in markdown

    # Preparing again refreshes candidates but never destroys completed review.
    preference.prepare_review([task], results, snapshot_dir, ["model-two", "model-one"])
    assert yaml.safe_load(judgment_path.read_text())["winner"] == winner


def test_preference_review_requires_exactly_two_configs(preference_task_dir, tmp_path):
    task, _, snapshot_dir, results = run_preference_fixture(
        preference_task_dir, tmp_path
    )

    with pytest.raises(preference.PreferenceError, match="exactly two"):
        preference.prepare_review([task], results, snapshot_dir, ["model-one"])


def test_preference_report_rejects_invalid_judgment(preference_task_dir, tmp_path):
    task, _, snapshot_dir, results = run_preference_fixture(
        preference_task_dir, tmp_path
    )
    preference.prepare_review(
        [task], results, snapshot_dir, ["model-one", "model-two"]
    )
    judgment = (
        snapshot_dir
        / "preference-review"
        / "write-brief"
        / "trial-1"
        / "judgment.yaml"
    )
    judgment.write_text("winner: model-two\nrationale: leaked identity\n")

    with pytest.raises(preference.PreferenceError, match="winner must be"):
        preference.build_report(snapshot_dir, results, "preference-snap")
