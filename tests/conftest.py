"""Shared fixtures: a small real git repo with a bug, a fix commit that also
adds tests, and helpers to build task directories from it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

BUGGY_CALC = '''\
def add(a, b):
    return a - b  # BUG: should be addition
'''

FIXED_CALC = '''\
def add(a, b):
    return a + b
'''

TEST_FILE = '''\
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from calc import add


def test_add():
    assert add(2, 3) == 5
'''


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def git_raw(repo: Path, *args: str) -> str:
    """Like git() but without stripping - patches need their trailing newline."""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


@pytest.fixture
def fixture_repo(tmp_path_factory) -> dict:
    """A repo whose HEAD commit fixes calc.py and adds tests/test_calc.py.

    Returns {"repo": path, "base": parent sha, "fix": fix sha}.
    """
    repo = tmp_path_factory.mktemp("fixture-repo")
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")

    (repo / "calc.py").write_text(BUGGY_CALC)
    (repo / "README.md").write_text("demo repo\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial (buggy)")
    base = git(repo, "rev-parse", "HEAD")

    (repo / "calc.py").write_text(FIXED_CALC)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_calc.py").write_text(TEST_FILE)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fix add() returning difference instead of sum")
    fix = git(repo, "rev-parse", "HEAD")

    return {"repo": repo, "base": base, "fix": fix}


@pytest.fixture
def task_dir(fixture_repo, tmp_path) -> Path:
    """A complete, valid task directory built from the fixture repo."""
    repo = fixture_repo["repo"]
    base, fix = fixture_repo["base"], fixture_repo["fix"]
    full_diff = git_raw(repo, "diff", "--binary", base, fix)

    from bench import patches

    tests_patch, solution_patch = patches.split_by_paths(full_diff, patches.is_test_path)

    d = tmp_path / "tasks" / "fix-add"
    d.mkdir(parents=True)
    (d / "prompt.md").write_text(
        "The add() function in calc.py returns the wrong result: add(2, 3) "
        "gives -1. Fix it so it returns the sum of its arguments.\n"
    )
    (d / "tests.patch").write_text(tests_patch)
    (d / "solution.patch").write_text(solution_patch)
    (d / "task.yaml").write_text(
        f"""\
id: fix-add
category: bugfix
repo:
  url: {repo}
  base_commit: {base}
prompt_file: prompt.md
tests:
  patch_file: tests.patch
  command: {sys.executable} -m pytest tests/ -x -q
  timeout_seconds: 120
environment:
  runner: local
solution:
  patch_file: solution.patch
"""
    )
    return d
