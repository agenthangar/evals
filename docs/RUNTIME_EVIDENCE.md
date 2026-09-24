# Evaluating behavior that a build cannot prove

Start with a failure someone experienced in their own work. Translate the
request into observable outcomes before choosing tests. A successful build,
an internal state flag or a candidate's own test report does not establish that
the user saw feedback, could interact, or received fresh sensor data.

Use the [runtime audit worksheet](templates/RUNTIME_AUDIT.md) alongside the
[incident review](templates/INCIDENT_REVIEW.md). Keep actual source captures,
recordings, user data and model outputs in your private task pack.

## Map each requirement to the boundary it needs

| Requirement | Observe | Insufficient substitute |
| --- | --- | --- |
| Feedback during slow work | Recorded rendered frames while the real operation is active | A loading flag becoming true |
| Responsive interaction | Input event to visible response, with synchronized clocks | An animation declaration or background task name |
| Main-thread availability | A separately scheduled main-queue probe during real work | Completion time alone |
| Reliable replay | Repeated user actions, completed transitions and new inputs reaching the next round | Navigating to a game screen once |
| Capture handoff | The successor receives fresh samples after the outgoing owner stops | A mock's `isRunning` value alone |
| Physical preview or mirroring | Device capture, displayed preview and receiving display together | A simulated external-display flag |

Queue scheduling is a useful responsiveness diagnostic, but it is not touch
latency. Decoded-pose fixtures can exercise ownership and recognition logic, but
they do not exercise image inference. State these differences in the result.

## Loading and responsiveness protocol

1. Freeze the real workload: data size, dependencies, operation, persistent
   store state, build mode, runtime and device. Use synthetic user records.
   Keep production computation and persistence in the measured path. Do not
   replace expensive work with a sleep to prove responsiveness.
2. Exercise both initial loading and refresh with existing content. Check the
   completed content and persistence as well as the progress UI. Add cancellation,
   error and stale-result cases when the original request requires them.
3. Record operation start/end on a monotonic clock. Record rendered pixels with
   an independently anchored clock. Measure and retain clock alignment error.
   Sample frames well inside active work; do not make a precise first-frame
   claim from coarse snapshots. If a deadline is contractual, capture densely
   enough to establish it within the clock uncertainty.
4. Schedule responsiveness probes independently of the work under test. Report
   the probe cadence, count and delays. A blocked UI can delay its own timer,
   making an entirely UI-owned measurement misleading.
5. Set acceptance limits from the actual product requirement before seeing
   candidate measurements. Report observations and uncertainty, not just a
   binary result. Verify that instrumentation does not insert a yield or move
   the operation to a different executor.

Qualify the grader against an unchanged failing baseline and a working control
under the same conditions. A minimal control can isolate a scheduling cause,
but disclose when it was derived from a candidate. It is not an independent
valid solution or an independent review. Use deliberately wrong controls, such
as visible feedback with blocked interaction or responsive work with hidden
feedback, to establish that both requirements matter.

## Replay and ownership protocol

Exercise each actual entry point: button, recognized gesture, next participant
or phase, and teardown/reentry. Repeat enough cycles to expose stale subscriptions
and late cleanup; choose and freeze the count before model grading. Check both
that transitions finish and that fresh data reaches the new consumer. Automatic
game progression can make replay appear healthy despite disconnected inputs.

For an ownership race, start a successor before stopping the old consumer, then
deliver a new sample. Assert that the successor receives it and that capture
eventually stops after the final owner leaves. Instantiate controllers as the
application does, including dependency arguments that select the production
path. Test implementations with different ownership designs where possible.

Use controlled adapters only at documented boundaries. Keep the actual
subscription, scheduling, recognizer and controller path above the adapter.
Verify negative cases such as incomplete gestures and a disconnected consumer.
UI replay tests and stream-delivery tests are complementary; separate tests do
not establish an uninterrupted physical end-to-end chain.

Preflight the runtime independently. Missing sensor hardware, unavailable model
assets or a failed reference environment must not count as model failures.
If image inference is unavailable, retain that diagnostic and mark inference
unscored. A separate decoded-input lane may still be useful, with its narrower
contract visible. Physical camera, preview synchronization, network mirroring
and end-to-end latency stay unscored until directly observed.

## Qualify, preserve and report

Run controls and unchanged candidate artifacts at least twice under matched
conditions. Serialize tests sharing a device. Require negative controls to fail
the intended behavioral assertion, rather than compilation, missing symbols or
unavailable infrastructure. A generous execution budget does not excuse missing
evidence, and an intentionally short assertion deadline must match the contract.

Freeze and hash the source patch, evaluator, adapter, workload and environment.
Keep per-attempt logs, measurements, recordings, assertions and excluded attempts.
Archive only necessary evidence; omit credentials, signed URLs, private reasoning
traces and unrelated data. Preserve tool versions and a replay command.

Report two separate questions:

- **Covered behavior:** passed, failed or unscored, with observations per
  requirement and the control evidence that qualifies the assertion.
- **Whole task:** pass only when all mandatory requirements are qualified and
  observed; fail when a qualified mandatory assertion fails; otherwise unscored.

A known mandatory failure can establish task failure even when other requirements
remain unobserved. Passing all simulator checks cannot establish a task pass when
physical requirements remain uncovered. Do not silently drop unknowns from a
pass-rate denominator.

These are reporting conventions for task authors, not additional native task YAML
fields or CLI result states. The current runner's command checks are binary.
Keep incomplete tasks out of an admitted full-task comparison, or explicitly
publish a narrower task contract and report that lane separately. Keep the
requirement-level audit as a sidecar artifact until all required checks exist.

When an evaluator changes after outputs exist, retain the old result and grader,
record why the new check is justified by the original request, and regrade every
unchanged artifact in the affected cohort. Label the result a post-output audit.
Changing the prompt or repairing candidate code requires a new generation cohort.
One observed failure improves diagnostic value; it does not prove general task
hardness, model reliability or a winner for another user's workload.
