"""A small decision report for a person's own tasks, without automatic routing."""
from __future__ import annotations

from collections import defaultdict
import math
from statistics import median

from bench.config import BenchConfig
from bench.runner import RunError, TrialResult


def summarize(results: list[TrialResult], config: BenchConfig, must_pass: list[str]) -> dict:
    by_setup = defaultdict(list)
    for result in results:
        by_setup[result.config_id].append(result)
    if len(by_setup) < 2 or config.incumbent not in by_setup:
        raise RunError("compare needs your current setup and at least one alternative")
    expected = {(r.task_id, r.trial) for r in by_setup[config.incumbent]}
    task_ids = sorted({task for task, _ in expected})
    if set(must_pass) - set(task_ids):
        raise RunError("must-pass tasks are missing from the comparison")
    rows = []
    for setup in config.configs:
        attempts = by_setup.get(setup.id, [])
        if not attempts:
            continue
        if {(r.task_id, r.trial) for r in attempts} != expected or len(attempts) != len(expected):
            raise RunError("compare requires the same task/trial cells for every setup")
        by_task = defaultdict(list)
        for result in attempts:
            by_task[result.task_id].append(result)
        passed_tasks = sorted(task for task, values in by_task.items() if all(r.passed for r in values))
        costs = [r.cost_usd for r in attempts]
        complete_cost = all(c is not None and math.isfinite(c) and c >= 0 for c in costs)
        total = sum(costs) if complete_cost else None
        successes = sum(r.passed for r in attempts)
        rows.append({
            "id": setup.id, "harness": setup.harness, "model": setup.model,
            "tasks_passed": len(passed_tasks), "task_count": len(task_ids),
            "passed_task_ids": passed_tasks,
            "attempts_passed": successes, "attempt_count": len(attempts),
            "total_cost_usd": total,
            "cost_per_success_usd": total / successes if total is not None and successes else None,
            "cost_sources": sorted({r.cost_source for r in attempts}),
            "median_seconds": median(r.agent_duration_seconds for r in attempts),
            "must_pass_failures": sorted(set(must_pass) - set(passed_tasks)),
            "needs_review": any(r.agent_exit_code is None or r.grade_reason not in (
                "tests_passed", "tests_failed", "agent_timed_out", "agent_exited_nonzero"
            ) or r.artifact_grade_reason not in (None, "tests_passed", "tests_failed")
                or any(c["reason"] not in ("tests_passed", "tests_failed") for c in r.check_results)
                for r in attempts),
        })
    if len(rows) != len(by_setup):
        raise RunError("a result references a setup missing from the configuration")
    current = next(row for row in rows if row["id"] == config.incumbent)
    for row in rows:
        row["meets_bar"] = (row["tasks_passed"] >= current["tasks_passed"]
                            and row["tasks_passed"] > 0 and not row["must_pass_failures"])
    eligible = [row for row in rows if row["meets_bar"]]
    pick = None
    if any(row["needs_review"] for row in rows):
        reason = "Resolve grading problems or unknown execution outcomes before choosing a setup."
    elif not eligible:
        reason = "No setup meets the quality bar. Inspect the failed tasks before expanding the benchmark."
    elif any(row["cost_per_success_usd"] is None or "unknown" in row["cost_sources"] for row in eligible):
        reason = "Cost information is incomplete for a setup meeting the quality bar; no cost pick is available."
    else:
        chosen = min(eligible, key=lambda row: (row["cost_per_success_usd"],
                                                row["id"] != config.incumbent, row["id"]))
        pick = chosen["id"]
        reason = (f"{pick} has the lowest observed cost per successful attempt among setups meeting the bar. "
                  "Inspect the failed tasks before switching; this sample does not establish equivalence.")
    return {"schema": 1, "current": config.incumbent, "task_count": len(task_ids),
            "must_pass": sorted(must_pass), "minimum_tasks_passed": current["tasks_passed"],
            "setups": rows, "observed_cost_pick": pick, "reason": reason}


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _money(value) -> str:
    return "unknown" if value is None else f"${value:.4f}"


def render(summary: dict, results: list[TrialResult], snapshot: str) -> str:
    lines = [f"# My benchmark: {_cell(snapshot)}", "",
             f"Current setup: **{summary['current']}**. {summary['task_count']} task(s).", "",
             "Quality bar: pass every must-pass task and at least as many tasks as your current setup. "
             "A task counts as passed only when every attempt succeeds. At least one task must pass.", "",
             "Must-pass tasks: " + (", ".join(summary["must_pass"]) or "none selected") + ".", "",
             "| Setup | Tasks passed | Attempts passed | Total cost | Cost / success | Median time |",
             "|---|---|---|---|---|---|"]
    sources = {"harness_reported": "reported usage", "token_estimate": "token estimate",
               "flat_estimate": "flat estimate", "unknown": "unknown"}
    for row in summary["setups"]:
        lines.append(f"| {row['id']} | {row['tasks_passed']}/{row['task_count']} | "
                     f"{row['attempts_passed']}/{row['attempt_count']} | {_money(row['total_cost_usd'])} | "
                     f"{_money(row['cost_per_success_usd'])} | {row['median_seconds']:.1f}s |")
    eligible = ", ".join(row["id"] for row in summary["setups"] if row["meets_bar"]) or "none"
    lines += ["", f"Meets the quality bar: **{eligible}**.", "", summary["reason"], "",
              "Costs include failed attempts. Reported usage costs are not invoices; token and flat costs "
              "are estimates. Compare the same cost basis across setups. Any missing amount makes total "
              "cost unknown. Time measures the agent run, including failed attempts.", "",
              "## Which tasks failed?", "",
              "Inspect different failures even when two setups have the same score. "
              "Each link opens the saved evidence for that attempt.", "",
              "| Task | Setup | Attempt | Outcome | Evidence |",
              "|---|---|---|---|---|"]
    for result in sorted(results, key=lambda r: (r.task_id, r.config_id, r.trial)):
        if result.passed:
            continue
        base = f"{result.task_id}/{result.config_id}/trial-{result.trial}"
        failed = [f"{c['id']}: {c['reason']}" for c in result.check_results if not c["passed"]]
        outcome = result.grade_reason + ("; " + ", ".join(failed) if failed else "")
        if result.artifact_grade_reason not in (None, "tests_passed", result.grade_reason):
            outcome += f"; artifact: {result.artifact_grade_reason}"
        lines.append(f"| {result.task_id} | {result.config_id} | {result.trial} | {_cell(outcome)} | "
                     f"[checks]({base}/tests.log) · [patch]({base}/diff.patch) · [agent]({base}/agent.log) |")
    if all(r.passed for r in results):
        lines += ["", "No failed attempts in this sample."]
    lines += ["", "## Setups compared", "", "| Setup | Harness | Model | Cost source |", "|---|---|---|---|"]
    for row in summary["setups"]:
        basis = ", ".join(sources.get(s, "unknown") for s in row["cost_sources"])
        lines.append(f"| {row['id']} | {_cell(row['harness'])} | {_cell(row['model'] or 'default')} | {basis} |")
    lines += ["", "Use the same tasks to compare models, harnesses, tools or effort. Change one setting "
              "at a time when you want to understand its effect. [Frozen run details](manifest.json).", "",
              "This is an observed comparison on your chosen tasks, not an automatic routing policy or "
              "proof of a general winner. Start with 5–10 representative tasks. Repeat a promising pilot "
              "with `--trials 3` and a new snapshot name; include fresh tasks before relying on the result.", ""]
    return "\n".join(lines)
