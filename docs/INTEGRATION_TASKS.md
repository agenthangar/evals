# Capturing integration tasks from your own work

A useful task can cross a database, an API, a browser and an external service.
Keep the boundaries that caused the original problem. Replace external effects
with controllable adapters, while retaining real local persistence and HTTP or
browser behavior when those are part of the acceptance contract.

## Freeze the contract before running models

Record the original request and immutable before/after source revisions in your
private task pack. A historical implementation is evidence, not an oracle: test
it against the proposed contract before treating it as a reference solution.
If it fails a newly specified requirement, document the adaptation and retain
the historical implementation as a negative control when useful.

For a new feature, a small API scaffold can make the task evaluable without
requiring a particular internal design. Label which files are historical and
which interfaces or persistence helpers were supplied. Keep the actual feature
logic as candidate work. Ensure the unchanged scaffold builds and fails on
behavior, rather than only on missing symbols. Give every model the same public
API, environment instructions and scope.

Examples of precise acceptance contracts:

| Boundary | Observable contract | Plausible incomplete implementation |
| --- | --- | --- |
| Saved state and restart | A repair survives reopening the store and preserves explicit choices | Repairs only the displayed state |
| Revisioned synchronization | Older or duplicate deliveries cannot replace a newer snapshot | Last arrival always wins |
| Database and external deletion | A DB rollback preserves rows and reports external deletions that already succeeded | Claims that all stores rolled back |
| Reports and downloads | Export includes every matching row, independently of UI pagination | Exports only the displayed page |
| Generated game content | An independent transition model proves the stated shortest solution | Searches using the candidate's possibly broken transitions |

For irreversible effects, specify failure and retry behavior explicitly. A fake
storage adapter should implement documented success, failure and idempotency
semantics. Inject failures before and after individual effects and immediately
before the database commit. Verify both surviving state and the returned account
of what happened. Do not require an impossible cross-service atomic rollback.

## Prepare an equal, reproducible environment

Pin the runtime, dependency lockfile, browser build and setup script. Put only
dependencies in a shared cache; keep source answers, transcripts, grading code
and previous attempts outside the agent's readable environment. Each attempt
needs its own writable dependency/build state when tools generate clients or
caches. A read-only shared cache plus a fresh local copy can avoid downloads
without sharing mutable state between candidates.

Provide a candidate-visible setup command and apply the same setup during
clean-checkout grading. Protect the setup script and grading configuration from
candidate edits. The current local runner does not provision dependencies for
you; the task's check commands must do so explicitly. Keep machine-specific
paths in your private environment definition, not in this public framework.

For database and browser checks:

- Allocate a fresh temporary database; never reuse a configured development or
  production database. Apply the actual migrations and seed synthetic records.
- Use separate database files and ports for concurrent attempts. Keep setup,
  server, browser and cleanup ownership within the check process.
- Exercise the real authenticated API and download bytes. Parse CSV or other
  formats structurally; do not grade only link text or screenshot appearance.
- Freeze or inject application clocks. Disable background timers in the fixture
  when the task tests scheduled work by directly invoking it with explicit times.
- Check timezone boundaries, overlaps, incomplete records, repeated names,
  inactive records, tenant scoping and pagination separately where relevant.
- Stop and reap the child processes you created, including on failure. A passing
  test process must not leave a server writing to the next attempt's database.

A task can expose multiple independent checks:

```yaml
tests:
  patch_file: tests.patch
  protected_paths: [package.json, package-lock.json, prepare.sh]
  checks:
    - id: database-contract
      command: sh prepare.sh && node heldout/check-database.mjs
      timeout_seconds: 600
    - id: browser-contract
      command: sh prepare.sh && node heldout/check-browser.mjs
      timeout_seconds: 600
```

These are task-specific entry points that the author supplies in the held-out
patch. They should retain assertion logs and clearly distinguish an unavailable
tool or failed reference environment from a candidate's broken migration,
invalid code or incorrect behavior. A generous model timeout does not replace
appropriate setup, server-start and grading timeouts.

## Admit only after a complete replay

Run the reference, unchanged baseline and each plausible incomplete solution
through clean-checkout grading at least twice. Require each negative control to
fail the intended assertion; a compiler error or a passed test's name appearing
in a log is insufficient evidence.

Also exercise the transport path: prepare an agent checkout under its actual
isolation boundary, build or run the reference there, capture the resulting
diff, and grade that diff in another fresh checkout. Check that generated
clients, build caches, temporary databases and candidate-authored tests neither
pollute the patch nor collide with held-out tests.

Then run a small real model access smoke test before the scored attempts. Freeze
all task contracts, model IDs, harness arguments, tool versions, effort and time
budgets. If tasks must run in separate cohorts, record their windows and preserve
the same per-task conditions for every model; disclose the cohorts when combining
results. Do not silently add new cells to an earlier comparison with different
inputs.

The result belongs to your workload. Several tasks from the same application
are correlated evidence. Keep per-task failure descriptions, repeated-attempt
counts, environment failures and remaining physical or external-service limits
alongside any aggregate score.
