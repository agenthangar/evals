# Task authoring

Keep real task packs in a private repository. A task is a reproducible starting
state, a request that makes sense on its own, and an independently reviewed
success contract. The grader is at least as important as the prompt.

## Contract

```yaml
id: repair-report
category: reporting
repo:
  url: repo.bundle
  base_commit: <full immutable Git hash>
prompt_file: prompt.md
tests:
  patch_file: tests.patch
  protected_paths: [package.json, package-lock.json]
  checks:
    - id: behavior
      command: node --test tests/report.test.mjs
      timeout_seconds: 120
    - id: regression
      command: node --test tests/existing.test.mjs
      timeout_seconds: 120
environment:
  runner: local
solution:
  patch_file: solution.patch
provenance:
  source: private issue or incident reference
  why_this_task: Explain why this work belongs in your workload.
evaluation:
  criteria:
    - id: correct-totals
      description: Totals reflect overlapping records without counting them twice.
      check: behavior
    - id: existing-behavior
      description: Existing filtering and empty-input behavior are preserved.
      check: regression
  negative_controls:
    - id: naive-sum
      patch_file: naive-sum.patch
      reason: Adds individual durations but double-counts overlaps.
      fails: [behavior]
  limitations:
    - Does not test the browser, database permissions or deployment.
```

`tests.command` and `tests.timeout_seconds` remain supported for old tasks, in
place of `tests.checks`; its check ID is `tests`. Do not specify both. For Docker,
use `runner: docker` and an `image` with all dependencies already installed,
preferably pinned by digest. Networking is disabled during Docker grading.
Local grading uses your host tools; record and pin them separately.

Every check is required. Named checks produce separate evidence and all run even
when one fails. Protect test configuration and harness helpers the agent should
not change; do not protect application files that the task legitimately needs
to modify. Held-out test patch paths are protected automatically. This mechanism
is not a security sandbox against malicious test-runner or application behavior.

## From a real task to a benchmark

1. Record the original request, available context, source revision, incident/date,
   frequency, impact, and relation to other tasks. Keep these references private.
2. Reproduce the initial failure. Prefer an actual historical pre-fix state. If
   you extract modules, stub an API or seed defects, label the construction and
   the coverage lost. Do not present a reduced fixture as end-to-end coverage.
3. Rewrite the prompt in behavioral terms. Specify required outputs and policy
   choices, including ambiguous boundary behavior. Do not include the fix, a
   solution-revealing commit message, test expectations or answer artifacts.
4. Map each requirement to assertions. Cover ordinary inputs, boundaries, invalid
   inputs, preservation of existing behavior, and costly failure modes. Use an
   independent oracle or metamorphic/property checks where possible.
5. Write two or more plausible wrong solutions: partial fixes, ignored opt-outs,
   wrong timezone assumptions, dropped records, happy-path-only behavior. Each
   control is a **complete candidate diff against base_commit**, not a patch on
   top of solution.patch. List the checks that must reject it in `fails`.
6. Try a second valid implementation when feasible. The grader should accept
   alternative algorithms, harmless refactors and equivalent output formatting.
7. Audit, calibrate twice and inspect the failures. A compiler error is not proof
   that your semantic assertions catch an incomplete but compiling solution.
8. Freeze the task and keep a new untouched holdout for the final comparison.

`bench audit` checks the presence and consistency of criteria, provenance,
controls and limitations. It cannot establish the truth of that metadata.
`bench smoke --repeat 2` exercises the reference solution, empty diff and every
control twice. Invalid patches, missing-command errors and timeouts do not count
as valid control detections. Other test-runner failures still require inspection.
Two rounds can catch obvious instability; they do not prove absence of flakes.

A passing task requires all required check commands to exit zero before their
timeouts. stdout/stderr and per-check status are retained. Check commands must
actually execute tests; empty collection, swallowed exceptions and always-zero
wrappers invalidate the task even if the metadata audit passes.

## Selection and maintenance

Start with a small calibrated pilot, then expand across recent work before
making routing decisions. Do not satisfy a category's sample floor by adding
near-duplicates or many repetitions of one task. Keep related incidents together
when reviewing uncertainty. Refresh saturated or obsolete tasks, record why they
were retired, and keep historical results tied to the old task fingerprint.

For UI, writing, research and release workflows, tests alone may miss the intended
outcome. Use a concrete artifact and an anchored human rubric, or add real UI/
sandbox integration checks. If the critical outcome cannot be graded reliably,
keep it in a separate manual evaluation lane. This CLI does not implement an
LLM judge or blind human-review workflow; do not disguise keyword checks as one.
See [methodology](../docs/METHODOLOGY.md) for a practical review protocol.
