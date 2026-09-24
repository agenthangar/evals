# Discover tasks without designing a winner

Start with work whose success matters to you. Difficulty is measured later, with
a trustworthy grader and a small model pilot. A long prompt, large diff, many
files, or several repair commits does not establish difficulty.

Keep three lanes: representative routine work, consequential challenge cases,
and work needing manual or device observation. Keep the routine lane even when
all candidates pass it; it can inform cost and latency choices. A challenge-only
set cannot estimate performance on your whole workload.

## 1. Retrieve leads locally

Run these from the framework environment and save outputs in your private pack:

```sh
bench mine incidents ~/code/project --since 2026-06-01 \
  --limit 250 --lookback 25 --window-days 14 --json > ../private-benchmark/incidents.json
bench mine struggles ~/.codex/sessions --source codex --mode interactive \
  --since 2026-06-01 --json > ../private-benchmark/corrections.json
bench mine struggles ~/.claude/projects --source claude --mode interactive \
  --since 2026-06-01 --json > ../private-benchmark/claude-corrections.json
```

`incidents` reads the current HEAD's first-parent, non-merge commits. A later
repair word plus overlapping source paths creates a possible link. Episode
bounds prevent a chain of nearby links from becoming months of unrelated work;
cross-episode links remain available for review. Documentation/asset/lock-only
overlap and initial repository creation do not create links. There is no
file-count ceiling and no test-presence filter. Unlinked commits remain in the
output so reviewers can nominate missed work. Squashed commit bodies, side
branches, renames and uncommitted attempts need separate inspection.

`struggles` finds visible user corrections after an assistant reply, such as an
unresolved issue or retry request. It exports evidence locations and hashes, not
assistant reasoning, tool logs or text excerpts. `--include-excerpts` explicitly
opts into short user excerpts. Benchmark sessions are excluded even with
`--mode all`. Unknown and automated modes are excluded by the default interactive
filter; inspect the exclusion counts and use an explicitly labelled wider scan
when appropriate. Archived transcript directories can be scanned separately.

Neither command uploads data or executes repository/transcript instructions.
Both use language heuristics with false positives and false negatives. A retry
may mean an unavailable account, a preference change or a misunderstanding.
Paths, subjects, hashes and project metadata are private even without excerpts.
Review the original source before treating anything as failed work.

## 2. Turn a lead into an incident card

Copy [the review template](templates/INCIDENT_REVIEW.md) into the private pack.
For each lead, establish the original user need, the exact pre-change revision,
actual failed attempts, the eventual outcome and the environment in which it was
observed. Distinguish your own incidents from upstream dependencies you use.
Split unrelated repairs that merely touch a shared module. Group multiple
variants of one incident as one family for holdout and uncertainty analysis.

Keep an exclusion ledger, with a reason for every reviewed candidate: routine,
unrelated repairs, missing request, irreproducible environment, duplicate family,
device coverage unavailable, or qualified for capture. Do not discard tasks
because a favored model fails, or select only tasks another model failed.
Record scan bounds and retain manually nominated work without keyword matches.

## 3. Preserve the cause of the difficulty

Prefer the original source tree and existing entry points. Write an extraction
ledger: what was retained, removed, provided to the agent, simulated or left
unobserved? Explain how each change could make the task easier or change success.
Supplying an API scaffold can remove design and discovery; reducing a UI race to
a boolean helper can remove the race. Keep a physical task in a manual/device
lane when a faithful automatic environment is unavailable.

Make the prompt sufficient and fair, without exposing solution code or held-out
answers. Pin dependencies and tool versions. Test setup and output capture in
fresh checkouts. An upstream historical fix is a candidate reference, not proof
that the acceptance contract is achievable or correctly specified.

## 4. Challenge the grader before the models

Map every requirement to an observable outcome, relevant regression cases and
at least one plausible mistake. Include boundaries that survived a simplified
happy-path test: shared references, partial external effects, restart durability,
in-flight writes, stale state, user edits and ownership boundaries as relevant.

Calibrate the reference, unchanged base and deliberately incomplete fixes twice.
Then try to escape the grader with additional plausible wrong implementations.
For each escape, retain the patch and old grade, add the missing assertion, and
show that the new check fails for the intended behavior. Repeating the same
controls many times does not expand coverage.

Replay actual failed fixes on the same frozen base where possible. A patch-apply
error or unrelated compilation failure does not demonstrate that the behavioral
oracle detects the incident. Record any adaptation. Check at least one materially
different valid solution or document the missing alternative-solution review.
Preserve logs and hashes. Same-author review is useful but is not independent
review; name the author/reviewer roles and leave independent review pending if it
has not happened. These are evidence states, not an invented approval ceremony.

If an escape is found after model outputs exist, preserve the original scores
and run the corrected checks on every unchanged artifact. Report this as a
derived post-output audit. If the prompt changes, run a new matched cohort.
Never infer that a model failed merely because a hypothetical wrong patch passed.

## 5. Pilot before expanding

Run an edit-and-test access smoke for every exact configuration, then freeze a
small pilot with equal prompts, tools, effort settings and generous time budgets.
One or two trials can expose a ceiling or broken transport; they cannot establish
reliability. Use a new snapshot for changed inputs. Keep quota and authentication
interruptions separate and retain all attempts.

```sh
bench --tasks ../private-benchmark/pilot-tasks \
  --configs ../private-benchmark/configs/pilot.yaml \
  --runs ../private-benchmark/runs run --snapshot incident-pilot --trials 1 --strict
bench --runs ../private-benchmark/runs \
  pilot-review --snapshot incident-pilot --json > ../private-benchmark/pilot-review.json
```

`pilot-review` requires a frozen manifest and complete matched task/config/trial
coverage for at least two configurations. It checks result locations, records
manifest/result hashes, and reports these states:

| State | Next action |
| --- | --- |
| `saturated` | Audit escapes and extraction losses; retain useful routine work and discover independent challenge incidents. |
| `all_failed_review_contract_and_environment` | Recheck reference, grader, task scope, environment and budget before claiming hardness. |
| `needs_execution_or_grader_review` | Inspect unknown execution, nonzero exits, timeouts, capture and grading errors. |
| `observed_separation` | Inspect actual failures; a pass-count difference is a pilot observation, not significance or a winner. |
| `within_config_variation_only` | All configurations have equal pass counts with mixed outcomes; investigate reliability. |

`--require-signal` exits 2 if there is no observed between-configuration difference
or any task needs execution/grader review. It is optional and appropriate for a
challenge-lane workflow, not a universal task admission rule. A detected signal
still requires reviewing universal failures, individual assertions and grading
limitations. The command does not certify isolation, log semantics or task quality.

## 6. Freeze fresh work for the comparison

Use pilot tasks for development and fresh independent incident families for the
final comparison. Reserve holdouts before inspecting model outputs. Tuning a
prompt on one incident then testing its follow-up fix is not an independent
holdout. Record family assignments and deviations even if the suite is small.

Only expand the matrix once the task and grader evidence justify it. Keep every
pilot, exclusion, correction and retry cohort. Report routine and challenge lanes
separately, with physical/manual limits and cost basis explicit. If all models
continue to pass, report that result; do not invent requirements to manufacture
the desired ranking. See [methodology](METHODOLOGY.md) for uncertainty and routing.
