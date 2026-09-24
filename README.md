# AgentHangar Evals

**Find the best model and agent configuration for your own day-to-day work.**
Build a private evaluation set from tasks you actually delegate, verify that its
graders detect meaningful failures, and compare configurations on the same work.
The output is evidence for your choices, not a worldwide model leaderboard.

This repository contains the generic engine, authoring workflow and synthetic
teaching examples. Your task history, source snapshots, reference solutions,
held-out tests, configurations and results belong in a separate private repo.

## Start with the tasks and their evaluation

1. **Sample your work.** Review recent requests, fixes, features and incidents.
   Include frequent routine work and infrequent costly mistakes. Record why each
   task matters; don't select tasks because a particular model wins them.
2. **Reconstruct a fair starting point.** Give the agent the information you had
   before solving the task, a pinned source tree and a behavioral specification.
3. **Define success before running models.** Map each requirement to an
   executable check, with boundary cases and regression checks. Test outcomes,
   not whether the diff resembles a reference implementation.
4. **Evaluate the evaluator.** The reference solution must pass, the starting
   state must fail, and plausible incomplete solutions must fail the intended
   checks. Repeat this calibration to catch obvious instability.
5. **Pilot task difficulty.** Run a small matched matrix. All-pass results may
   reveal useful routine work, lost context, or weak checks; they do not establish
   a demanding benchmark. Review failures before selecting fresh incident holdouts.
6. **Run a frozen comparison.** Hold tasks, tools, effort, environment and budget
   fixed. Inspect failures and uncertainty before changing your workflow.

Read [task authoring](tasks/README.md) and [evaluation methodology](docs/METHODOLOGY.md)
before building a benchmark you plan to trust. A valid YAML file is not evidence
that a task or grader is good.

## Install

Requires Python 3.10+ and Git. From a checkout:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
bench --version
```

The last published release can also be installed with
`uv tool install 'git+https://github.com/AgentHangar/evals.git@v1.0.1'`.
The quality-contract features documented here are in the 1.1.0 source tree;
use a reviewed commit SHA to pin that version until its release tag is published.

Real runs require the corresponding logged-in CLI: `codex`, `claude`, or
`cursor-agent`. Docker is needed for tasks using Docker grading.

## Try it without a model account

The original calculator fixture exercises the whole pipeline deterministically:

```sh
bench --tasks examples/tasks --configs examples/configs/script.yaml doctor
bench --tasks examples/tasks smoke
bench --tasks examples/tasks --configs examples/configs/script.yaml \
  --runs /tmp/agenthangar-demo run --snapshot demo --trials 1
bench --configs examples/configs/script.yaml \
  --runs /tmp/agenthangar-demo report --snapshot demo
bench --runs /tmp/agenthangar-demo pilot-review --snapshot demo --json
```

Two richer, standard-library-only examples show how to evaluate overlapping
intervals and a settings migration that must preserve user choices:

```sh
bench --tasks examples/quality-tasks validate
bench --tasks examples/quality-tasks audit
bench --tasks examples/quality-tasks smoke --repeat 2
```

Each has behavioral checks and two plausible wrong solutions. Their answers are
public, so they are teaching fixtures, not a model-ranking dataset.

## Build a private task pack

Survey your work locally, then discover recent candidates:

```sh
bench mine transcripts ~/.codex/sessions --source codex --mode interactive
bench mine transcripts ~/.claude/projects --source claude --mode interactive
bench mine commits ~/code/project --since 2026-09-01 --json
bench mine commits ~/code/project --since 2026-09-01 --include-untested --json
bench mine incidents ~/code/project --since 2026-09-01 --json
bench mine struggles ~/.codex/sessions --source codex --mode interactive --json
bench mine scaffold ~/code/project <fix-sha> ../private-benchmark/tasks/task-id
```

Mining lists candidates and review flags; it does not certify task quality.
`--include-untested` makes work needing a manually written grader visible rather
than excluding it from your workload. Scaffolding requires a commit with tests,
splits source/test patches, and creates a prompt stub and review checklist.
Finish the specification, environment and grader by hand. For features without
existing tests, build the task contract manually using the examples.

For deeper tasks, follow [incident discovery and qualification](docs/DISCOVERY.md).
`incidents` links nearby repairs without excluding broad or untested changes;
`struggles` retrieves visible user corrections after assistant replies. Both
produce private review leads, not difficulty scores. Excerpts are off by default.
Use the [candidate review template](docs/templates/INCIDENT_REVIEW.md) to preserve
real context, replay failed fixes, probe grader gaps, and record exclusions.
For UI timing, replay and device behavior, use the
[runtime evidence protocol](docs/RUNTIME_EVIDENCE.md) and its audit worksheet.

```sh
bench --tasks ../private-benchmark/tasks validate
bench --tasks ../private-benchmark/tasks audit --json
bench --tasks ../private-benchmark/tasks smoke --repeat 2
```

Use a private Git bundle when the task needs a portable source snapshot.
Relative `repo.url` values resolve from the task directory. `base_commit` must be
a full immutable Git hash. Never bundle credentials or unrelated production data.

## Compare current configurations

Copy [configs/products.example.yaml](configs/products.example.yaml) to your private
pack. It contains GPT-6 Astra and current Claude candidates verified on 2026-09-22,
with explicit effort settings and source links. Model availability is specific to
your account; `doctor` checks executables, not model entitlement or live inference.
Keep your incumbent and cost basis explicit. API-equivalent cost, subscription
marginal cost and invoice cost are different measurements.

```sh
bench --tasks ../private-benchmark/tasks \
  --configs ../private-benchmark/configs/products.yaml doctor
bench --tasks ../private-benchmark/tasks \
  --configs ../private-benchmark/configs/products.yaml \
  --runs ../private-benchmark/runs \
  run --snapshot september-comparison --trials 3 --strict
bench --configs ../private-benchmark/configs/products.yaml \
  --runs ../private-benchmark/runs report --snapshot september-comparison
```

`--strict` requires the authoring audit and two rounds of grader calibration.
Legacy tasks still run without `--strict`, but lack those quality assurances.
Tasks/configurations are interleaved deterministically to limit order effects.

Before that full run, use a smaller pilot snapshot and inspect it with
`bench --runs ../private-benchmark/runs pilot-review --snapshot pilot --json`.
The optional `--require-signal` exits with status 2 when no between-configuration
pass-count difference is observed or execution/grading problems remain. It is a
diagnostic gate, not proof of difficulty, statistical significance or a winner.
Routine tasks may be valuable even when this gate does not pass.

The agent gets a fresh Git repository containing only the starting tree, with
no remote or later solution history. Its resulting diff is replayed in a new
grading checkout. Held-out and explicitly protected paths are restored before
tests are applied. Each check's result and output are recorded; every required
check must pass for a task to pass.

Snapshots include input fingerprints, engine fingerprint, Python/platform and
agent CLI versions. Resuming refuses changed tasks, grading contracts, configs,
trial counts or budgets. Use a new snapshot after a change. Task authors must
also pin and record their Node/Swift/toolchain versions, dependency locks, images
and external inputs; the manifest cannot detect every host dependency change.

## Interpret results cautiously

Reports contain attempt pass rates, cost per solve, distinct tasks solved on
every attempt, per-category comparisons and `routing.yaml`. Comparisons require
matched task/trial coverage and use **distinct reliably solved tasks**, not
repeated attempts as independent evidence. Fewer than six distinct tasks in a
category yields `insufficient_data`; six is a floor, not a recommended sample size.

`roughly_equal` requires the full approximate 95% difference interval inside
±10 percentage points. A wide interval is `inconclusive`. Only demonstrated
better/equivalent candidates with complete comparable cost data can replace the
incumbent automatically. Falling back to the incumbent is not proof it is good
enough. Inspect critical failure modes and choose your own acceptance threshold.

No runs means no model recommendation. Calibration proves specific graders
caught specific controls; it does not establish model difficulty, representative
coverage or a trustworthy winner. Related tasks and tasks used to tune prompts
can inflate confidence; keep a fresh holdout and review dependence.

## Security and privacy

The harnesses run unattended with the permissions of the host user. Removing
Git history prevents an accidental local answer shortcut; it is **not an access
boundary**. Same-user agents may still access the task pack, original repository,
credentials or network. For credible held-out evaluation, run the agent in a
separate VM/container/user with only the starting tree and approved tools mounted,
and keep grading data outside that environment. Docker grading alone does not
isolate the agent. See [SECURITY.md](SECURITY.md).

Transcript surveying stays local. Keep all real tasks and results in your private
pack, and review source trees, bundle contents and diffs before sharing artifacts.

## Layout

```text
src/bench/                 discovery → validation → audit → calibration → run → report
examples/tasks/            tiny deterministic pipeline demonstration
examples/quality-tasks/    synthetic contracts with negative controls
configs/products.example.yaml
tasks/README.md           task authoring guide (real tasks are gitignored)
docs/METHODOLOGY.md         selection, grader review and interpretation
```

MIT. Contributions should improve the generic framework or use fictional fixtures.
