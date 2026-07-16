"""Grading: apply a candidate diff to a clean checkout, apply the held-out
test patch, run the tests, and record pass/fail.

Any agent edits to files touched by the held-out test patch are reverted
before the test patch is applied (SWE-bench style), so an agent can't pass by
rewriting the tests and grading can't fail on a test-file conflict.
"""

from __future__ import annotations

import dataclasses
import subprocess
import tempfile
from pathlib import Path

from bench import patches, workspace
from bench.task import Task


@dataclasses.dataclass
class GradeResult:
    passed: bool
    reason: str  # "tests_passed" | "tests_failed" | "patch_apply_failed" | "test_timeout"
    exit_code: int | None
    output: str


def capture_preference_artifact(task: Task, workdir: Path) -> GradeResult:
    """Validate and read the artifact produced for blinded preference review."""
    if task.grader_type != "preference" or not task.preference_artifact:
        raise ValueError("capture_preference_artifact requires a preference task")
    workdir = Path(workdir).resolve()
    artifact = workdir / task.preference_artifact
    resolved = artifact.resolve()
    if artifact.is_symlink() or not resolved.is_relative_to(workdir):
        return GradeResult(
            passed=False,
            reason="artifact_unsafe",
            exit_code=None,
            output=f"preference artifact {task.preference_artifact!r} escapes the workspace",
        )
    if not artifact.is_file():
        return GradeResult(
            passed=False,
            reason="artifact_missing",
            exit_code=None,
            output=f"expected preference artifact {task.preference_artifact!r}",
        )
    content = artifact.read_text(encoding="utf-8", errors="replace")
    if not content.strip():
        return GradeResult(
            passed=False,
            reason="artifact_empty",
            exit_code=None,
            output=f"preference artifact {task.preference_artifact!r} was empty",
        )
    return GradeResult(
        passed=True,
        reason="preference_ready",
        exit_code=0,
        output=content,
    )


def run_tests(task: Task, workdir: Path) -> GradeResult:
    """Run the task's test command in the configured environment."""
    if task.runner == "docker":
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network=none",
            "-v",
            f"{Path(workdir).resolve()}:/work",
            "-w",
            "/work",
            task.image,
            "sh",
            "-c",
            task.test_command,
        ]
        run_cwd = None
    else:
        cmd = ["sh", "-c", task.test_command]
        run_cwd = workdir
    try:
        proc = subprocess.run(
            cmd, cwd=run_cwd, capture_output=True, text=True, timeout=task.test_timeout
        )
    except subprocess.TimeoutExpired as e:
        out = e.stdout if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        return GradeResult(passed=False, reason="test_timeout", exit_code=None, output=out)
    output = proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr.strip() else "")
    passed = proc.returncode == 0
    return GradeResult(
        passed=passed,
        reason="tests_passed" if passed else "tests_failed",
        exit_code=proc.returncode,
        output=output,
    )


def grade_diff(task: Task, candidate_diff: str, scratch_dir: Path | None = None) -> GradeResult:
    """Grade a candidate diff from scratch: fresh checkout -> apply -> test."""
    with tempfile.TemporaryDirectory(dir=scratch_dir, prefix="bench-grade-") as tmp:
        workdir = workspace.checkout(task.repo_url, task.base_commit, Path(tmp) / "repo")
        try:
            workspace.apply_patch(workdir, candidate_diff)
        except workspace.GitError as e:
            return GradeResult(
                passed=False, reason="patch_apply_failed", exit_code=None, output=str(e)
            )
        return grade_workdir(task, workdir)


def grade_workdir(task: Task, workdir: Path) -> GradeResult:
    """Grade a workspace that already contains the candidate changes."""
    test_paths = sorted(patches.affected_paths(task.tests_patch))
    workspace.restore_paths(workdir, task.base_commit, test_paths)
    try:
        workspace.apply_patch(workdir, task.tests_patch)
    except workspace.GitError as e:
        # After restoring test paths to base, the held-out patch must apply;
        # failure means the task itself is broken, not the candidate.
        return GradeResult(
            passed=False,
            reason="patch_apply_failed",
            exit_code=None,
            output=f"held-out test patch failed to apply (broken task?):\n{e}",
        )
    return run_tests(task, workdir)
