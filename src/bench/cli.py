"""Command-line entry point.

Typical lifecycle::

    bench mine transcripts ~/.claude/projects --source claude --mode interactive
    bench mine transcripts ~/.codex/sessions --source codex --mode interactive
                                                    # learn your task mix
    bench mine commits ~/code/myrepo               # find candidate commits
    bench mine scaffold ~/code/myrepo <sha> tasks/fix-foo
    # ... hand-edit prompt.md, task.yaml (test command, image) ...
    bench validate                                 # tasks are well-formed
    bench smoke                                    # tasks detect pass AND fail
    bench run --snapshot 2026-07-sonnet5-launch    # the expensive part
    bench report --snapshot 2026-07-sonnet5-launch # report.md + routing.yaml
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
from pathlib import Path

from bench import __version__
from bench import config as config_mod
from bench import harness as harness_mod
from bench import preference as preference_mod
from bench import report as report_mod
from bench import runner as runner_mod
from bench import smoke as smoke_mod
from bench import task as task_mod
from bench import workspace as workspace_mod
from bench.mine import git_history, transcripts


def _load_tasks(tasks_dir: str) -> list[task_mod.Task]:
    return task_mod.load_all(Path(tasks_dir))


def _select_tasks(
    tasks: list[task_mod.Task], requested_ids: list[str] | None
) -> list[task_mod.Task]:
    if not requested_ids:
        return tasks
    available_ids = {task.id for task in tasks}
    unknown = sorted(set(requested_ids) - available_ids)
    if unknown:
        available = ", ".join(sorted(available_ids))
        raise task_mod.TaskError(
            f"unknown task id(s): {', '.join(unknown)}; available: {available}"
        )
    requested = set(requested_ids)
    return [task for task in tasks if task.id in requested]


def _select_configs(
    bench_config: config_mod.BenchConfig, requested_ids: list[str] | None
) -> list[config_mod.ProductConfig]:
    if not requested_ids:
        return bench_config.configs
    available_ids = {config.id for config in bench_config.configs}
    unknown = sorted(set(requested_ids) - available_ids)
    if unknown:
        available = ", ".join(sorted(available_ids))
        raise config_mod.ConfigError(
            f"unknown config id(s): {', '.join(unknown)}; available: {available}"
        )
    requested = set(requested_ids)
    return [config for config in bench_config.configs if config.id in requested]


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def cmd_validate(args) -> int:
    try:
        tasks = _load_tasks(args.tasks)
    except task_mod.TaskError as e:
        print(f"INVALID: {e}", file=sys.stderr)
        return 1
    for t in tasks:
        print(
            f"ok  {t.id}  (category={t.category}, grader={t.grader_type}, "
            f"runner={t.runner})"
        )
    print(f"{len(tasks)} task(s) valid")
    return 0


def cmd_smoke(args) -> int:
    tasks = _select_tasks(_load_tasks(args.tasks), args.task)
    failures = 0
    for result in smoke_mod.smoke_all(tasks):
        status = "ok " if result.ok else "GATE FAILED"
        print(f"{status}  {result.task_id}")
        if not result.ok:
            failures += 1
            print(f"    {result.detail}")
    if failures:
        print(
            f"\n{failures} task(s) failed the smoke gate - quarantine them "
            "before running a snapshot.",
            file=sys.stderr,
        )
        return 1
    print(f"\nall {len(tasks)} task(s) passed the smoke gate")
    return 0


def cmd_run(args) -> int:
    tasks = _select_tasks(_load_tasks(args.tasks), args.task)
    bench_config = config_mod.load(Path(args.configs))
    _select_configs(bench_config, args.config)
    snapshot_dir = Path(args.runs) / args.snapshot
    if not args.skip_smoke:
        bad = [r for r in smoke_mod.smoke_all(tasks) if not r.ok]
        if bad:
            for r in bad:
                print(f"GATE FAILED  {r.task_id}\n    {r.detail}", file=sys.stderr)
            print(
                "\nrefusing to run: fix or quarantine these tasks first "
                "(or pass --skip-smoke if you really know better)",
                file=sys.stderr,
            )
            return 1
    runner_mod.run_matrix(
        tasks,
        bench_config,
        snapshot_dir,
        trials=args.trials,
        config_ids=args.config or None,
        task_ids=None,
        agent_timeout=args.agent_timeout,
    )
    if all(task.grader_type == "preference" for task in tasks):
        next_step = f"bench preference prepare --snapshot {args.snapshot} --config ... --config ..."
    elif any(task.grader_type == "preference" for task in tasks):
        next_step = (
            f"bench report --snapshot {args.snapshot}, then prepare preference review"
        )
    else:
        next_step = f"bench report --snapshot {args.snapshot}"
    print(f"\nresults in {snapshot_dir}; next: {next_step}")
    return 0


def cmd_preference_prepare(args) -> int:
    tasks = _load_tasks(args.tasks)
    bench_config = config_mod.load(Path(args.configs))
    _select_configs(bench_config, args.config)
    snapshot_dir = Path(args.runs) / args.snapshot
    results = runner_mod.load_results(snapshot_dir)
    if not results:
        print(f"no results found under {snapshot_dir}", file=sys.stderr)
        return 1
    count = preference_mod.prepare_review(
        tasks, results, snapshot_dir, args.config
    )
    review_dir = snapshot_dir / "preference-review"
    print(f"prepared {count} blinded pair(s) in {review_dir}")
    print("complete each judgment.yaml, then run preference report")
    return 0


def cmd_preference_report(args) -> int:
    snapshot_dir = Path(args.runs) / args.snapshot
    results = runner_mod.load_results(snapshot_dir)
    if not results:
        print(f"no results found under {snapshot_dir}", file=sys.stderr)
        return 1
    data = preference_mod.build_report(snapshot_dir, results, args.snapshot)
    markdown = preference_mod.render_markdown(data)
    (snapshot_dir / "preference-report.md").write_text(markdown)
    (snapshot_dir / "preference-results.yaml").write_text(
        preference_mod.render_yaml(data)
    )
    print(markdown)
    print(
        f"\nwrote {snapshot_dir / 'preference-report.md'} and "
        f"{snapshot_dir / 'preference-results.yaml'}"
    )
    return 0


def cmd_report(args) -> int:
    bench_config = config_mod.load(Path(args.configs))
    snapshot_dir = Path(args.runs) / args.snapshot
    results = runner_mod.load_results(snapshot_dir)
    if not results:
        print(f"no results found under {snapshot_dir}", file=sys.stderr)
        return 1
    aggregated = report_mod.aggregate(results, bench_config)
    policy = report_mod.routing_policy(aggregated, bench_config)
    markdown = report_mod.render_markdown(aggregated, policy, bench_config, args.snapshot)
    (snapshot_dir / "report.md").write_text(markdown)
    (snapshot_dir / "routing.yaml").write_text(
        report_mod.render_routing_yaml(policy, args.snapshot)
    )
    print(markdown)
    print(f"\nwrote {snapshot_dir / 'report.md'} and {snapshot_dir / 'routing.yaml'}")
    return 0


def cmd_doctor(args) -> int:
    """Check the local prerequisites needed by a selected benchmark matrix."""
    tasks = _select_tasks(_load_tasks(args.tasks), args.task)
    bench_config = config_mod.load(Path(args.configs))
    configs = _select_configs(bench_config, args.config)
    failures: list[str] = []

    def executable(label: str, name: str) -> None:
        path = shutil.which(name)
        if path:
            print(f"ok    {label}: {path}")
        else:
            failures.append(f"{label}: executable {name!r} was not found on PATH")
            print(f"ERROR {failures[-1]}")

    print(f"ok    Python {platform.python_version()} (requires 3.10+)")
    executable("Git", "git")
    print(f"ok    tasks: {len(tasks)} selected from {args.tasks}")
    print(f"ok    configs: {len(configs)} selected from {args.configs}")

    if any(task.runner == "docker" for task in tasks):
        executable("Docker", "docker")

    cli_names = {
        "claude-code": "claude",
        "codex": "codex",
        "cursor": "cursor-agent",
    }
    checked: set[str] = set()
    for config in configs:
        try:
            harness_mod.get(config.harness)
        except harness_mod.HarnessError as exc:
            failures.append(f"config {config.id}: {exc}")
            print(f"ERROR {failures[-1]}")
            continue
        cli_name = cli_names.get(config.harness)
        if cli_name and cli_name not in checked:
            executable(f"{config.harness} harness", cli_name)
            checked.add(cli_name)
        if config.harness == "script" and config.patch_file:
            patch_path = Path(config.patch_file)
            if not patch_path.is_file():
                failures.append(
                    f"config {config.id}: patch file not found: {config.patch_file}"
                )
                print(f"ERROR {failures[-1]}")

    if failures:
        print(f"\nnot ready: {len(failures)} prerequisite check(s) failed", file=sys.stderr)
        return 1
    print("\nready to run")
    return 0


def cmd_mine_commits(args) -> int:
    candidates = git_history.find_candidates(Path(args.repo), limit=args.limit)
    if not candidates:
        print("no candidate commits found (need commits touching both source and tests)")
        return 0
    for c in candidates:
        print(f"{c.sha[:12]}  {c.subject}")
        print(f"              source: {len(c.source_files)} file(s), tests: {len(c.test_files)} file(s)")
    print(
        f"\n{len(candidates)} candidate(s). Scaffold one with:\n"
        f"  bench mine scaffold {args.repo} <sha> tasks/<task-id>"
    )
    return 0


def cmd_mine_scaffold(args) -> int:
    out = git_history.scaffold(
        Path(args.repo), args.commit, Path(args.out), category=args.category
    )
    print(f"scaffolded {out}")
    print(
        "now finish it by hand:\n"
        f"  1. rewrite {out / 'prompt.md'} as a real task description (remove the TODO)\n"
        f"  2. set the test command and docker image in {out / 'task.yaml'}\n"
        f"  3. bench validate && bench smoke --task {out.name}"
    )
    return 0


def cmd_mine_transcripts(args) -> int:
    session_items = transcripts.iter_sessions(
        Path(args.dir),
        source=None if args.source == "all" else args.source,
        mode=None if args.mode == "all" else args.mode,
    )
    sessions = list(session_items) if args.output else session_items
    result = transcripts.summarize_sessions(sessions)
    if result.sessions == 0:
        print(f"no parseable sessions found under {args.dir}", file=sys.stderr)
        return 1
    print(result.render())
    if args.output:
        output = Path(args.output).expanduser()
        count = transcripts.write_sessions_jsonl(sessions, output)
        noun = "session" if count == 1 else "sessions"
        print(f"\nWrote {count} cleaned {noun} to {output}")
        print(
            "Warning: the export contains private transcript content; keep it local.",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bench",
        description="Private coding-agent benchmarks for individuals and teams",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--tasks", default="tasks", help="tasks directory (default: tasks)")
    parser.add_argument(
        "--configs", default="configs/products.yaml", help="product configs file"
    )
    parser.add_argument("--runs", default="runs", help="runs output directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("doctor", help="check tasks, configs, and required local tools")
    p.add_argument("--config", action="append", help="check only this config id (repeatable)")
    p.add_argument("--task", action="append", help="check only this task id (repeatable)")

    sub.add_parser("validate", help="check every task directory is well-formed")

    p = sub.add_parser("smoke", help="verify tasks detect both success and failure")
    p.add_argument("--task", action="append", help="limit to task id (repeatable)")

    p = sub.add_parser("run", help="run the task x config x trial matrix")
    p.add_argument("--snapshot", required=True, help="snapshot name, e.g. 2026-07-sonnet5")
    p.add_argument("--trials", type=_positive_int, default=3)
    p.add_argument("--config", action="append", help="limit to config id (repeatable)")
    p.add_argument("--task", action="append", help="limit to task id (repeatable)")
    p.add_argument(
        "--agent-timeout", type=_positive_int, default=runner_mod.DEFAULT_AGENT_TIMEOUT
    )
    p.add_argument("--skip-smoke", action="store_true", help="skip the pre-run smoke gate")

    p = sub.add_parser("report", help="aggregate a snapshot into report.md + routing.yaml")
    p.add_argument("--snapshot", required=True)

    p = sub.add_parser(
        "preference", help="prepare and report blinded pairwise preference reviews"
    )
    preference_sub = p.add_subparsers(dest="preference_command", required=True)
    q = preference_sub.add_parser("prepare", help="create blinded A/B review packets")
    q.add_argument("--snapshot", required=True)
    q.add_argument(
        "--config",
        action="append",
        required=True,
        help="one of exactly two configs to compare (repeat twice)",
    )
    q = preference_sub.add_parser("report", help="aggregate completed judgments")
    q.add_argument("--snapshot", required=True)

    p = sub.add_parser("mine", help="mine tasks and task distribution from your history")
    mine_sub = p.add_subparsers(dest="mine_command", required=True)
    q = mine_sub.add_parser("commits", help="list candidate commits in a repo")
    q.add_argument("repo")
    q.add_argument("--limit", type=int, default=200)
    q = mine_sub.add_parser("scaffold", help="scaffold a task directory from a commit")
    q.add_argument("repo")
    q.add_argument("commit")
    q.add_argument("out", help="task directory to create, e.g. tasks/fix-date-parse")
    q.add_argument("--category", default="bugfix")
    q = mine_sub.add_parser("transcripts", help="survey session transcripts by category")
    q.add_argument("dir", help="e.g. ~/.claude/projects")
    q.add_argument(
        "--source",
        choices=("all", *transcripts.SOURCES),
        default="all",
        help="include only this transcript source (default: all)",
    )
    q.add_argument(
        "--mode",
        choices=("all", *transcripts.MODES),
        default="all",
        help="include only this session mode (default: all)",
    )
    q.add_argument(
        "--output",
        help="write cleaned sessions as private JSONL for local review",
    )

    args = parser.parse_args(argv)
    handlers = {
        "doctor": cmd_doctor,
        "validate": cmd_validate,
        "smoke": cmd_smoke,
        "run": cmd_run,
        "report": cmd_report,
    }
    if args.command == "mine":
        handlers = {
            "commits": cmd_mine_commits,
            "scaffold": cmd_mine_scaffold,
            "transcripts": cmd_mine_transcripts,
        }
        handler = handlers[args.mine_command]
    elif args.command == "preference":
        handlers = {
            "prepare": cmd_preference_prepare,
            "report": cmd_preference_report,
        }
        handler = handlers[args.preference_command]
    else:
        handler = handlers[args.command]

    try:
        return handler(args)
    except (
        config_mod.ConfigError,
        git_history.MineError,
        harness_mod.HarnessError,
        preference_mod.PreferenceError,
        runner_mod.RunError,
        task_mod.TaskError,
        workspace_mod.GitError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
