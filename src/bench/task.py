"""Portable task contracts; evaluation evidence stays in the task pack."""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
import yaml


class TaskError(Exception):
    """A malformed or incomplete task."""


@dataclasses.dataclass
class Check:
    id: str
    command: str
    timeout_seconds: int = 600


@dataclasses.dataclass
class NegativeControl:
    id: str
    patch: str
    reason: str
    fails: list[str]


@dataclasses.dataclass
class Task:
    id: str
    category: str
    repo_url: str
    base_commit: str
    prompt: str
    tests_patch: str
    test_command: str
    test_timeout: int
    runner: str
    image: str | None
    solution_patch: str
    path: Path
    checks: list[Check] = dataclasses.field(default_factory=list)
    negative_controls: list[NegativeControl] = dataclasses.field(default_factory=list)
    criteria: list[dict] = dataclasses.field(default_factory=list)
    provenance: dict = dataclasses.field(default_factory=dict)
    limitations: list[str] = dataclasses.field(default_factory=list)
    protected_paths: list[str] = dataclasses.field(default_factory=list)

    @property
    def grading_checks(self) -> list[Check]:
        return self.checks or [Check("tests", self.test_command, self.test_timeout)]

    @classmethod
    def load(cls, task_dir: Path) -> "Task":
        task_dir = Path(task_dir)
        meta_path = task_dir / "task.yaml"
        def fail(message):
            raise TaskError(f"{meta_path}: {message}")
        def mapping(value, name):
            if not isinstance(value, dict):
                fail(f"{name} must be a mapping")
            return value
        def required(value, key, context=""):
            if key not in value or value[key] in (None, ""):
                fail(f"missing required field {context}{key}")
            return value[key]
        def string(value, name):
            if not isinstance(value, str) or not value.strip():
                fail(f"{name} must be a non-empty string")
            return value
        def identifier(value, name):
            if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", value):
                fail(f"{name} must be a safe identifier")
            return value
        def positive(value, name):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                fail(f"{name} must be a positive integer")
            return value
        def sequence(value, name):
            if not isinstance(value, list):
                fail(f"{name} must be a list")
            return value
        def relative(value, name):
            value = string(value, name)
            p = Path(value)
            if p.is_absolute() or ".." in p.parts or value == "." or ".git" in p.parts:
                fail(f"{name} must be a relative path within the task/workspace")
            return value
        def read_file(name, context):
            name = relative(name, context)
            path = task_dir / name
            if not path.resolve().is_relative_to(task_dir.resolve()) or not path.is_file():
                fail(f"missing {context} file {name!r}")
            return string(path.read_text(), context)
        if not meta_path.is_file():
            fail("missing task.yaml")
        try:
            meta = mapping(yaml.safe_load(meta_path.read_text()), "task")
        except yaml.YAMLError as exc:
            fail(f"invalid YAML: {exc}")
        task_id = identifier(required(meta, "id"), "id")
        if task_id != task_dir.name:
            fail(f"id {task_id!r} does not match directory name {task_dir.name!r}")
        repo = mapping(required(meta, "repo"), "repo")
        tests = mapping(required(meta, "tests"), "tests")
        env = mapping(meta.get("environment", {}), "environment")
        solution = mapping(required(meta, "solution"), "solution")
        evaluation = mapping(meta.get("evaluation", {}), "evaluation")
        runner = env.get("runner", "docker")
        if runner not in ("docker", "local"):
            fail("environment.runner must be 'docker' or 'local'")
        image = env.get("image")
        if runner == "docker" and not image:
            fail("environment.image is required when runner is 'docker'")
        prompt = read_file(meta.get("prompt_file", "prompt.md"), "prompt")
        if "TODO:" in prompt:
            fail("prompt still contains a TODO: marker - finish writing it")
        timeout = positive(tests.get("timeout_seconds", 600), "tests.timeout_seconds")
        checks = []
        for item in sequence(tests.get("checks", []), "tests.checks"):
            item = mapping(item, "check")
            checks.append(Check(identifier(required(item, "id"), "check.id"),
                                string(required(item, "command"), "check.command"),
                                positive(item.get("timeout_seconds", timeout), "check.timeout_seconds")))
        if len({c.id for c in checks}) != len(checks):
            fail("duplicate check ids")
        if checks and "command" in tests:
            fail("use tests.command or tests.checks, not both")
        command = "" if checks else string(required(tests, "command", "tests."), "tests.command")
        check_ids = {c.id for c in checks} if checks else {"tests"}
        criteria = sequence(evaluation.get("criteria", []), "evaluation.criteria")
        for criterion in criteria:
            mapping(criterion, "criterion")
            identifier(required(criterion, "id"), "criterion.id")
            string(required(criterion, "description"), "criterion.description")
            if criterion.get("check") not in check_ids:
                fail("criterion.check must name a grading check")
        if len({c["id"] for c in criteria}) != len(criteria):
            fail("duplicate criterion ids")
        controls = []
        for item in sequence(evaluation.get("negative_controls", []), "negative_controls"):
            mapping(item, "negative control")
            fails = sequence(required(item, "fails"), "negative control.fails")
            if not fails or any(c not in check_ids for c in fails):
                fail("negative control.fails must name grading checks")
            controls.append(NegativeControl(identifier(required(item, "id"), "control.id"),
                read_file(required(item, "patch_file"), "negative control patch"),
                string(required(item, "reason"), "control.reason"), fails))
        if len({c.id for c in controls}) != len(controls):
            fail("duplicate negative control ids")
        revision = string(required(repo, "base_commit", "repo."), "repo.base_commit")
        if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", revision):
            fail("repo.base_commit must be a full immutable commit hash")
        url = string(required(repo, "url", "repo."), "repo.url")
        local = (task_dir / url).expanduser()
        if not Path(url).expanduser().is_absolute() and local.exists():
            url = str(local.resolve())
        limitations = sequence(evaluation.get("limitations", []), "limitations")
        for limitation in limitations:
            string(limitation, "limitation")
        protected = [relative(p, "protected path") for p in sequence(tests.get("protected_paths", []), "protected_paths")]
        return cls(task_id, string(required(meta, "category"), "category"), url,
            string(required(repo, "base_commit", "repo."), "repo.base_commit"), prompt,
            read_file(required(tests, "patch_file", "tests."), "tests patch"), command,
            timeout, runner, image, read_file(required(solution, "patch_file", "solution."), "solution patch"),
            task_dir, checks, controls, criteria,
            mapping(meta.get("provenance", {}), "provenance"), limitations, protected)


def load_all(tasks_dir: Path) -> list[Task]:
    tasks_dir = Path(tasks_dir)
    if not tasks_dir.is_dir():
        raise TaskError(f"tasks directory not found: {tasks_dir}")
    tasks = [Task.load(p) for p in sorted(tasks_dir.iterdir())
             if p.is_dir() and (p / "task.yaml").exists()]
    if not tasks:
        raise TaskError(f"no tasks found under {tasks_dir}")
    return tasks
