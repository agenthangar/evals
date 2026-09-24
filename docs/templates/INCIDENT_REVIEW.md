# Incident review: <private task title>

- State: discovery / captured / grader-qualified / pilot-reviewed / holdout
- Lane: routine / challenge candidate / manual-device
- Family ID and split: <one real incident; development or untouched holdout>
- Relevance: <frequency, impact, own work or upstream dependency>
- Provenance: <request location/date/hash, source repo, full base/fix revisions>
- Discovery limits: <query/window, missing history, manual nomination>
- Review: <author, independent reviewer or explicitly pending>

## Source evidence

Describe the original need and observed failure. Separate user reports, commit
descriptions, reproduced behavior and unverified inference. Include actual failed
attempt revisions and explain how they differ from the eventual reference.

## Extraction ledger

| Boundary or context | Retained / changed / omitted | Effect on difficulty and evidence |
| --- | --- | --- |
| <existing call chain> | <original source, adapter, supplied interface> | <what remains observable> |

Record toolchain, dependencies, setup, isolation, clocks, external-service/device
requirements and the immutable artifact hashes. Keep private data out of public
framework examples.

## Requirement-to-evidence map

| Agent-visible requirement | Independent observed outcome | Regression / plausible mistake | Known limits |
| --- | --- | --- | --- |
| <behavior> | <assertion/artifact> | <boundary> | <coverage gap> |

## Grader qualification

| Candidate | Provenance / patch hash | Old check | New check | Intended failure evidence |
| --- | --- | --- | --- | --- |
| Reference | <historical or adapted> | <result> | <two runs> | <none> |
| Unchanged base | <revision> | <result> | <two runs> | <behavior> |
| Real failed fix | <revision/replay adaptation> | <result> | <two runs> | <behavior, not accidental apply error> |
| Additional escape probe | <plausible wrong patch> | <result> | <two runs> | <assertion/log> |
| Different valid solution | <implementation or pending> | <result> | <result> | <validity rationale> |

Record same-author and independent review separately. If reviewing after outputs,
link original scores and regrade every unchanged candidate without overwriting.

## Pilot and decision

- Access smoke: <exact configurations, observed execution, separate costs>
- Frozen pilot: <manifest, toolchain, budget, results and hashes>
- Diagnostic: <pilot-review states; inspect the underlying checks>
- Exclusions / interruptions / grader repairs: <retained evidence>
- Decision: <routine, further capture, qualified challenge candidate, manual lane>
- Fresh holdout families reserved before outputs: <IDs or explicitly none yet>
- Remaining uncertainty: <not a proven hard task or model ranking until measured>
