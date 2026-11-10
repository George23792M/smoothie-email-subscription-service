# MCP integration

## PostgreSQL domain tools

`PostgresMCPClient.call` opens an authenticated streamable HTTP MCP session per attempt, initializes it under a timeout, and validates structured results. It rejects credential-bearing URLs and non-loopback HTTP, and maps tool/transport failures to safe `PostgresMCPError` categories, including uncertain outcomes. `PostgresWorkflows` supplies typed customer, claim, completion, history, batch, readiness and provisional template operations. A bounded, jittered retry policy exists for transient failures of internally verified read-only tools, but `VERIFIED_READ_TOOLS` is empty: currently all tools are called once. No blind mutation retry or automatic reconciliation is implemented.

The optional `tests/mcp/test_postgres_protocol.py` starts a loopback server from a separately configured checkout with fake database functions; it is skipped without `POSTGRES_MCP_TEST_ROOT` and `POSTGRES_MCP_TEST_PYTHON`. This is not a real database or delivery integration test.

## Legacy email and escalation tools

`app/mcp/mcp_client.py` uses LangChain `MCPAdapter` and chooses a healthy `workflow_service` replica from `MCPRegistry`; graph delivery and escalation use this separate path. `initialize_mcp_registry` exists but `main.py` does not call it. The prior scan found the registry health checker uses placeholder checks; that behavior was not revalidated in this incremental scan. Email readiness is currently always false and prevents normal workflow processing.

The separate `app/mcp/email_client.py:EmailMCPClient` is a disabled, unintegrated proposal; its real acceptance contract has not been verified. See [email integrations](email.md).

Sources: app/mcp/postgres_client.py, app/services/postgres_workflows.py, app/mcp/email_client.py, app/mcp/mcp_client.py, app/mcp/registry.py, app/mcp/config.py, app/core/config.py, main.py, app/services/delivery_readiness.py, tests/mcp/test_postgres_protocol.py, tests/mcp/test_postgres_retry_policy.py
Verified: 2026-11-10
