# Email integrations

The primary LangGraph send node (`app/graph/workflow.py:send_email_node`) sends generated content through `app/mcp/mcp_client.py:send_email`. The MCP tool receives recipient address/name, subject, body, and correlation ID.

This path is not available for normal processing: `app/services/delivery_readiness.py:is_delivery_ready` always returns false, blocking triggers before claims and preventing scheduler startup. Readiness reports unavailable until delivery is implemented and verified.

A separate provider adapter exists:
- `app/services/email/email_client.py:EmailClient` defines a provider protocol.
- `app/services/email/resend_email_client.py:ResendEmailClient` calls the Resend SDK.
- `app/services/email/service.py:EmailService` renders a welcome template and submits a provider payload.

The separate `EmailService` is not instantiated elsewhere in the application source. It requests `welcome_email.html`, while the scanned `app/templates/email/` directory contains text prompt files rather than that HTML template. Its operational status is therefore unverified and it is not the graph's delivery path.

## Provisional welcome path

- `PostgresWorkflows.active_welcome_template` validates a proposed active-template response. `render_welcome` accepts only `{{first_name}}`, validates a restricted balanced HTML tag/entity policy, escapes the name in HTML, and enforces length limits.
- `EmailMCPClient` defines a proposed request and fake response contract, but real delivery is hard-disabled. If its gate is artificially opened, it invokes once, reports an unknown outcome and closes the reconciliation gate; accepted fake responses do not establish provider acceptance or delivery.
- `DeliveryLimits` provides process-local batch, concurrency and rolling-rate bounds; `get_delivery_limits` requires `single_worker_exclusive` mode. None of these new components is wired into the existing workflow or scheduler. Cross-replica rate enforcement and actual provider semantics remain unverified.

The generator prompts contain customer context including email and customer ID, while the system prompt explicitly instructs the model not to reproduce those values in the message body. `LANGSMITH_ENABLED` defaults true in settings and the LLM client documentation describes prompt/response tracing; production tracing/data-retention configuration should be verified before sending customer data.

Sources: app/graph/workflow.py, app/mcp/mcp_client.py, app/mcp/email_client.py, app/services/postgres_workflows.py, app/services/delivery_readiness.py, app/services/workflow_execution.py, app/core/scheduler.py, app/services/email/, app/templates/email/, app/agents/generator/prompts.py, app/core/config.py, app/agents/generator/llm_client.py, tests/services/test_welcome_provider.py, tests/services/test_welcome_rendering.py, tests/services/test_delivery_limits.py
Verified: 2026-11-10
