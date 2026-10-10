"""Calibrate graders against good, empty and plausible wrong solutions."""
from __future__ import annotations
import dataclasses
import tempfile
from pathlib import Path
from bench import grade, workspace
from bench.task import Task

@dataclasses.dataclass
class SmokeResult:
    task_id: str
    ok: bool
    solution_passed: bool
    empty_failed: bool
    detail: str
    controls: list[dict] = dataclasses.field(default_factory=list)


def smoke_task(task: Task, repeats: int = 1) -> SmokeResult:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if task.grader_type == "preference":
        with tempfile.TemporaryDirectory(prefix="bench-smoke-preference-") as tmp:
            workdir = workspace.checkout(task.repo_url, task.base_commit, Path(tmp) / "repo")
            baseline = grade.capture_preference_artifact(task, workdir)
        ok = baseline.reason == "artifact_missing"
        if ok:
            detail = ("preference artifact is absent at baseline; manual pairwise review "
                      "is required after the run")
        elif baseline.reason == "preference_ready":
            detail = "preference artifact already exists at the base commit"
        else:
            detail = (f"preference artifact baseline is invalid ({baseline.reason}): "
                      f"{baseline.output}")
        return SmokeResult(task.id, ok, True, ok, detail, [])
    details, evidence = [], []
    solution_passed = empty_failed = True
    for repeat in range(1, repeats + 1):
        solution = grade.grade_diff(task, task.solution_patch)
        empty = grade.grade_diff(task, "")
        solution_passed &= solution.passed
        # An invalid patch or timeout is not evidence the assertions catch a bug.
        empty_failed &= empty.reason == "tests_failed"
        if not solution.passed:
            details.append(f"known-good solution FAILED ({solution.reason}):\n{solution.output[-2000:]}")
        if empty.reason != "tests_failed":
            details.append(f"empty diff must fail tests, got {empty.reason}:\n{empty.output[-1000:]}")
        for control in task.negative_controls:
            result = grade.grade_diff(task, control.patch)
            failed_checks = {c["id"] for c in result.checks if c["reason"] == "tests_failed"}
            detected = set(control.fails) <= failed_checks
            evidence.append({"id": control.id, "repeat": repeat, "detected": detected,
                             "reason": result.reason, "failed_checks": sorted(failed_checks)})
            if not detected:
                details.append(f"negative control {control.id} was not detected by {control.fails} ({result.reason})")
    return SmokeResult(task.id, not details, solution_passed, empty_failed,
                       "\n".join(details) or "ok", evidence)


def smoke_all(tasks: list[Task], repeats: int = 1) -> list[SmokeResult]:
    return [smoke_task(t, repeats) for t in tasks]
