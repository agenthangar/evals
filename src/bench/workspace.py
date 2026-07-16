"""Git workspace management: reproducible checkouts and diff capture."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def _git(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc


def checkout(repo_url: str, commit: str, dest: Path) -> Path:
    """Clone ``repo_url`` into ``dest`` and check out ``commit`` (detached)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(["clone", "--quiet", repo_url, str(dest)])
    _git(["-c", "advice.detachedHead=false", "checkout", "--quiet", commit], cwd=dest)
    # Agents may commit; give them an identity so that doesn't error out.
    _git(["config", "user.email", "bench@localhost"], cwd=dest)
    _git(["config", "user.name", "bench"], cwd=dest)
    return dest


def apply_patch(workdir: Path, patch_text: str) -> None:
    """Apply a git-format patch to the working tree (no commit)."""
    if not patch_text.strip():
        return
    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=workdir,
        input=patch_text,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitError(f"git apply failed:\n{proc.stderr.strip()}")


def capture_diff(workdir: Path, base_commit: str) -> str:
    """Diff of the workspace's final state against ``base_commit``.

    Stages everything first so new files are included, and diffs the index
    against the base commit so it also works when the agent made commits.
    """
    _git(["add", "-A"], cwd=workdir)
    proc = _git(["diff", "--binary", "--cached", base_commit], cwd=workdir)
    return proc.stdout


def restore_paths(workdir: Path, base_commit: str, paths: list[str]) -> None:
    """Reset the given paths back to their state at ``base_commit``.

    Paths that did not exist at the base commit are removed. Used to strip
    agent edits to held-out test files before the test patch is applied.
    """
    if not paths:
        return
    existing = set(
        _git(["ls-tree", "-r", "--name-only", base_commit], cwd=workdir).stdout.splitlines()
    )
    to_restore = [p for p in paths if p in existing]
    to_delete = [p for p in paths if p not in existing]
    if to_restore:
        _git(["checkout", base_commit, "--", *to_restore], cwd=workdir)
    for p in to_delete:
        target = Path(workdir) / p
        if target.is_file():
            target.unlink()
