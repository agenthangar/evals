# AgentHangar Evals

AgentHangar Evals helps you decide which coding agent and model to use for your
own work. It runs each option against repeatable tasks from your repositories,
grades the results with held-out tests, and compares reliability with cost per
solved task. The result is a simple routing policy: use this configuration for
this kind of work.

## Why this exists

Public leaderboards measure somebody else's tasks. AgentHangar Evals helps you
build a private benchmark from work you actually do, so you can choose the
cheapest option that is reliable enough for each category of task.

The benchmark engine is public. Your real prompts, held-out tests, known-good
solutions, model outputs, and reports stay in your own private task workspace.

## How it works

1. Turn tested fixes from your Git history into repeatable tasks.
2. Run the same tasks through each coding-agent configuration you are
   considering.
3. Grade every attempt with held-out tests that the agent cannot rewrite.
4. Generate a report showing pass rate, cost per solve, and which configuration
   to use for each kind of task.

## What this is (and is not)

- **A snapshot comparison, not a leaderboard.** All configs are measured in
  the same window; numbers are never compared across snapshots because the
  products themselves change between them.
- **Coarse decisions, not fine rankings.** With tens of tasks the statistics
  only support three buckets per category — clearly better / roughly equal /
  clearly worse vs your incumbent (Wilson/Newcombe 95% intervals, with a
  10-point equivalence margin).
- **Autonomous one-shot runs.** This measures which setup can solve your tasks
  unattended, not which one feels best during an interactive session.
- **Tasks come from git history, not transcripts.** Transcripts are only a
  survey of your task-category mix; commits with tests give reproducible
  state and automated grading.

## Install

AgentHangar Evals requires Python 3.10 or newer and Git. Docker is needed only
for task packs that use Docker grading. The easiest way to install the CLI in
an isolated environment is with [uv](https://docs.astral.sh/uv/):

```sh
uv tool install --python 3.12 \
  "git+https://github.com/AgentHangar/evals.git@v1.0.1"
bench --version
```

Until the package is published on PyPI, releases are installed directly from
GitHub. To work on the project itself:

```sh
git clone https://github.com/AgentHangar/evals.git
cd evals
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
```

Product CLIs are needed only for real runs: `claude` (Claude Code),
`codex` (Codex CLI), `cursor-agent` (Cursor), each installed and logged in.
Docker is recommended for grading (`environment.runner: docker` in tasks).

## Try the synthetic example

The repository includes a deliberately small, fully public calculator task.
It uses the deterministic script harness, so it exercises validation, grading,
the smoke gate, running, and reporting without a paid agent account:

```sh
bench --tasks examples/tasks \
  --configs examples/configs/script.yaml \
  doctor
bench --tasks examples/tasks validate
bench --tasks examples/tasks smoke
bench --tasks examples/tasks \
  --configs examples/configs/script.yaml \
  --runs /tmp/agenthangar-evals-demo \
  run --snapshot demo --trials 1
bench --configs examples/configs/script.yaml \
  --runs /tmp/agenthangar-evals-demo \
  report --snapshot demo
```

The example's tests and solution are intentionally visible. Real benchmark
task packs must remain private so agents cannot inspect held-out grading data.

`bench doctor` checks the selected tasks, configurations, Git, Docker when
needed, and the agent CLIs required for a run. It exits with a clear error when
something is missing instead of starting an incomplete benchmark.

## Run your own benchmark

### 1. Understand your task mix (optional)

```sh
bench mine transcripts ~/.claude/projects --source claude --mode interactive
bench mine transcripts ~/.codex/sessions --source codex --mode interactive

# Optional: export the cleaned conversations for local, manual review
bench mine transcripts ~/.codex/sessions --source codex --mode interactive \
  --output codex-candidates.jsonl
```

Prints your session distribution by category (bugfix / feature / refactor /
...) so the task suite you build matches the work you actually delegate. The
parser understands current Claude Code and Codex JSONL formats, ignores
sidechains and injected context, and reports session sources and modes. Use
`--mode automation` to inspect headless jobs such as scheduled newsletters,
`--mode benchmark` to inspect agent runs launched by this benchmark, or omit
the filters to include everything. Transcript contents stay local.

`--output` writes one source-neutral JSON record per cleaned session, including
the conversation and enough local metadata to find the original transcript.
The export may contain private prompts, responses, and paths: keep it in a
private workspace and review it manually. It is a candidate list, not a set of
reproducible benchmark tasks.

### 2. Build tasks from Git history

```sh
bench mine commits ~/code/myrepo             # commits touching source AND tests
bench mine scaffold ~/code/myrepo <sha> tasks/fix-date-parse
```

The scaffold sets `base_commit` to the parent of the fix, splits the commit
into `solution.patch` (source) and `tests.patch` (held-out tests), and stubs
`prompt.md` + `task.yaml`. Then finish it **by hand** — this is the part that
makes the benchmark trustworthy:

1. Rewrite `prompt.md` as a real task description (what's broken, how to
   reproduce, where to look — never the solution). Validation refuses
   prompts that still contain `TODO`.
2. Set the real test command and a Docker image with the repo's dependencies
   in `task.yaml`.
3. `bench validate && bench smoke --task fix-date-parse`

Aim for 25–30 tasks whose category mix matches step 1. See
[tasks/README.md](tasks/README.md) for the format and authoring guidance.

### 3. Choose the configurations to compare

Create your private product configuration from the concrete example:

```sh
cp configs/products.example.yaml configs/products.yaml
```

The example includes a useful starting matrix of common Claude Code, Codex,
and Cursor configurations. Edit `configs/products.yaml` to keep the products
and models you want to compare, choose your `incumbent` (the baseline
everything is bucketed against), and update pricing before each snapshot.
Decide explicitly whether you're costing at API prices or at your
subscription's marginal cost. The working file is gitignored because product
choices, routing decisions, and pricing assumptions may be private and become
stale quickly.

### Autonomous run permissions

Real benchmark runs are intentionally unattended. The Claude Code, Codex, and
Cursor harnesses use their unrestricted, non-interactive permission modes so
an agent can edit files and run commands without pausing for approval. This is
the same tradeoff as running those CLIs autonomously yourself: the agent has
the access of the user running `bench`. Use it carefully, run only tasks and
repositories you trust, and be mindful of credentials and sensitive files on
your computer. Docker task grading isolates the test command, not the agent
process itself. See [SECURITY.md](SECURITY.md) for more detail.

### 4. Run one benchmark snapshot

Run only when a genuinely notable model ships — and a few weeks after launch,
once the product integrations have matured. Every run starts with the smoke
gate (known-good solution must pass, empty diff must fail) so bit-rotted
tasks are caught before they masquerade as model failures.

```sh
bench doctor
bench run --snapshot 2026-07-sonnet5 --trials 3
```

Interrupted snapshots resume: completed trials are cached on disk under
`runs/<snapshot>/<task>/<config>/trial-N/`.

### 5. Read the recommendation

```sh
bench report --snapshot 2026-07-sonnet5
```

Writes `report.md` (pass rates with 95% CIs, cost per solve, per-category
buckets) and `routing.yaml` — the actionable artifact:

```yaml
routing:
  bugfix:
    use: claude-code-haiku
    why: cheapest config not clearly worse than incumbent (pass 8/9)
  debugging:
    use: claude-code-opus
    why: no challenger qualified; defaulting to incumbent
```

## Keeping it honest

- **Capture as you go.** When you finish a real task that has tests, spend
  ten minutes scaffolding it into the suite. That's how the benchmark stays
  representative without a periodic harvesting project.
- **Never skip the smoke gate.** `--skip-smoke` exists for debugging only.
- **Don't read `insufficient_data` as "equal".** Fewer than 6 trials per
  side in a category means the bucket is a shrug, not a verdict.
- **Agents can't grade themselves.** Grading reverts any agent edits to
  held-out test paths before applying the test patch, so rewriting the tests
  doesn't count as solving the task.

## Layout

```
configs/products.example.yaml  concrete product/model example (tracked)
configs/products.yaml          private snapshot configuration (gitignored)
tasks/<id>/             task.yaml, prompt.md, tests.patch, solution.patch
runs/<snapshot>/        per-trial results, report.md, routing.yaml (gitignored)
src/bench/              the pipeline (mine → validate → smoke → run → report)
tests/                  unit + end-to-end tests (no product CLIs required)
```

## Security and privacy

Real task packs and transcript exports can contain proprietary source, held-out
tests, known-good solutions, prompts, responses, and local paths. Keep them
outside this repository and review [SECURITY.md](SECURITY.md) before processing
transcripts or running third-party agent CLIs.

## License

MIT
