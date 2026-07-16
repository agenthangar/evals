"""Blinded, manual pairwise review for subjective preference tasks.

Preference results are intentionally separate from objective pass/fail grading.
The framework captures model artifacts, prepares anonymous A/B packets, and
aggregates human judgments without pretending that taste is a test result.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import yaml

from bench.runner import TrialResult
from bench.task import Task


class PreferenceError(Exception):
    """Raised when preference review inputs or judgments are invalid."""


_PACKET_FILES = {
    "prompt": "prompt.md",
    "rubric": "rubric.md",
    "candidate-a": "candidate-a.md",
    "candidate-b": "candidate-b.md",
}


def _pair_key(task_id: str, trial: int) -> str:
    return f"{task_id}-trial-{trial}.json"


def _content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _packet_hashes(packet: dict[str, str]) -> dict[str, str]:
    return {name: _content_sha256(packet[name]) for name in _PACKET_FILES}


def _packet_hashes_from_dir(review_dir: Path) -> dict[str, str] | None:
    """Hash a visible review packet, or return None when it is incomplete."""
    packet = {}
    for name, filename in _PACKET_FILES.items():
        path = review_dir / filename
        if not path.is_file():
            return None
        packet[name] = path.read_text(encoding="utf-8", errors="replace")
    return _packet_hashes(packet)


def _completed_judgment(judgment_path: Path) -> bool:
    if not judgment_path.exists():
        return False
    try:
        raw = yaml.safe_load(judgment_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise PreferenceError(f"{judgment_path}: invalid YAML: {exc}") from exc
    return isinstance(raw, dict) and raw.get("winner") is not None


def prepare_review(
    tasks: list[Task],
    results: list[TrialResult],
    snapshot_dir: Path,
    config_ids: list[str],
) -> int:
    """Create deterministic, blinded A/B packets for complete preference pairs."""
    if len(config_ids) != 2 or len(set(config_ids)) != 2:
        raise PreferenceError("preference review requires exactly two distinct configs")
    config_ids = sorted(config_ids)
    snapshot_dir = Path(snapshot_dir)
    task_map = {task.id: task for task in tasks if task.grader_type == "preference"}
    selected = set(config_ids)
    cells: dict[tuple[str, int], dict[str, TrialResult]] = defaultdict(dict)
    for result in results:
        if (
            result.grader_type == "preference"
            and result.config_id in selected
            and result.grade_reason == "preference_ready"
            and result.artifact_file
            and result.task_id in task_map
        ):
            cells[(result.task_id, result.trial)][result.config_id] = result

    review_root = snapshot_dir / "preference-review"
    keys_root = review_root / ".keys"
    keys_root.mkdir(parents=True, exist_ok=True)
    manifest_path = keys_root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("configs") != config_ids:
            raise PreferenceError(
                "preference review was already prepared for a different config pair"
            )
    else:
        manifest_path.write_text(json.dumps({"configs": config_ids}, indent=2) + "\n")
    (review_root / "README.md").write_text(
        "# Blinded preference review\n\n"
        "For each task, read `prompt.md` and `rubric.md`, compare candidates A and B, "
        "then set `winner` in `judgment.yaml` to `A`, `B`, `tie`, or `neither`. "
        "Do not inspect `.keys` until review is complete.\n"
    )

    prepared = 0
    for (task_id, trial), per_config in sorted(cells.items()):
        if set(per_config) != selected:
            continue
        task = task_map[task_id]
        digest = hashlib.sha256(
            f"{snapshot_dir.name}:{task_id}:{trial}".encode()
        ).digest()
        ordered = list(config_ids)
        if digest[0] % 2:
            ordered.reverse()
        labels = {"A": ordered[0], "B": ordered[1]}
        review_dir = review_root / task_id / f"trial-{trial}"
        review_dir.mkdir(parents=True, exist_ok=True)
        packet = {
            "prompt": task.prompt,
            "rubric": task.preference_rubric or "",
        }
        for label, filename in (("A", "candidate-a.md"), ("B", "candidate-b.md")):
            result = per_config[labels[label]]
            artifact = (
                snapshot_dir
                / task_id
                / result.config_id
                / f"trial-{trial}"
                / str(result.artifact_file)
            )
            if not artifact.is_file():
                raise PreferenceError(f"missing captured artifact: {artifact}")
            packet[f"candidate-{label.lower()}"] = artifact.read_text(
                encoding="utf-8", errors="replace"
            )
        judgment = review_dir / "judgment.yaml"
        key_path = keys_root / _pair_key(task_id, trial)
        content_sha256 = _packet_hashes(packet)
        if _completed_judgment(judgment):
            existing_sha256 = _packet_hashes_from_dir(review_dir)
            previous_key = {}
            if key_path.is_file():
                try:
                    previous_key = json.loads(key_path.read_text())
                except (json.JSONDecodeError, OSError) as exc:
                    raise PreferenceError(f"invalid blinded review key: {key_path}") from exc
            previous_sha256 = previous_key.get("content_sha256")
            packet_changed = (
                existing_sha256 != content_sha256
                if previous_sha256 is None
                else (
                    previous_key.get("labels") != labels
                    or existing_sha256 != previous_sha256
                    or content_sha256 != previous_sha256
                )
            )
            if packet_changed:
                raise PreferenceError(
                    f"{judgment}: completed judgment cannot be reused because "
                    "the review packet changed"
                )

        for name, filename in _PACKET_FILES.items():
            (review_dir / filename).write_text(packet[name])
        if not judgment.exists():
            judgment.write_text(yaml.safe_dump({"winner": None, "rationale": ""}))
        key_path.write_text(
            json.dumps(
                {
                    "task_id": task_id,
                    "trial": trial,
                    "labels": labels,
                    "content_sha256": content_sha256,
                },
                indent=2,
            )
            + "\n"
        )
        prepared += 1

    if prepared == 0:
        raise PreferenceError("no complete preference pairs were ready for review")
    return prepared


def build_report(
    snapshot_dir: Path, results: list[TrialResult], snapshot: str
) -> dict:
    """Resolve completed blinded judgments and aggregate wins separately."""
    snapshot_dir = Path(snapshot_dir)
    review_root = snapshot_dir / "preference-review"
    keys_root = review_root / ".keys"
    if not keys_root.is_dir():
        raise PreferenceError("preference review has not been prepared")

    summary: dict[str, dict] = {}
    judgments: list[dict] = []
    reviewed_cells: set[tuple[str, str, int]] = set()
    pending = 0
    for judgment_path in sorted(review_root.glob("*/trial-*/judgment.yaml")):
        task_id = judgment_path.parent.parent.name
        try:
            trial = int(judgment_path.parent.name.removeprefix("trial-"))
        except ValueError as exc:
            raise PreferenceError(f"invalid review path: {judgment_path}") from exc
        key_path = keys_root / _pair_key(task_id, trial)
        if not key_path.is_file():
            raise PreferenceError(f"missing blinded review key: {key_path}")
        key = json.loads(key_path.read_text())
        labels = key.get("labels") or {}
        if set(labels) != {"A", "B"}:
            raise PreferenceError(f"invalid blinded review key: {key_path}")
        expected_sha256 = key.get("content_sha256")
        if expected_sha256 is not None:
            actual_sha256 = _packet_hashes_from_dir(judgment_path.parent)
            if actual_sha256 != expected_sha256:
                raise PreferenceError(
                    f"{judgment_path.parent}: review packet changed after preparation"
                )
        for config_id in labels.values():
            reviewed_cells.add((task_id, config_id, trial))
            summary.setdefault(
                config_id,
                {
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "neither": 0,
                    "preference_share": None,
                    "total_cost_usd": None,
                },
            )

        raw = yaml.safe_load(judgment_path.read_text()) or {}
        if not isinstance(raw, dict):
            raise PreferenceError(f"{judgment_path}: expected a mapping")
        winner = raw.get("winner")
        rationale = str(raw.get("rationale") or "").strip()
        if winner is None:
            pending += 1
            judgments.append(
                {
                    "task_id": task_id,
                    "trial": trial,
                    "winner": None,
                    "winner_config": None,
                    "rationale": rationale,
                }
            )
            continue
        if winner not in ("A", "B", "tie", "neither"):
            raise PreferenceError(
                f"{judgment_path}: winner must be A, B, tie, neither, or null"
            )
        winner_config = None
        a_config = labels["A"]
        b_config = labels["B"]
        if winner in ("A", "B"):
            winner_config = labels[winner]
            loser_config = b_config if winner == "A" else a_config
            summary[winner_config]["wins"] += 1
            summary[loser_config]["losses"] += 1
        elif winner == "tie":
            summary[a_config]["ties"] += 1
            summary[b_config]["ties"] += 1
        else:
            summary[a_config]["neither"] += 1
            summary[b_config]["neither"] += 1
        judgments.append(
            {
                "task_id": task_id,
                "trial": trial,
                "winner": winner,
                "winner_config": winner_config,
                "rationale": rationale,
            }
        )

    if not judgments:
        raise PreferenceError("no preference judgments found")

    result_by_cell = {
        (result.task_id, result.config_id, result.trial): result
        for result in results
        if result.grader_type == "preference"
    }
    missing_cells = reviewed_cells - set(result_by_cell)
    if missing_cells:
        task_id, config_id, trial = sorted(missing_cells)[0]
        raise PreferenceError(
            "missing result for reviewed preference pair: "
            f"{task_id} / {config_id} / trial-{trial}"
        )

    for config_id, stats in summary.items():
        decided = stats["wins"] + stats["losses"] + stats["ties"]
        if decided:
            stats["preference_share"] = round(
                (stats["wins"] + 0.5 * stats["ties"]) / decided, 3
            )
        costs = [
            result_by_cell[cell].cost_usd
            for cell in sorted(reviewed_cells)
            if cell[1] == config_id and result_by_cell[cell].cost_usd is not None
        ]
        if costs:
            stats["total_cost_usd"] = round(sum(costs), 6)

    return {
        "snapshot": snapshot,
        "track": "preference",
        "review_method": "blinded_pairwise_manual",
        "pending": pending,
        "summary": dict(sorted(summary.items())),
        "judgments": judgments,
    }


def render_markdown(data: dict) -> str:
    """Render a preference-only report; never combine it with pass rates."""
    lines = [
        f"# Blinded pairwise preference: {data['snapshot']}",
        "",
        "These are manual A/B judgments of valid artifacts. They are separate "
        "from objective correctness and should not be read as pass rates.",
        "",
        "## Overall",
        "",
        "| Config | Wins | Losses | Ties | Neither | Preference share | Total cost |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for config_id, stats in data["summary"].items():
        share = (
            f"{stats['preference_share']:.0%}"
            if stats["preference_share"] is not None
            else "n/a"
        )
        cost = (
            f"${stats['total_cost_usd']:.4f}"
            if stats["total_cost_usd"] is not None
            else "n/a"
        )
        lines.append(
            f"| `{config_id}` | {stats['wins']} | {stats['losses']} | "
            f"{stats['ties']} | {stats['neither']} | {share} | {cost} |"
        )
    lines += ["", "## By task", "", "| Task | Trial | Result | Rationale |", "|---|---:|---|---|"]
    for judgment in data["judgments"]:
        if judgment["winner_config"]:
            result = f"`{judgment['winner_config']}`"
        elif judgment["winner"]:
            result = judgment["winner"]
        else:
            result = "pending"
        rationale = judgment["rationale"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| `{judgment['task_id']}` | {judgment['trial']} | {result} | {rationale} |"
        )
    lines += ["", f"Pending judgments: {data['pending']}", ""]
    return "\n".join(lines)


def render_yaml(data: dict) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
