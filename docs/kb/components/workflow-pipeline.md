# Workflow pipeline and agents

## Orchestration

`app/graph/state.py:PipelineState` defines the shared TypedDict state, including customer data, guardrail outcomes, generated/refined content, critic outcome, and delivery status. `app/graph/workflow.py:build_workflow` wires generator → critic → final guards → send, with critic → refiner → critic looping and manual-review escalation. `app/graph/executor.py:run_email_pipeline` initializes the state, invokes the compiled graph, and converts uncaught exceptions to a failed state.

## Agent responsibilities

- Generator (`app/agents/generator/`): builds customer context, renders system/task prompt templates, calls a cached `ChatOpenAI` client with Tenacity retries, parses an `EmailContent`, and runs output checks.
- Critic (`app/agents/critic/`): deterministic checks for sensitive content, phishing-like language, health claims, formatting, and personalization. For moderate issues it calls Jev through `typesafe_sdk`.
- Refiner (`app/agents/refiner/node.py`): applies critic feedback via a second LLM call and loops to the critic; maximum refinements is three.
- Guardrails (`app/guardrails/`): input data checks and generated/final email checks.

## Confirmed execution blockers and risks

1. The graph contains no input-check node. `generator_node` returns without generating if `input_guardrail_passed` is false or absent; `run_email_pipeline` does not set this flag in its initial state. Thus the usual graph path does not generate an email.
2. `OutputGuards` references `max_body_lenght`, which is not a field of `OutputGuardRailConfig`, and `enable_html_validation`, which is also absent. Subject validation or the HTML validation call can raise `AttributeError`; the subject comparison reads the missing attribute regardless of subject length.
3. The input guard implementation also has incompatible references: `enabled_pii_detections` does not match config `enable_pii_detection`, multiple result lookups use `serverity` rather than `severity`, and `detect_sql_injection` is called with an unsupported `field` argument.
4. The former lowercase `"sent"` comparison and unconditional success aggregation are no longer present: `execute_claim` requires `"SENT"` and otherwise returns a failure requiring reconciliation. The delivery gate currently prevents normal execution before any claim.
5. If `typesafe_sdk` is unavailable, the Jev client returns a synthetic `"SEND"` recommendation for moderate issues. The package is not listed in `requirements.txt`, so a missing optional dependency can bypass the intended review decision.
6. `app/templates/email/welcome_email_task.txt` instructs the model not to invent subscriber benefits, but its examples promise recipes, offers, wellness tips, and plan-specific product access that are not established by the runtime customer data.

The project virtual environment suite passed 260 tests, with one optional cross-repository protocol test skipped, on 2026-11-09. It does not establish that the real graph, guardrails, database, or MCP delivery path works end to end.

Sources: app/graph/state.py, app/graph/workflow.py, app/graph/executor.py, app/agents/generator/, app/agents/critic/, app/agents/refiner/node.py, app/guardrails/, app/services/workflow_execution.py, requirements.txt, tests/
Verified: 2026-11-09
