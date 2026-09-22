from pathlib import Path

import pytest

from bench.mine import git_history
from bench.task import Task, TaskError


def test_find_candidates(fixture_repo):
    candidates = git_history.find_candidates(fixture_repo["repo"])
    assert len(candidates) == 1
    c = candidates[0]
    assert c.sha == fixture_repo["fix"]
    assert c.source_files == ["calc.py"]
    assert c.test_files == ["tests/test_calc.py"]


def test_scaffold_roundtrip(fixture_repo, tmp_path):
    out = git_history.scaffold(
        fixture_repo["repo"], fixture_repo["fix"], tmp_path / "fix-add"
    )
    assert (out / "task.yaml").exists()
    assert "calc.py" in (out / "solution.patch").read_text()
    assert "test_calc" in (out / "tests.patch").read_text()
    # base commit is the parent of the fix
    assert fixture_repo["base"] in (out / "task.yaml").read_text()

    # The scaffold must not load as-is: the prompt is a stub the human rewrites.
    with pytest.raises(TaskError, match="TODO"):
        Task.load(out)

    # After finishing it by hand, it loads.
    (out / "prompt.md").write_text("Fix the add() function in calc.py.\n")
    meta = (out / "task.yaml").read_text().replace(
        "python -m pytest -x -q  # TODO: set the real test command",
        "python -m pytest tests/ -x -q",
    ).replace(
        "runner: docker", "runner: local"
    ).replace(
        "  image: python:3.11-slim  # TODO: set an image with the repo's deps\n", ""
    )
    (out / "task.yaml").write_text(meta)
    task = Task.load(out)
    assert task.base_commit == fixture_repo["base"]


def test_scaffold_rejects_test_only_commit(fixture_repo, tmp_path):
    repo = fixture_repo["repo"]
    from tests.conftest import git

    (Path(repo) / "tests" / "test_more.py").write_text("def test_more():\n    assert True\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add another test")
    sha = git(repo, "rev-parse", "HEAD")
    with pytest.raises(git_history.MineError, match="only changes test files"):
        git_history.scaffold(repo, sha, tmp_path / "nope")


def test_discovery_can_include_work_without_tests(fixture_repo):
    from tests.conftest import git
    repo = fixture_repo['repo']
    (repo / 'calc.py').write_text('def add(a,b):\n    return sum([a,b])\n')
    git(repo, 'add', '-A');git(repo, 'commit', '-qm', 'refactor implementation')
    candidates = git_history.find_candidates(repo, include_untested=True)
    assert candidates[0].test_files == []
    assert 'needs_grader' in candidates[0].review_flags
    assert not git_history.find_candidates(repo, since='2099-01-01')
