"""Run orchestration: task x config x trial matrix for one snapshot.

Results land under::

    runs/<snapshot>/<task>/<config>/trial-<n>/
        result.json     -- everything the reporter needs
        diff.patch      -- the agent's final diff against the base commit
        agent.log       -- harness stdout/stderr
        tests.log       -- grading output

A snapshot is one internally-consistent measurement window (all configs run
in the same period). Never compare numbers across snapshots - product
harnesses change between them.
"""

from __future__ import annotations

import dataclasses
import json
import tempfile
import time
from pathlib import Path

from bench import grade, harness, workspace
from bench.config import BenchConfig, ProductConfig
from bench.task import Task

DEFAULT_AGENT_TIMEOUT = 1800  # seconds per agent run


class RunError(Exception):
    """Raised when a requested benchmark matrix cannot be constructed."""


@dataclasses.dataclass
class TrialResult:
    task_id: str
    category: str
    config_id: str
    trial: int
    passed: bool | None
    grade_reason: str
    cost_usd: float | None
    agent_duration_seconds: float
    agent_timed_out: bool
    diff_bytes: int
    # Keep new preference fields after the original constructor fields so
    # pre-preference positional construction remains backward compatible.
    grader_type: str = "tests"
    artifact_file: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TrialResult":
        """Load current results and objective results from older snapshots."""
        normalized = dict(data)
        normalized.setdefault("grader_type", "tests")
        normalized.setdefault("artifact_file", None)
        return cls(**normalized)


def run_trial(
    task: Task,
    config: ProductConfig,
    trial: int,
    out_dir: Path,
    agent_timeout: int = DEFAULT_AGENT_TIMEOUT,
) -> TrialResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter = harness.get(config.harness)

    with tempfile.TemporaryDirectory(prefix="bench-run-") as tmp:
        workdir = workspace.checkout(task.repo_url, task.base_commit, Path(tmp) / "repo")
        agent = adapter.run(config, workdir, task.prompt, timeout=agent_timeout)
        diff = workspace.capture_diff(workdir, task.base_commit)
        if task.grader_type == "preference":
            graded = grade.capture_preference_artifact(task, workdir)
        else:
            graded = grade.grade_workdir(task, workdir)

    (out_dir / "diff.patch").write_text(diff)
    (out_dir / "agent.log").write_text(
        f"$ {config.harness} (model={config.model})\n"
        f"exit={agent.exit_code} timed_out={agent.timed_out} "
        f"duration={agent.duration_seconds:.1f}s\n"
        f"--- stdout ---\n{agent.stdout}\n--- stderr ---\n{agent.stderr}\n"
    )
    artifact_file = None
    if task.grader_type == "preference":
        (out_dir / "grade.log").write_text(
            f"{graded.reason}: {task.preference_artifact}\n"
        )
        if graded.passed:
            artifact_file = "artifact.md"
            (out_dir / artifact_file).write_text(graded.output)
    else:
        (out_dir / "tests.log").write_text(graded.output)

    result = TrialResult(
        task_id=task.id,
        category=task.category,
        config_id=config.id,
        trial=trial,
        grader_type=task.grader_type,
        passed=graded.passed if task.grader_type == "tests" else None,
        grade_reason=graded.reason,
        cost_usd=config.cost.cost_usd(
            agent.cost_usd,
            agent.input_tokens,
            agent.output_tokens,
            agent.cached_input_tokens,
        ),
        agent_duration_seconds=round(agent.duration_seconds, 2),
        agent_timed_out=agent.timed_out,
        diff_bytes=len(diff.encode()),
        artifact_file=artifact_file,
    )
    (out_dir / "result.json").write_text(json.dumps(result.to_dict(), indent=2) + "\n")
    return result


def run_matrix(
    tasks: list[Task],
    bench_config: BenchConfig,
    snapshot_dir: Path,
    trials: int = 3,
    config_ids: list[str] | None = None,
    task_ids: list[str] | None = None,
    agent_timeout: int = DEFAULT_AGENT_TIMEOUT,
    log=print,
) -> list[TrialResult]:
    """Run every (task, config, trial) cell, skipping cells that already have
    a result.json so an interrupted snapshot can be resumed."""
    if trials <= 0:
        raise RunError("trials must be greater than zero")
    if agent_timeout <= 0:
        raise RunError("agent timeout must be greater than zero")

    available_config_ids = {c.id for c in bench_config.configs}
    requested_config_ids = set(config_ids or [])
    unknown_configs = sorted(requested_config_ids - available_config_ids)
    if unknown_configs:
        available = ", ".join(sorted(available_config_ids))
        raise RunError(
            f"unknown config id(s): {', '.join(unknown_configs)}; available: {available}"
        )

    available_task_ids = {t.id for t in tasks}
    requested_task_ids = set(task_ids or [])
    unknown_tasks = sorted(requested_task_ids - available_task_ids)
    if unknown_tasks:
        available = ", ".join(sorted(available_task_ids))
        raise RunError(
            f"unknown task id(s): {', '.join(unknown_tasks)}; available: {available}"
        )

    configs = [
        c
        for c in bench_config.configs
        if config_ids is None or c.id in config_ids
    ]
    selected = [t for t in tasks if task_ids is None or t.id in task_ids]
    if not configs:
        raise RunError("no configurations selected")
    if not selected:
        raise RunError("no tasks selected")
    results: list[TrialResult] = []
    total = len(selected) * len(configs) * trials
    done = 0
    started = time.monotonic()
    for task in selected:
        for config in configs:
            for trial in range(1, trials + 1):
                done += 1
                out_dir = snapshot_dir / task.id / config.id / f"trial-{trial}"
                existing = out_dir / "result.json"
                if existing.exists():
                    data = json.loads(existing.read_text())
                    results.append(TrialResult.from_dict(data))
                    log(f"[{done}/{total}] {task.id} / {config.id} #{trial}: cached")
                    continue
                result = run_trial(task, config, trial, out_dir, agent_timeout)
                results.append(result)
                if result.grader_type == "preference":
                    status = (
                        "READY (preference review)"
                        if result.grade_reason == "preference_ready"
                        else f"FAIL ({result.grade_reason})"
                    )
                else:
                    status = "PASS" if result.passed else f"FAIL ({result.grade_reason})"
                cost = f"${result.cost_usd:.2f}" if result.cost_usd is not None else "cost n/a"
                log(f"[{done}/{total}] {task.id} / {config.id} #{trial}: {status}, {cost}")
    log(f"snapshot complete: {done} trials in {time.monotonic() - started:.0f}s")
    return results


def load_results(snapshot_dir: Path) -> list[TrialResult]:
    """Load all persisted trial results for a snapshot."""
    results = []
    for path in sorted(Path(snapshot_dir).glob("*/*/trial-*/result.json")):
        results.append(TrialResult.from_dict(json.loads(path.read_text())))
    return results
