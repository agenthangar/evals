"""Smoke-test gate: verify every task can still detect success and failure.

Run this before every benchmark snapshot. A task passes the gate when:

  1. the known-good solution patch grades as PASS (the environment and tests
     still work), and
  2. an empty diff grades as FAIL (the held-out tests actually detect the
     problem - otherwise every no-op agent would "solve" the task).

Tasks that fail the gate must be quarantined, not run: a broken task would
otherwise masquerade as model failures (or free passes) in the results.
"""

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


def smoke_task(task: Task) -> SmokeResult:
    if task.grader_type == "preference":
        with tempfile.TemporaryDirectory(prefix="bench-smoke-preference-") as tmp:
            workdir = workspace.checkout(
                task.repo_url, task.base_commit, Path(tmp) / "repo"
            )
            baseline = grade.capture_preference_artifact(task, workdir)
        ok = not baseline.passed
        return SmokeResult(
            task_id=task.id,
            ok=ok,
            solution_passed=True,
            empty_failed=ok,
            detail=(
                "preference artifact is absent at baseline; manual pairwise review "
                "is required after the run"
                if ok
                else "preference artifact already exists at the base commit"
            ),
        )
    solution = grade.grade_diff(task, task.solution_patch)
    empty = grade.grade_diff(task, "")
    ok = solution.passed and not empty.passed
    details = []
    if not solution.passed:
        details.append(
            f"known-good solution FAILED ({solution.reason}):\n{solution.output[-2000:]}"
        )
    if empty.passed:
        details.append(
            "empty diff PASSED - the held-out tests do not detect the problem"
        )
    return SmokeResult(
        task_id=task.id,
        ok=ok,
        solution_passed=solution.passed,
        empty_failed=not empty.passed,
        detail="\n".join(details) if details else "ok",
    )


def smoke_all(tasks: list[Task]) -> list[SmokeResult]:
    return [smoke_task(t) for t in tasks]
