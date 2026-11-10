# API and persistence

`app/api/workflows.py` defines trigger, customer history, and batch-status routes under `/api/workflows`; `main.py` adds `/api`, producing `/api/api/workflows/...`.

All workflow routes use `require_operator`: missing configured token returns 503; invalid bearer credentials return 401; authenticated requests share a process-local rolling limit of 60/minute (429). This is not a per-user or deployment-wide authorization/rate limit. `TriggerWorkflowRequest` accepts 1–100 UUIDs and only `NEW_REGISTRATION`. History validates a UUID and limits results to 1–100.

`get_workflow_service` injects MCP-backed DAOs. Triggers call `execute_workflow_for_customers`, which checks delivery readiness before claiming; currently this returns 503. History and batch status map `PostgresMCPError` to 503. Other trigger failures produce generic 500 responses. Scheduler and execution call `PostgresWorkflows` instead of issuing SQL directly.

Sources: main.py, app/api/auth.py, app/api/workflows.py, app/api/schemas/requests.py, app/services/workflow_execution.py, app/services/workflow_service.py, app/services/postgres_workflows.py, app/dao/workflow_runs_dao.py, app/dao/batch_runs_dao.py, app/services/delivery_readiness.py
Verified: 2026-11-09
