# Incident log

Evidence: the 2026-11-09 run summary supplied by the user; `.ai/plans/20261109-welcome-email-redesign.plan.yaml`; the current working tree and tests. Earlier intermediate failures and corrections are reported in the run summary, not preserved independently in the current tree. Root-cause chains below distinguish hypotheses from verified outcomes.

## INC-0001 | 2026-11-09 | Integration boundary and outcome semantics corrected
- Agent / phase: planner / requirements
- Category: user-requirement
- Symptom: The user reports correcting an initial direct-provider design to a separate email MCP service and clarifying that `email_sent` means provider acceptance, not inbox delivery. The current plan reflects both corrections.
- Root cause: Hypothesis, five-whys chain: the design needed correction because the integration boundary and outcome meaning were wrong; they were wrong because provider implementation and service responsibility were conflated; the distinction was not captured as an explicit requirement; the initial requirements handoff did not establish these semantics; no verified pre-plan boundary-and-outcome confirmation is evident. The initial plan and handoff are unavailable for independent confirmation.
- Resolution: The revised plan specifies a separate provisional email MCP contract and acceptance semantics; implementation and external verification remain incomplete.
- Prevention: L-001
- Recurrence: 1 (2026-11-09)
- Status: mitigated

## INC-0002 | 2026-11-09 | Unagreed template policy stalled local implementation
- Agent / phase: planner and implementer / planning and implementation
- Category: planning
- Symptom: The user reports that implementation stopped after T0a–T1 because placeholder syntax and HTML policy were treated as unagreed; the plan was revised to permit a user-approved provisional contract. The current plan records the provisional policy and a closed production gate.
- Root cause: Hypothesis, five-whys chain: T2 onward stalled because template behavior lacked agreement; agreement was treated as necessary even for local fake-based work; provisional implementation and production authorization were not initially separated; the plan did not identify a safe local contract with an explicit release gate; the planning handoff lacked a decision for handling external uncertainty. The earlier plan is unavailable for independent confirmation.
- Resolution: The revised plan permits the provisional single-placeholder, restrictive HTML contract for local work while requiring external owner agreement before release. T2 and T3 are now marked done, not the entire delivery path.
- Prevention: L-002
- Recurrence: 1 (2026-11-09)
- Status: mitigated

## INC-0003 | 2026-11-09 | Deadline cancellation confused with external cancellation
- Agent / phase: implementer / retry policy
- Category: implementation
- Symptom: The user reports an initial targeted result of 8 passed and 1 failed due to AnyIO deadline cancellation misclassification, followed by 9 passed after correction. The current PostgreSQL client explicitly recognizes timeout cancellation context; the intermediate failure output is unavailable.
- Root cause: Hypothesis, five-whys chain: the deadline case failed because cancellation context was classified incorrectly; a deadline-generated cancellation was treated like external cancellation; the classifier did not account for the timeout library's exception chaining; its behavior was not initially verified against a real deadline; the implementation check did not require a separate deadline-versus-caller-cancellation probe.
- Resolution: The current client includes a timeout-context distinction. The plan reports a later full-suite pass; it does not identify a dedicated real-deadline regression test.
- Prevention: L-003
- Recurrence: 1 (2026-11-09)
- Status: mitigated

## INC-0004 | 2026-11-09 | Post-invocation error exposed raw details
- Agent / phase: implementer and tester / provider adapter
- Category: security
- Symptom: The user reports that a post-invocation `ValueError` leaked raw details, with targeted 89 passed/1 failed and full 340 passed/1 failed/1 skipped. Current provider tests inject such an error and check sanitized output, suppressed chaining, a closed gate and no resend.
- Root cause: Hypothesis, five-whys chain: details escaped because the error was not translated at the invocation boundary; the handled exception set omitted a possible value error; the set was not checked against failure modes after the side effect; the initial tests did not exercise this boundary case; boundary verification did not enumerate both expected errors and uncertain-side-effect behavior.
- Resolution: The current adapter catches `ValueError` narrowly and raises a sanitized unknown-outcome error; it closes the reconciliation gate in `finally`. The plan records the targeted and full retest as passing.
- Prevention: L-004
- Recurrence: 1 (2026-11-09)
- Status: mitigated

## INC-0005 | 2026-11-09 | First security fix used a prohibited broad catch
- Agent / phase: implementer / fix loop
- Category: implementation
- Symptom: The user reports that the first fix for INC-0004 used a broad `Exception` catch despite the no-broad-catch rule and was returned for a narrow correction. The intermediate patch is unavailable; the current adapter catches explicit exception types, and tests require unexpected programming errors and cancellation to propagate.
- Root cause: Hypothesis, five-whys chain: the first fix violated the catch rule because it generalized the error translation; the fix optimized for containing the reported leak; programming-error and cancellation behavior were not included in the initial correction's verification; fix-loop handoff did not enforce all applicable exception constraints as acceptance checks; the workflow lacked a mandatory rule-compliance check on patches, not just passing targeted tests.
- Resolution: A narrower correction was applied; the plan records a 47-pass targeted retest and 346 passed/1 skipped full retest.
- Prevention: L-005
- Recurrence: 1 (2026-11-09)
- Status: mitigated

## INC-0006 | 2026-11-09 | Passing tests did not complete the delivery redesign
- Agent / phase: engineer and implementer / orchestration and delivery
- Category: orchestration
- Symptom: The plan remains `in_progress`: T4 is in progress, T5–T10 are pending, and T11 is blocked. The old graph remains invoked in the workflow code and readiness returns false. The plan reports a passing retest and a skipped cross-repository protocol check, not an end-to-end delivery.
- Root cause: Local completion reason is not established by available evidence. Hypothesis, five-whys chain: the requested delivery path is incomplete because dependent integration tasks have not been implemented; those tasks remained pending after a partial handoff; the handoff did not result in a completed continuation; the run ended with partial work rather than a verified task-by-task completion; the available evidence does not establish why continuation stopped. Separately, T11 cannot release because external contracts, acceptance semantics and durable reconciliation are unverified; this does not explain all pending local tasks.
- Resolution: No complete delivery resolution this run. The gate remains closed; the plan retains local task states and the separate external verification blocker.
- Prevention: L-006
- Recurrence: 1 (2026-11-09)
- Status: open

## INC-0007 | 2026-11-09 | Unintended line-ending change during agent customization
- Agent / phase: general-purpose agent / approved instruction edits
- Category: tooling
- Symptom: The user reports that a patch normalized one unrelated planner line ending and that the agent restored it. The current planner file has mixed line endings; the original bytes and intermediate patch were not available for comparison.
- Root cause: Hypothesis, five-whys chain: an unrelated byte changed because the patch altered a line ending; the edit did not preserve all original bytes; its line-ending behavior was not verified against the original before application; the verification used matching byte counts after removing additions rather than a byte-for-byte comparison; the reported process did not establish exact preservation of unaffected content. The patch mechanics and original verification steps are not independently available.
- Resolution: The agent reported restoring the line ending and matching the original byte count after removing additions in memory. Exact restoration is not independently established by a byte count; current frontmatter parses successfully.
- Prevention: L-007
- Recurrence: 2 (2026-11-09, 2026-11-10); repeated verification gap, not a confirmed second byte change.
- Status: mitigated

### 2026-11-10 recurrence: dirty-file baseline unavailable
- Agent / phase: implementer / implementation
- Symptom: The run reports that CRLF was preserved but original dirty files were not captured byte-for-byte before edits; exact preservation of unrelated bytes cannot be independently established.
- Root cause: Hypothesis, five-whys chain: preservation is unproved because no original byte baseline remains; it was not retained before edits; review can compare against Git HEAD but not the pre-run dirty state; the handoff did not establish a pre-edit baseline; compliance depended on an after-the-fact comparison that could not reconstruct prior dirty bytes. No additional unrelated byte change is established.
- Resolution: No retrospective byte comparison is possible; the limitation is reported. L-007 now requires the baseline before the first edit.

## INC-0008 | 2026-11-10 | Knowledge base lags worktree changes
- Agent / phase: project-analyzer and engineer / KB refresh and final verification
- Category: kb
- Symptom: The KB refresh records that the prior KB omitted provisional delivery components and the inactive verified-read retry policy. After the focused implementation, `docs/kb/architecture.md` still says execution invokes the graph, and `docs/kb/components/workflow-pipeline.md` still describes claim processing, while current `execute_claim` unconditionally rejects. The refresh predated the focused implementation; no post-implementation KB refresh is evidenced.
- Root cause: Hypothesis, five-whys chain: KB descriptions lagged source because changed and untracked components or later implementation changes were absent from the published descriptions; refresh coverage was tied to the state and scope at scan time; execution changed after that scan; the final handoff did not reconcile affected KB claims against the completed diff; the workflow lacked a verified post-change freshness check.
- Resolution: The earlier refresh documented the provisional components and empty retry allowlist. Focused-run execution descriptions remain stale; KB files are outside this postmortem's permitted edit scope.
- Prevention: L-008
- Recurrence: 1 (2026-11-10)
- Status: open

## INC-0009 | 2026-11-10 | Direct claim bypassed disabled delivery boundary
- Agent / phase: planner and implementer / execution boundary
- Category: security
- Symptom: The run reports that the pre-edit `execute_claim` independently fetched a customer and invoked the graph without a readiness guard. That pre-edit dirty version is unavailable for independent comparison; the focused plan specifically requires direct rejection, and the current implementation rejects without inspecting inputs.
- Root cause: Hypothesis, five-whys chain: a direct entry point could reach side effects because its caller's gate was not applied there; the guard was associated with normal orchestration rather than every callable execution path; direct invocation was not covered as a disabled-state boundary; the original acceptance checks did not require a side-effect-free direct-call probe; entry-point enumeration was not enforced for gated workflows.
- Resolution: The current `execute_claim` rejects unconditionally; focused regression tests exercise direct calls with untouchable inputs under both readiness states. The run reports the full suite passed.
- Prevention: L-009
- Recurrence: 1 (2026-11-10)
- Status: mitigated

## INC-0010 | 2026-11-10 | Offline build selected an unavailable pinned interpreter
- Agent / phase: tester / build verification
- Category: tooling
- Symptom: The run reports that the first offline build could not find the pinned Python and succeeded after explicitly selecting the project interpreter. The pin is 3.14.7 and the existing project interpreter reports 3.14.6; intermediate command output is unavailable.
- Root cause: Hypothesis, five-whys chain: the first build failed because interpreter resolution selected an unavailable pinned version; the offline environment could not provision it; an existing compatible project interpreter was not selected explicitly; the build invocation assumed the pin was locally resolvable; the build preflight did not check both the selected interpreter and offline availability.
- Resolution: The tester reports using the project interpreter and passing the build. The build also regenerated ignored egg-info; no resulting defect or loss is established.
- Prevention: L-010
- Recurrence: 1 (2026-11-10)
- Status: mitigated

## INC-0011 | 2026-11-10 | New regression test exceeded function-length convention
- Agent / phase: tester and refactorer / test and refactoring
- Category: refactoring
- Symptom: The run reports a newly added focused test was 46 lines because it embedded a subprocess probe. The current test uses a module-level probe and fits under 30 lines. An unrelated pre-existing API test remains over the limit and was not refactored in this run.
- Root cause: Hypothesis, five-whys chain: the test exceeded the limit because a complete probe was embedded in its function; the subprocess scenario was written inline; function length was not checked after adding the test; the check was deferred to refactoring; test authoring did not include a changed-function length check before handoff.
- Resolution: The refactorer reports extracting the probe and rerunning the full suite: 355 passed, no skips, using a fake database protocol; the build passed. Intermediate outputs are unavailable. The untouched legacy test remains outside this focused change.
- Prevention: L-011
- Recurrence: 1 (2026-11-10)
- Status: mitigated
