"""Reporting: aggregate a snapshot's trials into a markdown report and a
machine-readable routing policy.

Routing rule per category: among configs whose bucket vs the incumbent is
clearly_better or roughly_equal, recommend the one with the lowest cost per
solve (the incumbent itself competes on cost too). Categories where every
challenger is insufficient_data fall back to the incumbent.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict

import yaml

from bench.config import BenchConfig
from bench.runner import TrialResult
from bench.stats import (
    CLEARLY_BETTER,
    INSUFFICIENT_DATA,
    ROUGHLY_EQUAL,
    Comparison,
    Rate,
    compare,
)


@dataclasses.dataclass
class ConfigCategoryStats:
    config_id: str
    category: str
    rate: Rate
    total_cost_usd: float | None  # None when no trial reported a cost
    comparison: Comparison | None  # None for the incumbent itself

    @property
    def cost_per_solve(self) -> float | None:
        if self.total_cost_usd is None or self.rate.successes == 0:
            return None
        return self.total_cost_usd / self.rate.successes


ALL = "__all__"  # pseudo-category aggregating every trial


def aggregate(
    results: list[TrialResult], bench_config: BenchConfig
) -> dict[str, dict[str, ConfigCategoryStats]]:
    """-> {category: {config_id: stats}}, including the ALL pseudo-category."""
    cells: dict[tuple[str, str], list[TrialResult]] = defaultdict(list)
    for r in results:
        cells[(r.category, r.config_id)].append(r)
        cells[(ALL, r.config_id)].append(r)

    def make_rate(trials: list[TrialResult]) -> Rate:
        return Rate(successes=sum(1 for t in trials if t.passed), n=len(trials))

    def total_cost(trials: list[TrialResult]) -> float | None:
        costs = [t.cost_usd for t in trials if t.cost_usd is not None]
        return sum(costs) if costs else None

    out: dict[str, dict[str, ConfigCategoryStats]] = defaultdict(dict)
    incumbent = bench_config.incumbent
    for category in {cat for cat, _ in cells}:
        incumbent_trials = cells.get((category, incumbent), [])
        incumbent_rate = make_rate(incumbent_trials)
        for config in bench_config.configs:
            trials = cells.get((category, config.id))
            if not trials:
                continue
            rate = make_rate(trials)
            comparison = None
            if config.id != incumbent:
                comparison = compare(rate, incumbent_rate)
            out[category][config.id] = ConfigCategoryStats(
                config_id=config.id,
                category=category,
                rate=rate,
                total_cost_usd=total_cost(trials),
                comparison=comparison,
            )
    return dict(out)


def routing_policy(
    aggregated: dict[str, dict[str, ConfigCategoryStats]], bench_config: BenchConfig
) -> dict[str, dict]:
    """-> {category: {"use": config_id, "why": ..., "candidates": [...]}}"""
    incumbent = bench_config.incumbent
    policy: dict[str, dict] = {}
    for category, per_config in sorted(aggregated.items()):
        if category == ALL:
            continue
        eligible: list[ConfigCategoryStats] = []
        for stats in per_config.values():
            if stats.config_id == incumbent:
                eligible.append(stats)
            elif stats.comparison and stats.comparison.bucket in (
                CLEARLY_BETTER,
                ROUGHLY_EQUAL,
            ):
                eligible.append(stats)

        def sort_key(s: ConfigCategoryStats):
            # Cheapest cost-per-solve first; unknown cost sorts last;
            # tie-break by pass rate (higher better), then stable by id.
            cps = s.cost_per_solve
            return (cps is None, cps if cps is not None else 0.0, -s.rate.point, s.config_id)

        eligible.sort(key=sort_key)
        chosen = eligible[0] if eligible else per_config.get(incumbent)
        if chosen is None:
            continue
        n_insufficient = sum(
            1
            for s in per_config.values()
            if s.comparison and s.comparison.bucket == INSUFFICIENT_DATA
        )
        why = (
            f"cheapest config not clearly worse than incumbent "
            f"(pass {chosen.rate.successes}/{chosen.rate.n})"
        )
        if chosen.config_id == incumbent and len(eligible) == 1:
            why = "no challenger qualified; defaulting to incumbent"
        policy[category] = {
            "use": chosen.config_id,
            "why": why,
            "insufficient_data_configs": n_insufficient,
            "candidates": [
                {
                    "config": s.config_id,
                    "pass_rate": round(s.rate.point, 3),
                    "trials": s.rate.n,
                    "cost_per_solve_usd": (
                        round(s.cost_per_solve, 4) if s.cost_per_solve is not None else None
                    ),
                    "bucket": s.comparison.bucket if s.comparison else "incumbent",
                }
                for s in sorted(per_config.values(), key=sort_key)
            ],
        }
    return policy


def _fmt_ci(rate: Rate) -> str:
    lo, hi = rate.interval
    return f"{rate.point:.0%} [{lo:.0%}-{hi:.0%}]"


def render_markdown(
    aggregated: dict[str, dict[str, ConfigCategoryStats]],
    policy: dict[str, dict],
    bench_config: BenchConfig,
    snapshot: str,
) -> str:
    lines = [
        f"# Benchmark snapshot: {snapshot}",
        "",
        f"Incumbent: `{bench_config.incumbent}`. "
        "All numbers are valid within this snapshot only - do not compare "
        "across snapshots (product harnesses change between them).",
        "",
        "## Overall",
        "",
        "| Config | Pass rate (95% CI) | Trials | Total cost | Cost/solve | vs incumbent |",
        "|---|---|---|---|---|---|",
    ]
    overall = aggregated.get(ALL, {})
    for config in bench_config.configs:
        s = overall.get(config.id)
        if not s:
            continue
        bucket = s.comparison.bucket if s.comparison else "(incumbent)"
        cost = f"${s.total_cost_usd:.2f}" if s.total_cost_usd is not None else "n/a"
        cps = f"${s.cost_per_solve:.2f}" if s.cost_per_solve is not None else "n/a"
        lines.append(
            f"| `{s.config_id}` | {_fmt_ci(s.rate)} | {s.rate.n} | {cost} | {cps} | {bucket} |"
        )

    lines += ["", "## By category", ""]
    for category in sorted(aggregated):
        if category == ALL:
            continue
        lines += [
            f"### {category}",
            "",
            "| Config | Pass rate (95% CI) | Trials | Cost/solve | vs incumbent |",
            "|---|---|---|---|---|",
        ]
        for config in bench_config.configs:
            s = aggregated[category].get(config.id)
            if not s:
                continue
            bucket = s.comparison.bucket if s.comparison else "(incumbent)"
            cps = f"${s.cost_per_solve:.2f}" if s.cost_per_solve is not None else "n/a"
            lines.append(
                f"| `{s.config_id}` | {_fmt_ci(s.rate)} | {s.rate.n} | {cps} | {bucket} |"
            )
        lines.append("")

    lines += ["## Routing policy", ""]
    if policy:
        lines += ["| Category | Use | Why |", "|---|---|---|"]
        for category, entry in sorted(policy.items()):
            lines.append(f"| {category} | `{entry['use']}` | {entry['why']} |")
    else:
        lines.append("_No per-category results._")
    lines += [
        "",
        "Buckets: `clearly_better` / `roughly_equal` / `clearly_worse` vs the "
        "incumbent (Newcombe 95% CI on the pass-rate difference; deficits "
        "within the 10-point equivalence margin count as roughly equal). "
        "`insufficient_data` means too few trials to say anything.",
        "",
    ]
    return "\n".join(lines)


def render_routing_yaml(policy: dict[str, dict], snapshot: str) -> str:
    return yaml.safe_dump(
        {"snapshot": snapshot, "routing": policy}, sort_keys=True, default_flow_style=False
    )
