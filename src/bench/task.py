"""Task model: a reproducible, gradeable unit of work.

A test-graded task is a directory containing:

    task.yaml       -- metadata (see schema below)
    prompt.md       -- the task description given to the agent
    tests.patch     -- held-out tests applied at grading time
    solution.patch  -- known-good fix, used by the smoke-test gate

A preference task instead declares ``grader.type: preference`` plus a named
artifact and a private rubric. Its artifact is captured for blinded manual A/B
review and is never treated as an objective pass.

task.yaml schema::

    id: fix-date-parse            # must match the directory name
    category: bugfix              # free-form; used for per-category routing
    repo:
      url: /path/or/git/url      # anything `git clone` accepts
      base_commit: <sha>          # state the agent starts from
    prompt_file: prompt.md
    tests:
      patch_file: tests.patch
      command: python -m pytest tests/ -x -q
      timeout_seconds: 600
    environment:
      runner: docker              # "docker" or "local"
      image: python:3.11-slim     # required for docker
    solution:
      patch_file: solution.patch

Preference grader alternative::

    grader:
      type: preference
      artifact: answer.md
      rubric_file: rubric.md
"""

from __future__ import annotations

import dataclasses
from pathlib import Path, PurePosixPath

import yaml


class TaskError(Exception):
    """Raised when a task directory is malformed."""


@dataclasses.dataclass
class Task:
    id: str
    category: str
    grader_type: str
    repo_url: str
    base_commit: str
    prompt: str
    tests_patch: str
    test_command: str
    test_timeout: int
    runner: str
    image: str | None
    solution_patch: str
    preference_artifact: str | None
    preference_rubric: str | None
    path: Path

    @classmethod
    def load(cls, task_dir: Path) -> "Task":
        task_dir = Path(task_dir)
        meta_path = task_dir / "task.yaml"
        if not meta_path.is_file():
            raise TaskError(f"{task_dir}: missing task.yaml")
        try:
            meta = yaml.safe_load(meta_path.read_text())
        except yaml.YAMLError as e:
            raise TaskError(f"{meta_path}: invalid YAML: {e}") from e
        if not isinstance(meta, dict):
            raise TaskError(f"{meta_path}: expected a mapping at top level")

        def require(d: dict, key: str, ctx: str):
            if key not in d or d[key] in (None, ""):
                raise TaskError(f"{meta_path}: missing required field {ctx}{key}")
            return d[key]

        task_id = require(meta, "id", "")
        if task_id != task_dir.name:
            raise TaskError(
                f"{meta_path}: id {task_id!r} does not match directory name {task_dir.name!r}"
            )
        repo = require(meta, "repo", "")
        grader = meta.get("grader") or {"type": "tests"}
        if not isinstance(grader, dict):
            raise TaskError(f"{meta_path}: grader must be a mapping")
        grader_type = str(grader.get("type", "tests"))
        if grader_type not in ("tests", "preference"):
            raise TaskError(
                f"{meta_path}: grader.type must be 'tests' or 'preference'"
            )
        env = meta.get("environment") or {}

        runner = env.get("runner", "docker")
        if runner not in ("docker", "local"):
            raise TaskError(f"{meta_path}: environment.runner must be 'docker' or 'local'")
        image = env.get("image")
        if runner == "docker" and not image:
            raise TaskError(f"{meta_path}: environment.image is required when runner is 'docker'")

        def read_file(name: str, ctx: str) -> str:
            p = task_dir / name
            if not p.is_file():
                raise TaskError(f"{task_dir}: missing {ctx} file {name!r}")
            return p.read_text()

        prompt = read_file(meta.get("prompt_file", "prompt.md"), "prompt")
        # "TODO:" (with colon) is the scaffold's fill-me-in marker; a bare
        # "TODO" may legitimately appear in a prompt about TODO comments.
        if "TODO:" in prompt:
            raise TaskError(
                f"{task_dir}: prompt still contains a TODO: marker - finish writing it "
                "(scaffolded prompts must be rewritten by hand)"
            )

        tests_patch = ""
        test_command = ""
        test_timeout = 600
        solution_patch = ""
        preference_artifact = None
        preference_rubric = None
        if grader_type == "tests":
            tests = require(meta, "tests", "")
            solution = require(meta, "solution", "")
            tests_patch = read_file(
                require(tests, "patch_file", "tests."), "tests patch"
            )
            test_command = str(require(tests, "command", "tests."))
            test_timeout = int(tests.get("timeout_seconds", 600))
            solution_patch = read_file(
                require(solution, "patch_file", "solution."), "solution patch"
            )
        else:
            preference_artifact = str(require(grader, "artifact", "grader."))
            normalized = preference_artifact.replace("\\", "/")
            artifact_path = PurePosixPath(normalized)
            if (
                artifact_path.is_absolute()
                or artifact_path in (PurePosixPath("."), PurePosixPath(""))
                or ".." in artifact_path.parts
            ):
                raise TaskError(
                    f"{meta_path}: grader.artifact must be a safe relative path"
                )
            preference_artifact = artifact_path.as_posix()
            preference_rubric = read_file(
                require(grader, "rubric_file", "grader."), "preference rubric"
            )
            if "TODO:" in preference_rubric:
                raise TaskError(
                    f"{task_dir}: preference rubric still contains a TODO: marker"
                )

        repo_url = str(require(repo, "url", "repo."))
        local_repo = (task_dir / repo_url).expanduser()
        if not Path(repo_url).expanduser().is_absolute() and local_repo.exists():
            repo_url = str(local_repo.resolve())

        return cls(
            id=task_id,
            category=str(require(meta, "category", "")),
            grader_type=grader_type,
            repo_url=repo_url,
            base_commit=str(require(repo, "base_commit", "repo.")),
            prompt=prompt,
            tests_patch=tests_patch,
            test_command=test_command,
            test_timeout=test_timeout,
            runner=runner,
            image=image,
            solution_patch=solution_patch,
            preference_artifact=preference_artifact,
            preference_rubric=preference_rubric,
            path=task_dir,
        )


def load_all(tasks_dir: Path) -> list[Task]:
    """Load every task under ``tasks_dir``; raise TaskError on the first bad one."""
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.is_dir():
        raise TaskError(f"tasks directory not found: {tasks_dir}")
    tasks = []
    for entry in sorted(tasks_dir.iterdir()):
        if entry.is_dir() and (entry / "task.yaml").exists():
            tasks.append(Task.load(entry))
    if not tasks:
        raise TaskError(f"no tasks found under {tasks_dir}")
    return tasks
