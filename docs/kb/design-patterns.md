# Design patterns

## State machine / conditional workflow

`app/graph/workflow.py:build_workflow` constructs a LangGraph `StateGraph` with named agent/safety nodes and conditional routes. The critic chooses final checks, refinement, or manual review; the refiner loops back to the critic up to `MAX_REFINEMENTS`.

## Service and DAO layers

`app/services/workflow_service.py:WorkflowService` handles workflow-history and batch-status use cases. `app/dao/workflow_runs_dao.py:WorkflowRunsDAO` and `app/dao/batch_runs_dao.py:BatchRunsDAO` delegate reads to the injected `PostgresWorkflows` adapter. `app/api/workflows.py:get_workflow_service` injects DAO dependencies. This router/service/DAO layering resembles the FastAPI standards, although actual persistence is external.

## Adapter and protocol

`app/services/email/email_client.py:EmailClient` defines a provider-neutral protocol, implemented by `app/services/email/resend_email_client.py:ResendEmailClient` and consumed by `app/services/email/service.py:EmailService`. This path is separate from the graph's MCP-based `send_email_node`; no construction/use of `EmailService` was found elsewhere in the application.

## Singleton-style shared resources

`app/agents/generator/llm_client.py:_get_llm_client` caches `ChatOpenAI` clients by model. `app/mcp/registry.py:get_registry` and `app/core/scheduler.py:get_scheduler` hold shared instances. The former local database pool has been removed.

## Retry and resilience

`app/agents/generator/llm_client.py:call_llm_with_retry` uses Tenacity exponential backoff for timeout/connection exceptions. `app/mcp/mcp_client.py:_call_tool` records replica success/failure and translates tool errors into `ServiceException`.

`app/mcp/postgres_client.py:PostgresMCPClient` implements deadline-bounded, jittered retries only for explicitly verified reads and selected transient failures. The allowlist is empty, so this policy is currently dormant; mutations and unverified tools run once.

## Fail-closed gate and reconciliation

`app/services/delivery_readiness.py:is_delivery_ready` currently returns false; `workflow_execution.py:require_delivery_ready` and `scheduler.py:initialize_scheduler` prevent claims and scheduling until delivery is ready. `postgres_client.py:PostgresMCPClient.call` does not retry uncertain calls, while workflow execution and scheduler log identifiers for manual reconciliation.

## Important implementation caveats

- The MCP registry does not register services during `main.py` startup.
- The generated-email path does not currently initialize the input guardrail state.
- `EmailService` expects `welcome_email.html`, while the scanned email templates are `.txt`; this adapter path is not wired into the main graph.
- The new welcome renderer, email MCP client and process-local delivery limiter are also not wired into the execution path; their contracts are provisional.

Sources: app/graph/workflow.py, app/agents/refiner/node.py, app/services/workflow_service.py, app/services/workflow_execution.py, app/services/postgres_workflows.py, app/services/delivery_readiness.py, app/dao/, app/api/workflows.py, app/services/email/, app/agents/generator/llm_client.py, app/mcp/, app/core/scheduler.py, main.py, app/templates/
Verified: 2026-11-10
