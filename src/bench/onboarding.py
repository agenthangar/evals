"""The short path from past work to a private, runnable task pack."""
from __future__ import annotations

import math
import re
import shlex
import sys
import tempfile
from pathlib import Path

import yaml

from bench import config, patches, smoke
from bench.mine import git_history
from bench.task import Task


class SetupError(Exception):
    pass


def ask(value, label: str, flag: str, default: str | None = None) -> str:
    if value is not None:
        return str(value).strip()
    if not sys.stdin.isatty():
        if default is not None:
            return default
        raise SetupError(f"provide {flag}, or run in a terminal for guided input")
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{label}{suffix}: ").strip() or default
        if answer is not None:
            return answer
        print("Please enter a value.")


def identifier(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", value):
        raise SetupError("use a name containing letters, numbers, hyphens or underscores")
    return value


def init_pack(args) -> int:
    root = Path(args.directory).expanduser().resolve()
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        raise SetupError("choose a new or empty directory for your private benchmark")
    root.mkdir(parents=True, exist_ok=True)
    (root / "tasks").mkdir()
    (root / "configs").mkdir()
    (root / ".gitignore").write_text("runs/\n.cache/\n.venv/\n")
    (root / "README.md").write_text(
        "# My benchmark\n\n"
        "Keep this directory private: tasks contain source patches and solutions.\n\n"
        "1. `bench add /path/to/repo` — choose past work and describe the request.\n"
        "2. `bench setup` — add your current setup first, then an alternative.\n"
        "3. `bench compare --snapshot first` — run and inspect the comparison.\n\n"
        "Start with 5–10 representative tasks. Each task has a starting revision,\n"
        "a prompt, and executable checks. The historical fix must pass and the\n"
        "starting state must fail. Review checks for missing requirements.\n\n"
        "Task creation and comparison execute your test commands in fresh local\n"
        "checkouts. Install their dependencies or include setup in the command.\n"
        "Agents run unattended with your user permissions. Keep credentials and\n"
        "unrelated data out of the environment; separate agent isolation is needed\n"
        "to enforce held-out secrecy.\n\n"
        "Edit `prompt.md` or `task.yaml` to refine a task. Set `must_pass: true`\n"
        "for work an alternative must solve before you would switch.\n"
        "Edit `configs/products.yaml` for models, tools, effort and pricing.\n"
        "Use the same cost basis across setups; reported usage cost is not an invoice.\n\n"
        "Reports and failure evidence live in `runs/<snapshot>/comparison.md`.\n"
        "Use a new snapshot name after changing tasks, setups or trial counts.\n"
        "Repeat with `--trials 3` before relying on a promising pilot result.\n"
    )
    print(f"Created private benchmark at {root}\n\n"
          f"  cd {shlex.quote(str(root))}\n"
          "  bench add /path/to/repo\n"
          "  bench setup\n"
          "  bench setup\n"
          "  bench compare --snapshot first")
    return 0


def _prompt(path: str | None) -> str:
    if path:
        return Path(path).expanduser().read_text()
    if not sys.stdin.isatty():
        raise SetupError("provide --prompt-file, or run in a terminal to describe the task")
    print("What needed doing? Describe the request and expected behavior, without the fix.\n"
          "Enter multiple lines; finish with an empty line.")
    lines = []
    while True:
        line = input("> ")
        if not line.strip():
            if lines:
                return "\n".join(lines) + "\n"
            print("Enter the task description first.")
        else:
            lines.append(line)


def add_task(args) -> int:
    repo = Path(args.repo).expanduser().resolve()
    commit = args.commit
    if not commit:
        history = git_history._git(repo, ["log", "-100", "--no-merges", "--format=%H %P"])
        replayable = {line.split()[0] for line in history.splitlines() if len(line.split()) == 2}
        candidates = git_history.find_candidates(repo, limit=100, max_source_files=10000,
                                                 include_untested=True)
        candidates = [candidate for candidate in candidates if candidate.sha in replayable][:20]
        if not candidates:
            raise SetupError("no recent source changes with a starting revision found; pass a specific fix commit")
        print("Choose work representative of what you delegate:")
        for index, candidate in enumerate(candidates, 1):
            note = "tests changed" if candidate.test_files else "needs a test patch"
            print(f"  {index}. {candidate.sha[:10]} {candidate.subject} ({note})")
        choice = ask(None, "Commit number or hash", "a commit argument")
        if choice.isdigit():
            if not 1 <= int(choice) <= len(candidates):
                raise SetupError("choose a number from the list or pass a commit hash")
            commit = candidates[int(choice) - 1].sha
        else:
            commit = choice
    sha = git_history._git(repo, ["rev-parse", "--verify", f"{commit}^{{commit}}"]).strip()
    parents = git_history._git(repo, ["rev-list", "--parents", "-n", "1", sha]).split()
    if len(parents) != 2:
        raise SetupError("choose a non-merge commit with a parent; split a larger change into a task manually")
    parent = parents[1]
    full_diff = git_history._git(repo, ["diff", "--binary", parent, sha])
    tests_patch, solution_patch = patches.split_by_paths(full_diff, patches.is_test_path)
    test_patch_path = args.tests_patch
    if not tests_patch.strip() and not test_patch_path:
        test_patch_path = ask(None, "Path to a test patch against the starting revision", "--tests-patch")
    if test_patch_path:
        tests_patch = Path(test_patch_path).expanduser().read_text()
        held_out = patches.affected_paths(tests_patch)
        _, solution_patch = patches.split_by_paths(full_diff, lambda p: patches.is_test_path(p) or p in held_out)
    if not tests_patch.strip() or not solution_patch.strip():
        raise SetupError("a task needs both a source change and a test patch that checks it")
    task_id = identifier(ask(args.id, "Short task name", "--id", f"task-{sha[:8]}"))
    target = Path(args.tasks) / task_id
    if target.exists():
        raise SetupError(f"task already exists: {target}; choose another --id")
    prompt = _prompt(args.prompt_file)
    print("Checks run in a fresh local checkout. Include dependency setup in the command if needed.")
    command = ask(args.test_command, "Command that checks success", "--test-command")
    must_pass = args.must_pass
    if must_pass is None:
        answer = ask(None, "Must this task pass before you would switch setups? (yes/no)",
                     "--must-pass or --no-must-pass", "no").lower()
        if answer not in ("y", "yes", "n", "no"):
            raise SetupError("answer yes or no for must-pass")
        must_pass = answer in ("y", "yes")
    metadata = {
        "id": task_id, "category": args.category, "must_pass": must_pass,
        "repo": {"url": str(repo), "base_commit": parent}, "prompt_file": "prompt.md",
        "tests": {"patch_file": "tests.patch", "command": command, "timeout_seconds": 600},
        "environment": {"runner": "local"}, "solution": {"patch_file": "solution.patch"},
        "provenance": {"source": f"git commit {sha}"},
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".adding-") as tmp:
        staged = Path(tmp) / task_id
        staged.mkdir()
        for name, content in {"prompt.md": prompt, "tests.patch": tests_patch,
                              "solution.patch": solution_patch,
                              "task.yaml": yaml.safe_dump(metadata, sort_keys=False)}.items():
            (staged / name).write_text(content)
        Task.load(staged)  # Validate before publishing the task directory.
        staged.rename(target)
    print(f"Saved {target}. Checking the historical fix and the starting state…", flush=True)
    result = smoke.smoke_task(Task.load(target))
    if not result.ok:
        print(f"Task needs attention:\n{result.detail}\n\n"
              f"Edit {target / 'task.yaml'} and the checks, then run bench smoke.")
        return 1
    print(f"Ready: {task_id}. Historical fix passes; starting state fails.\n"
          "Review that the checks cover the request. Add another task or run bench setup.")
    return 0


def add_setup(args) -> int:
    path = Path(args.configs)
    if path.exists():
        existing = config.load(path)  # Do not extend an invalid configuration.
        raw = yaml.safe_load(path.read_text())
        raw["incumbent"] = existing.incumbent
    else:
        raw = {"configs": []}
    setup_id = identifier(ask(args.id, "Setup name (for example current or cheaper)", "--id"))
    if any(c["id"] == setup_id for c in raw["configs"]):
        raise SetupError(f"setup {setup_id!r} already exists; edit {path} or choose another --id")
    harness = ask(args.harness, "Harness (codex / claude-code / cursor)", "--harness")
    if harness not in ("codex", "claude-code", "cursor"):
        raise SetupError("choose codex, claude-code or cursor")
    model = ask(args.model, "Exact model ID available in your account", "--model")
    if not model:
        raise SetupError("provide a nonempty --model ID")
    extra = ask(args.extra_args, "Optional CLI flags for effort or tools (blank for defaults)",
                "--extra-args", "")
    try:
        extra_args = shlex.split(extra)
    except ValueError as exc:
        raise SetupError(f"invalid --extra-args: {exc}") from exc
    if harness == "codex":
        print("This adapter reports tokens, not dollars. Choose tokens for a cost estimate; reported leaves cost unknown.")
    elif harness == "cursor":
        print("This adapter does not extract usage costs. Choose flat for your own estimate; reported leaves cost unknown.")
    cost_mode = ask(args.cost, "Cost: reported / tokens / flat (reported may be unavailable)",
                    "--cost", "reported")
    modes = {"reported": "harness_reported", "tokens": "per_token", "flat": "flat_per_run"}
    if cost_mode not in modes:
        raise SetupError("choose reported, tokens or flat for cost")
    cost = {"mode": modes[cost_mode]}

    def price(value, label, flag, default=None):
        text = ask(value, label, flag, default)
        try:
            amount = float(text)
        except ValueError as exc:
            raise SetupError(f"{flag} must be a finite nonnegative number") from exc
        if not math.isfinite(amount) or amount < 0:
            raise SetupError(f"{flag} must be a finite nonnegative number")
        return amount

    if cost_mode == "tokens":
        if args.flat_price is not None:
            raise SetupError("--flat-price requires --cost flat")
        cost["input_per_mtok"] = price(args.input_price, "USD per million input tokens", "--input-price")
        cost["output_per_mtok"] = price(args.output_price, "USD per million output tokens", "--output-price")
        cost["cached_input_per_mtok"] = price(args.cached_input_price, "USD per million cached input tokens",
                                              "--cached-input-price", str(cost["input_per_mtok"]))
    elif cost_mode == "flat":
        if any(v is not None for v in (args.input_price, args.output_price, args.cached_input_price)):
            raise SetupError("token prices require --cost tokens")
        cost["flat_usd"] = price(args.flat_price, "Estimated USD per attempt", "--flat-price")
    elif any(v is not None for v in (args.input_price, args.output_price, args.cached_input_price, args.flat_price)):
        raise SetupError("use --cost tokens or --cost flat with price arguments")
    raw["configs"].append({"id": setup_id, "harness": harness, "model": model,
                           "extra_args": extra_args, "cost": cost})
    if args.current or not raw.get("incumbent"):
        raw["incumbent"] = setup_id
    path.parent.mkdir(parents=True, exist_ok=True)
    # Validate and replace atomically; never partially rewrite an existing setup list.
    with tempfile.TemporaryDirectory(dir=path.parent, prefix=".setup-") as tmp:
        pending = Path(tmp) / path.name
        pending.write_text(yaml.safe_dump(raw, sort_keys=False))
        config.load(pending)
        pending.replace(path)
    print(f"Saved {setup_id} in {path}. Current setup: {raw['incumbent']}.\n"
          "Reported usage cost is not an invoice. Token and flat costs are estimates; use the same cost basis.\n"
          + ("Add an alternative with bench setup." if len(raw["configs"]) < 2
             else "Next: bench compare --snapshot first"))
    return 0
