# AgentHangar Evals

**Find a cost-efficient coding setup that works on your own tasks.**

Turn work you have already done into a private benchmark. Replay the same tasks
with different models, harnesses, tools or settings, then compare success, cost,
time and the actual failures.

A task has three parts: **the code before the work, the request, and checks for
success**. The framework verifies that the historical fix passes and the starting
state fails before running agents.

## Install

The guided MVP is available from this source checkout. Requires Python 3.10+ and Git:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
bench --help
```

For model runs, install and sign into the CLI you want to evaluate: `codex`,
`claude`, or `cursor-agent`. Use model IDs available in your own account.

## Create your benchmark

```sh
bench init ~/my-benchmark
cd ~/my-benchmark
bench add ~/code/my-project
```

`bench add` shows recent changes and guides you through:

1. Selecting a past task and giving it a short name.
2. Describing what needed doing, without giving away the solution.
3. Providing a command that checks success.
4. Marking it **must-pass** if an alternative must solve it before you would switch.

It extracts the starting revision, source change and test change, then checks the
historical solution and starting state in fresh local checkouts. Your original
repository is unchanged. Install the dependencies required by those checkouts,
or include setup in the test command. If a commit has no tests, supply a test
patch against its starting revision; the guide asks for its path.

Start with **5–10 representative tasks**: bugs, features, migrations or refactors
you actually delegate. Review whether the checks cover the request. Passing the
historical fix and rejecting the starting state does not prove complete coverage.
The guided flow handles individual non-merge commits; use the
[authoring guide](tasks/README.md) for changes spanning multiple commits.

## Add setups

```sh
bench setup  # Add your current setup first
bench setup  # Add an alternative
```

A **setup** is a model, harness and settings. The guide asks for the model ID,
optional CLI flags for effort or tools, and how to measure cost. The first setup
is your current baseline; use `bench setup --current` when adding a new baseline.

Cost can come from reported usage, your token prices, or a flat estimate per
attempt. Missing cost stays unknown. Reported usage cost is not your subscription
bill; token and flat costs are estimates. Use the same cost basis for alternatives.
For harnesses that report tokens but no dollar amount, choose token prices.

To evaluate a model, keep the harness and tools fixed. To evaluate a tool, keep
the model and harness fixed. You can also compare complete everyday setups;
that result describes the whole setup. Edit `configs/products.yaml` to adjust
settings, or use `bench setup --help` for noninteractive flags.

## Compare and inspect

```sh
bench compare --snapshot first
```

This checks prerequisites and task checks, runs one attempt per task and setup,
and writes `runs/first/comparison.md` plus a machine-readable `comparison.json`.
It shows:

- Tasks and attempts passed.
- Total cost, including failed attempts, and cost per successful attempt.
- Median agent time and the source of the cost figures.
- Failed attempts with links to checks, patches and agent logs.

The quality bar is simple: **pass every must-pass task and at least as many tasks
as your current setup**. At least one task must pass. Among setups meeting that
bar with complete cost information, the report identifies the lowest observed
cost per successful attempt. It does not change your routing automatically.

Inspect *which* tasks failed before switching: equal totals can hide different
failures. A small sample is a useful starting point, not proof of a general winner.
Repeat a promising comparison, and include fresh tasks before relying on it:

```sh
bench compare --snapshot repeated --trials 3
bench compare --snapshot repeated --report-only  # No agents or tests run
```

With repetitions, a task counts as passed only if every attempt succeeds. Resume
an interrupted run with the same command. Completed attempts are reused; use a
new snapshot name after changing tasks, setups or trial counts.

## Try it without a model account

From this repository, a deterministic example runs a known-good patch against a
no-op setup. It exercises the full comparison flow without model calls:

```sh
bench --tasks examples/tasks --configs examples/configs/script.yaml \
  --runs /tmp/agenthangar-demo compare --snapshot demo
```

The public fixtures teach the workflow. Their solutions are public, so they are
not a model-ranking dataset.

## Keep your work private

Create real benchmarks in a separate private directory or repository. This repo
contains the generic framework and fictional examples. Keep real requests, source
patches, solutions and results in your own pack. Source repositories must remain
available at their recorded locations; a private Git bundle can make a pack portable.

Agents and local checks run with your user permissions. Removing solution history
from a checkout is not a security boundary. Enforced held-out secrecy requires a
separate agent environment with only approved inputs. See [security](SECURITY.md).

## When you need more

The existing advanced commands remain available: `mine`, `validate`, `audit`,
`smoke`, `doctor`, `run`, `report` and `pilot-review`.

- [Task authoring](tasks/README.md): custom checks, Docker grading and negative controls.
- [Evaluation methodology](docs/METHODOLOGY.md): grader review, repeated trials and uncertainty.
- [Incident discovery](docs/DISCOVERY.md): finding deeper work in Git and transcripts.
- [Integration tasks](docs/INTEGRATION_TASKS.md) and [runtime evidence](docs/RUNTIME_EVIDENCE.md): broader coverage.
- [Contributing](CONTRIBUTING.md): develop and test the framework.

MIT. Built for personal and team decisions on relevant work.
