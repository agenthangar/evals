"""Mine candidate tasks from a repository's git history.

A good candidate commit changes both source files and test files: the source
part becomes the known-good solution, the test part becomes the held-out
grading tests, and the parent commit is the reproducible starting state.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
from pathlib import Path

from bench import patches


class MineError(Exception):
    pass


def _git(repo: Path, args: list[str]) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise MineError(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


@dataclasses.dataclass
class Candidate:
    sha: str
    subject: str
    source_files: list[str]
    test_files: list[str]


def find_candidates(repo: Path, limit: int = 200, max_source_files: int = 20) -> list[Candidate]:
    """Scan recent history for commits that touch both source and tests."""
    repo = Path(repo)
    log = _git(
        repo,
        ["log", f"-{limit}", "--no-merges", "--name-only", "--pretty=format:@@%H %s"],
    )
    candidates: list[Candidate] = []
    sha = subject = None
    files: list[str] = []

    def flush():
        if sha is None:
            return
        tests = [f for f in files if patches.is_test_path(f)]
        source = [f for f in files if f and not patches.is_test_path(f)]
        if tests and source and len(source) <= max_source_files:
            candidates.append(
                Candidate(sha=sha, subject=subject, source_files=source, test_files=tests)
            )

    for line in log.splitlines():
        if line.startswith("@@"):
            flush()
            sha, _, subject = line[2:].partition(" ")
            files = []
        elif line.strip():
            files.append(line.strip())
    flush()
    return candidates


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 48) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "task"


def scaffold(repo: Path, commit: str, out_dir: Path, category: str = "bugfix") -> Path:
    """Create a task directory skeleton from one commit.

    The scaffold is deliberately incomplete: the generated prompt contains a
    TODO marker and task validation refuses to load it until a human rewrites
    the prompt as a real task description (the commit message is a record of
    what was done, not a specification of what to do).
    """
    repo = Path(repo).resolve()
    sha = _git(repo, ["rev-parse", commit]).strip()
    parent = _git(repo, ["rev-parse", f"{sha}^"]).strip()
    subject = _git(repo, ["log", "-1", "--pretty=%s", sha]).strip()
    body = _git(repo, ["log", "-1", "--pretty=%b", sha]).strip()
    full_diff = _git(repo, ["diff", "--binary", parent, sha])

    tests_patch, solution_patch = patches.split_by_paths(full_diff, patches.is_test_path)
    if not tests_patch.strip():
        raise MineError(f"{sha[:12]}: commit does not change any test files")
    if not solution_patch.strip():
        raise MineError(f"{sha[:12]}: commit only changes test files - nothing to solve")

    task_id = out_dir.name if out_dir.name else slugify(subject)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "solution.patch").write_text(solution_patch)
    (out_dir / "tests.patch").write_text(tests_patch)
    (out_dir / "prompt.md").write_text(
        "TODO: rewrite this as a task description an agent could act on\n"
        "(what is broken / needed, how to reproduce, where to look - do NOT\n"
        "paste the solution). Original commit message for reference:\n\n"
        f"> {subject}\n\n{body}\n"
    )
    (out_dir / "task.yaml").write_text(
        "\n".join(
            [
                f"id: {task_id}",
                f"category: {category}",
                "repo:",
                f"  url: {repo}",
                f"  base_commit: {parent}",
                "prompt_file: prompt.md",
                "tests:",
                "  patch_file: tests.patch",
                "  command: python -m pytest -x -q  # TODO: set the real test command",
                "  timeout_seconds: 600",
                "environment:",
                "  runner: docker",
                "  image: python:3.11-slim  # TODO: set an image with the repo's deps",
                "solution:",
                "  patch_file: solution.patch",
                "",
            ]
        )
    )
    return out_dir
