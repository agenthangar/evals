# Evaluating models for your work

## Select for relevance before difficulty

Keep a private candidate inventory with the original request, source, date,
frequency, cost of failure, available environment and success evidence. Mine
recent Git history and review local transcript category summaries. Include work
without tests in the inventory: otherwise you select only the work easiest to
automate. Mining flags are triage information, not a quality score.

Separate routine tasks, valuable improvements and critical failure scenarios.
Prefer a suite whose mix resembles the work you delegate. Publish no universal
winner from this mixture. Report categories separately; this engine's overall
rate is an unweighted description of the chosen task set, not an estimate of
business value or a workload-weighted score.

Choose an initial pilot for breadth, calibrate it, and expand where results are
uncertain. Use real multi-step work when that is representative; do not add
artificial complexity solely to make modern models fail. If all contenders solve
an important routine task, the result can still inform cost and latency choices.
Retain enough fresh tasks to detect regressions after prompt/tool changes.

## Review the evaluator

For each task, a reviewer should be able to answer:

| Question | Evidence |
|---|---|
| Is the requirement stated to the agent? | Prompt acceptance behavior |
| Is success observable? | Assertion or recorded artifact tied to that requirement |
| Can an incomplete fix pass? | Plausible wrong solution rejected by the intended assertion |
| Does the test accept other valid solutions? | Alternative implementation or oracle review |
| Does it preserve working behavior? | Relevant regression cases |
| Can the environment fail independently? | Reference calibration, pinned tools, failure logs |
| What remains untested? | Explicit task limitations |

Avoid graders that compare exact source text, reward verbosity, require a single
algorithm, check only keywords or trust the candidate's own claim of success.
Protect grading helpers and dependency/test-runner configuration. Include
negative controls aimed at shortcuts (empty output, skipped work, ignored errors)
as well as realistic domain mistakes. Examine each failure log: syntax failure
and failed assertions are different evidence.

Give held-out tests their own test target or namespace so valid candidate-authored
tests cannot collide with evaluator class names. Check evidence relationships
instead of incidental claim IDs. When prose is unconstrained, validate structured
facts automatically and record a separate semantic review; capitalization and
one preferred sentence are poor correctness criteria.

For subjective artifacts, first check objective requirements, then have reviewers
score anonymized outputs in randomized order. Use anchored dimensions such as
correctness, completeness, evidence, usability and constraint adherence, with
examples for each score and explicit critical failures. Review disagreements;
calibrate any future model judge against those human judgments, and test for
order, length and self-preference bias. Keep manual judgments outside automatic
routing until the engine has a reviewed implementation for that lane.

Also smoke-test the complete transport path: build or test a reference candidate
in the agent environment, capture its diff, and grade that diff in a fresh
checkout. Reference-patch calibration alone does not exercise generated build
products. Include suitable build/cache exclusions in the starting repository and
clean generated products before grading. Compiled caches can embed absolute paths
and fail when moved, even when the source is correct. Keep infrastructure failures
separate from behavioral failures; fix the environment and start a new snapshot
when the evaluation contract changes.

A live pilot may still reveal grader defects. Preserve its original results and
candidate patches, document every repair, recalibrate the grader, and regrade
every unchanged candidate under the same corrected contract. Record a derived
snapshot linked to the original generation manifest. Disclose this post-hoc
calibration and validate conclusions on fresh tasks before making strong routing
claims.

## Keep comparisons fair

A candidate is a model **plus** harness, effort, prompt, tools, environment,
permissions and budget. Comparing native Claude Code and Codex measures those
configurations, not isolated foundation-model quality. Effort labels are not
equal compute budgets across providers. Record wall time and cost as well as
success. Keep toolchain versions, dependencies, network policy and hardware
consistent, and avoid training or tuning on the final held-out tasks.

Before a full matrix, run a small live edit-and-test probe for each exact model ID
under the actual agent permissions. A CLI being installed or authenticated does
not prove that it supports a newly released model. Resolve CLI-version and account
access problems before freezing the snapshot; never silently substitute a model.
Give every candidate the same environment setup guidance, including any nested
sandbox restrictions, and keep smoke-probe costs separate from scored attempts.

The runner interleaves cells in a stable shuffled order. It fingerprints the
contract and selected matrix to prevent accidental stale-cache reuse, and records
engine/runtime/CLI versions. This does not freeze provider backend changes or
host language tools. Record those separately, finish within a bounded measurement
window, and start a new snapshot if anything material changes.

Remove solution history from the agent checkout and isolate the agent from the
private pack at the OS level. Unrestricted local execution is convenient for
trusted development but does not prove held-out secrecy. Live production accounts,
private network access and real sends/deployments should not be needed to replay
a task; use a faithful sandbox or explicitly mark missing coverage.

## Read uncertainty before routing

An attempt succeeds only when every check passes. Attempt rates summarize run
reliability on this fixed set; repeated attempts on one task are correlated.
For comparisons, the engine reduces each task to whether **every** recorded
attempt succeeded and compares that reliable-task rate. Both configurations must
have the same task/trial cells. This conservative metric depends on trial count,
so freeze the count for the snapshot.

The engine uses approximate Wilson/Newcombe intervals on distinct tasks. These
still assume independent tasks. Several tasks extracted from one incident can
violate that assumption: group them in interpretation and collect new independent
work. The six-task minimum is only a guard against the most extreme sparsity;
you will usually need substantially more to establish a small difference.

Equivalence is a claim that needs evidence: the entire difference interval must
fit in the ±10-point margin. Otherwise the report says `inconclusive`, even if
point estimates happen to be close. The margin is a coarse default, not a
universal acceptable failure rate. Investigate every critical failure separately.

Cost per solve includes successful and failed attempts. If any cost is missing,
the aggregate cost is unknown, not the sum of the known portion. Compare the
same cost basis for all contenders. An automatic incumbent fallback indicates
insufficient evidence for switching; it does not certify the incumbent's quality.
