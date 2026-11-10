# Project lessons

- [L-001] agent: planner | category: user-requirement | status: active | seen: 1
  Rule: Before planning an integration, confirm the service boundary and the meaning of each externally visible success flag; distinguish provider acceptance from final delivery.
  Why: A reported initial design required user correction on both architecture and outcome semantics.
  Check: The plan names the responsible service and defines each success outcome without asserting unverified downstream guarantees.

- [L-002] agent: planner | category: planning | status: active | seen: 1
  Rule: For an unverified external contract, explicitly separate user-approved provisional local behavior from production prerequisites and keep real side effects gated.
  Why: Treating template policy as wholly unagreed reportedly blocked local implementation until the plan was revised.
  Check: Each provisional assumption states approval, permitted fake-based work, required external agreement and the closed release gate.

- [L-003] agent: implementer | category: implementation | status: active | seen: 1
  Rule: When classifying async failures, distinguish an actual deadline's internal cancellation from independent caller cancellation, including exception context and groups.
  Why: A deadline cancellation was reportedly misclassified during retry implementation.
  Check: Exercise a real timeout scope and a separately cancelled caller; verify timeout classification, cancellation propagation and retry limits.

- [L-004] agent: implementer | category: security | status: active | seen: 1
  Rule: Enumerate expected errors at each external side-effect boundary; sanitize their public errors and treat uncertain outcomes as non-retryable until reconciled.
  Why: A post-invocation value error reportedly leaked details instead of becoming an uncertain outcome.
  Check: Inject each expected failure, including malformed-value errors, and assert sanitized output and chain, gate closure and no repeat side effect.

- [L-005] agent: implementer | category: implementation | status: active | seen: 1
  Rule: Apply exception-handling restrictions to fix-loop patches; catch only justified exception types and preserve unexpected programming errors and cancellation.
  Why: A reported first security fix used a prohibited broad catch.
  Check: Inspect changed handlers for broad catches and test an expected error, an unexpected programming error and cancellation.

- [L-006] agent: engineer | category: orchestration | status: active | seen: 1
  Rule: Reconcile every task and integration path against the plan before declaring a run complete; distinguish unfinished local work from external release blockers.
  Why: A passing retest accompanied pending integration tasks and unverified external contracts.
  Check: Report each incomplete task, actual wiring, gate state and external verification separately; resume local work without claiming that fake-only tests prove delivery.

- [L-007] agent: all | category: tooling | status: RECURRING | seen: 2
  Rule: Before the first edit, retain each affected dirty file's exact bytes, including line endings, for comparison; preserve all bytes outside approved changes.
  Why: A prior unrelated line-ending change and a later missing dirty baseline left exact preservation unproved.
  Check: Compare the baseline byte-for-byte with the edited content after reversing only intended changes; if no baseline exists, report preservation as unverified.

- [L-008] agent: all | category: kb | status: active | seen: 1
  Rule: Refresh affected KB claims against tracked and untracked worktree changes, then recheck freshness after implementation.
  Why: A pre-implementation refresh cannot describe later execution changes.
  Check: Trace changed entry points and enabled policies into affected KB pages; refresh or explicitly report stale claims before handoff.

- [L-009] agent: implementer | category: security | status: active | seen: 1
  Rule: Apply disabled-state rejection at every callable execution entry point before data access or side effects, independently of upstream gates.
  Why: A reported direct claim path bypassed the normal readiness boundary.
  Check: Invoke each entry point directly with readiness false and mocked true; assert rejection before input inspection, data access, claims or outbound calls.

- [L-010] agent: tester | category: tooling | status: active | seen: 1
  Rule: Before an offline build, verify the selected Python is locally available and satisfies project requirements; select the existing project interpreter explicitly if appropriate.
  Why: Automatic resolution selected an unavailable pinned interpreter despite an available project environment.
  Check: Report the actual interpreter path and version, requirement compatibility, build command and outcome; disclose any pin mismatch.

- [L-011] agent: all | category: refactoring | status: active | seen: 1
  Rule: Keep newly added or changed test functions under the project's 30-line limit, extracting substantial subprocess probes when needed.
  Why: An inline probe made a new test exceed the stated convention until refactoring.
  Check: Measure changed test functions before handoff and identify pre-existing out-of-scope exceptions separately.
