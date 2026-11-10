# Database

## Access and operations

PostgreSQL is accessed via an external authenticated MCP server, not a local asyncpg pool. The former `app/services/db_pool.py` and `app/services/db_service.py` are deleted. `PostgresWorkflows` exposes tools for customer lookup, registration claim/completion, batch creation/completion, history, readiness and provisional active welcome-template retrieval; `WorkflowRunsDAO` and `BatchRunsDAO` delegate history reads to it. `PostgresMCPClient` makes isolated streamable HTTP sessions with a timeout, without automatically retrying uncertain requests. Its bounded read retry policy is inactive because the verified-read allowlist is empty.

`RegistrationClaim` validates workflow type, running status and worker ownership; targeted claims additionally validate the customer ID. `PostgresWorkflows.customer` constructs the required `customer_name` from first and last names. `execute_claim` records completion only after a `SENT` pipeline result; uncertain claims, delivery, or persistence require manual reconciliation. The local service does not provide automatic recovery or an exactly-once delivery guarantee.

The external server owns actual SQL, schema, constraints, migrations and transactions. The README instructs operators to apply its registration schema and migrations 002 and 003; their contents and deployed state were not verified in this scan. Real database integration remains unverified.

Sources: README.md, app/mcp/postgres_client.py, app/services/postgres_workflows.py, app/services/workflow_execution.py, app/dao/workflow_runs_dao.py, app/dao/batch_runs_dao.py, app/core/scheduler.py, app/schemas/responses.py
Verified: 2026-11-10
