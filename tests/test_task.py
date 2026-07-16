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


def test_task_preserves_legacy_positional_constructor(tmp_path):
    task = Task(
        "legacy-task",
        "bugfix",
        "repo",
        "base",
        "prompt",
        "tests patch",
        "python -m pytest",
        60,
        "local",
        None,
        "solution patch",
        tmp_path,
    )

    assert task.grader_type == "tests"
    assert task.preference_artifact is None
    assert task.preference_rubric is None


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


def test_load_preference_task_without_test_or_solution_patches(preference_task_dir):
    task = Task.load(preference_task_dir)

    assert task.grader_type == "preference"
    assert task.preference_artifact == "answer.md"
    assert "concise" in task.preference_rubric
    assert task.tests_patch == ""
    assert task.solution_patch == ""


def test_preference_task_requires_rubric_file(preference_task_dir):
    meta = yaml.safe_load((preference_task_dir / "task.yaml").read_text())
    del meta["grader"]["rubric_file"]
    (preference_task_dir / "task.yaml").write_text(yaml.safe_dump(meta))

    with pytest.raises(TaskError, match="grader.rubric_file"):
        Task.load(preference_task_dir)


@pytest.mark.parametrize("artifact", ["/tmp/answer.md", "../answer.md", "output/../../x"])
def test_preference_artifact_must_be_a_safe_relative_path(
    preference_task_dir, artifact
):
    meta = yaml.safe_load((preference_task_dir / "task.yaml").read_text())
    meta["grader"]["artifact"] = artifact
    (preference_task_dir / "task.yaml").write_text(yaml.safe_dump(meta))

    with pytest.raises(TaskError, match="safe relative path"):
        Task.load(preference_task_dir)


def test_unknown_grader_type_is_rejected(preference_task_dir):
    meta = yaml.safe_load((preference_task_dir / "task.yaml").read_text())
    meta["grader"]["type"] = "vibes"
    (preference_task_dir / "task.yaml").write_text(yaml.safe_dump(meta))

    with pytest.raises(TaskError, match="grader.type"):
        Task.load(preference_task_dir)
