import pytest
import yaml

from bench.task import Task, TaskError, load_all


def test_load_valid_task(task_dir):
    t = Task.load(task_dir)
    assert t.id == "fix-add"
    assert t.category == "bugfix"
    assert t.runner == "local"
    assert "add()" in t.prompt
    assert "test_calc" in t.tests_patch
    assert "calc.py" in t.solution_patch


def test_load_all(task_dir):
    tasks = load_all(task_dir.parent)
    assert [t.id for t in tasks] == ["fix-add"]


def test_id_must_match_directory(task_dir):
    meta = yaml.safe_load((task_dir / "task.yaml").read_text())
    meta["id"] = "something-else"
    (task_dir / "task.yaml").write_text(yaml.safe_dump(meta))
    with pytest.raises(TaskError, match="does not match directory"):
        Task.load(task_dir)


def test_todo_prompt_rejected(task_dir):
    (task_dir / "prompt.md").write_text("TODO: write me\n")
    with pytest.raises(TaskError, match="TODO"):
        Task.load(task_dir)


def test_docker_requires_image(task_dir):
    meta = yaml.safe_load((task_dir / "task.yaml").read_text())
    meta["environment"] = {"runner": "docker"}
    (task_dir / "task.yaml").write_text(yaml.safe_dump(meta))
    with pytest.raises(TaskError, match="image"):
        Task.load(task_dir)


def test_missing_patch_file(task_dir):
    (task_dir / "tests.patch").unlink()
    with pytest.raises(TaskError, match="tests patch"):
        Task.load(task_dir)


def test_relative_local_repo_is_resolved_from_task_directory(task_dir):
    fixture = task_dir / "fixture.bundle"
    fixture.write_text("placeholder")
    meta = yaml.safe_load((task_dir / "task.yaml").read_text())
    meta["repo"]["url"] = "fixture.bundle"
    (task_dir / "task.yaml").write_text(yaml.safe_dump(meta))

    task = Task.load(task_dir)

    assert task.repo_url == str(fixture.resolve())
