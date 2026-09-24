# Runtime audit: <private task ID>

This worksheet is a sidecar report, not a task YAML schema. See
[runtime evidence](../RUNTIME_EVIDENCE.md) for the protocol.

- Original request and frozen contract: <private references and hashes>
- Candidate artifact: <unchanged patch hash and original attempt>
- Evaluator version and hash: <revision>
- Timing: <before outputs / derived post-output audit and rationale>
- Environment: <runtime, build mode, device, workload, store state, dependencies>
- Replay command: <private environment setup and grading command>
- Author / independent reviewer: <roles, or pending>

## Coverage and measurement

| Mandatory requirement | Actual execution path | Observation and limit | Coverage gap |
| --- | --- | --- | --- |
| <user behavior> | <real components and substituted boundary> | <assertion, units, threshold, artifact> | <remaining unknown> |

Record every adapter and its effect on the claim. For timing, include monotonic
clock anchors, alignment uncertainty, probe cadence and sampling coverage. For
repeated actions, include cycle counts and evidence of new data reaching each
consumer. Identify scripted completion paths that could mask disconnected input.

## Calibration and attempts

| Artifact / provenance | Trial | Behavioral result | Intended assertion and evidence |
| --- | --- | --- | --- |
| Baseline | <number> | <result> | <observed defect> |
| Working control | <number> | <result> | <same workload and instrumentation> |
| Plausible incomplete fix | <number> | <result> | <not merely build failure> |
| Different valid solution | <number or pending> | <result> | <design independence> |
| Candidate, unchanged | <number> | <result> | <observations> |

Disclose candidate-derived controls. Preserve failed preflights, grader mistakes,
amendments, reruns and exclusions without counting them as candidate failures.

## Result

- Covered behavior: <pass / fail / unscored per requirement>
- Whole task: <pass / fail / unscored, with derivation>
- Mandatory failures: <qualified assertions, or none observed>
- Remaining requirements: <unobserved, unqualified or physical/manual coverage>
- Comparison limits: <repetitions, correlated incidents, shared resources>
- Evidence archive and checksums: <private locations>
- Original result preserved at: <reference if this is a regrade>
