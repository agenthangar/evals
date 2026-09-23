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
import hashlib
import random
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from bench import __version__, grade, harness, workspace
from bench.config import BenchConfig, ProductConfig
from bench.task import Task

DEFAULT_AGENT_TIMEOUT = 1800  # seconds per agent run


class RunError(Exception):
    """Raised when a requested benchmark matrix cannot be constructed."""


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _config_fingerprint(config: ProductConfig) -> str:
    contract = dataclasses.asdict(config)
    if config.patch_file:
        contract["patch_contents"] = Path(config.patch_file).read_text()
    return _digest(contract)


def verify_report_config(snapshot_dir: Path, config: BenchConfig) -> None:
    path = Path(snapshot_dir) / "manifest.json"
    if not path.exists():
        return  # legacy reports remain readable, with conservative comparisons
    manifest = json.loads(path.read_text())
    if manifest["incumbent"] != config.incumbent:
        raise RunError("report incumbent differs from the frozen snapshot")
    for entry in manifest["configs"]:
        if _config_fingerprint(config.by_id(entry["id"])) != entry["sha256"]:
            raise RunError("report configuration differs from the frozen snapshot")


@dataclasses.dataclass
class TrialResult:
    task_id: str
    category: str
    config_id: str
    trial: int
    passed: bool
    grade_reason: str
    cost_usd: float | None
    agent_duration_seconds: float
    agent_timed_out: bool
    diff_bytes: int
    check_results: list[dict] = dataclasses.field(default_factory=list)
    # None preserves old snapshots without inventing an execution outcome.
    agent_exit_code: int | None = None
    artifact_passed: bool | None = None
    artifact_grade_reason: str | None = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


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
        workdir, base = workspace.agent_checkout(task.repo_url, task.base_commit, Path(tmp) / "repo")
        agent = adapter.run(config, workdir, task.prompt, timeout=agent_timeout)
        diff = workspace.capture_diff(workdir, base)
        graded = grade.grade_diff(task, diff)

    (out_dir / "diff.patch").write_text(diff)
    (out_dir / "agent.log").write_text(
        f"$ {config.harness} (model={config.model})\n"
        f"exit={agent.exit_code} timed_out={agent.timed_out} "
        f"duration={agent.duration_seconds:.1f}s\n"
        f"--- stdout ---\n{agent.stdout}\n--- stderr ---\n{agent.stderr}\n"
    )
    (out_dir / "tests.log").write_text(graded.output)

    result = TrialResult(
        task_id=task.id,
        category=task.category,
        config_id=config.id,
        trial=trial,
        passed=graded.passed and agent.exit_code == 0 and not agent.timed_out,
        grade_reason=("agent_timed_out" if agent.timed_out else
                      "agent_exited_nonzero" if agent.exit_code != 0 else graded.reason),
        cost_usd=config.cost.cost_usd(
            agent.cost_usd,
            agent.input_tokens,
            agent.output_tokens,
            agent.cached_input_tokens,
        ),
        agent_duration_seconds=round(agent.duration_seconds, 2),
        agent_timed_out=agent.timed_out,
        diff_bytes=len(diff.encode()),
        check_results=[{k: v for k, v in c.items() if k != "output"} for c in graded.checks],
        agent_exit_code=agent.exit_code,
        artifact_passed=graded.passed,
        artifact_grade_reason=graded.reason,
    )
    pending = out_dir / "result.json.tmp"
    pending.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
    pending.replace(out_dir / "result.json")
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
    # Refuse stale cache reuse when any task, grader, model or budget changes.
    snapshot_dir = Path(snapshot_dir)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", snapshot_dir.name):
        raise RunError("snapshot name must be a safe identifier")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    task_contracts = []
    for task in sorted(selected, key=lambda t: t.id):
        contract = dataclasses.asdict(task)
        contract.pop("path")
        task_contracts.append({"id": task.id, "sha256": _digest(contract)})
    config_contracts = []
    for config in sorted(configs, key=lambda c: c.id):
        config_contracts.append({"id": config.id, "sha256": _config_fingerprint(config),
                                 "harness": config.harness, "model": config.model,
                                 "extra_args": config.extra_args})
    versions = {}
    for binary in sorted({{"codex": "codex", "claude-code": "claude", "cursor": "cursor-agent"}.get(c.harness, "") for c in configs} - {""}):
        try:
            proc = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
            if proc.returncode:
                raise RunError(f"cannot determine {binary} version: {proc.stderr.strip()}")
            versions[binary] = proc.stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RunError(f"cannot determine {binary} version: {exc}") from exc
    engine_digest = _digest({str(p.relative_to(Path(__file__).parent)): p.read_text()
                            for p in sorted(Path(__file__).parent.rglob("*.py"))})
    manifest = {"schema": 1, "engine_sha256": engine_digest,
                "runtime": {"python": sys.version, "platform": platform.platform(), "cli_versions": versions}, "engine": __version__, "tasks": task_contracts,
                "configs": config_contracts, "trials": trials, "agent_timeout": agent_timeout,
                "incumbent": bench_config.incumbent}
    manifest_path = snapshot_dir / "manifest.json"
    if manifest_path.exists():
        if json.loads(manifest_path.read_text()) != manifest:
            raise RunError("snapshot inputs changed; choose a new snapshot name")
    elif any(snapshot_dir.glob("*/*/trial-*/result.json")):
        raise RunError("legacy snapshot has no input manifest; choose a new snapshot name")
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    results: list[TrialResult] = []
    total = len(selected) * len(configs) * trials
    done = 0
    started = time.monotonic()
    cells = [(task, config, trial) for task in selected for config in configs
             for trial in range(1, trials + 1)]
    random.Random(0).shuffle(cells)  # deterministic interleaving limits order effects
    for task, config, trial in cells:
        done += 1
        out_dir = snapshot_dir / task.id / config.id / f"trial-{trial}"
        existing = out_dir / "result.json"
        if existing.exists():
            data = json.loads(existing.read_text())
            if (data.get("task_id"), data.get("config_id"), data.get("trial")) != (task.id, config.id, trial):
                raise RunError(f"cached result does not match its matrix cell: {existing}")
            results.append(TrialResult(**data))
            log(f"[{done}/{total}] {task.id} / {config.id} #{trial}: cached")
            continue
        result = run_trial(task, config, trial, out_dir, agent_timeout)
        results.append(result)
        status = "PASS" if result.passed else f"FAIL ({result.grade_reason})"
        cost = f"${result.cost_usd:.2f}" if result.cost_usd is not None else "cost n/a"
        log(f"[{done}/{total}] {task.id} / {config.id} #{trial}: {status}, {cost}")
    log(f"snapshot complete: {done} trials in {time.monotonic() - started:.0f}s")
    return results


def load_results(snapshot_dir: Path) -> list[TrialResult]:
    """Load all persisted trial results for a snapshot."""
    results = []
    for path in sorted(Path(snapshot_dir).glob("*/*/trial-*/result.json")):
        results.append(TrialResult(**json.loads(path.read_text())))
    manifest_path = Path(snapshot_dir) / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        expected = {(t["id"], c["id"], trial) for t in manifest["tasks"]
                    for c in manifest["configs"] for trial in range(1, manifest["trials"] + 1)}
        actual = {(r.task_id, r.config_id, r.trial) for r in results}
        if actual != expected or len(actual) != len(results):
            raise RunError("snapshot matrix is incomplete or contains unexpected cells; resume it before reporting")
    return results
