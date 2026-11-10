# Infrastructure and configuration

## Runtime and dependencies

`pyproject.toml` requires Python >=3.11 and dynamically loads dependencies from `requirements.txt`; the previous empty-dependency and Python >=3.9 KB claims are obsolete. Requirements include FastAPI, Pydantic, LangGraph/LangChain, APScheduler, Resend, MCP >=2.3,<3, httpx2 >=2.12,<3 and anyio >=4,<5. Most other requirements lack upper bounds. The prior scan found `.python-version` 3.14.7, no CI workflow, container/deployment manifest or lock file; these areas were not rescanned in this incremental refresh.

`README.md` documents setup, separately administered PostgreSQL MCP migrations, TLS/network restrictions, process-local rate limiting, and operator reconciliation. Real database and delivery infrastructure are separate and unverified.

## Configuration names

`app/core/config.py:Settings` reads `.env`. Values are not recorded.

- PostgreSQL MCP/auth: `POSTGRES_MCP_URL`, `POSTGRES_MCP_TOKEN`, `OPERATOR_API_TOKEN`, `MCP_REQUEST_TIMEOUT_SECONDS`, `MAX_WORKFLOWS_PER_BATCH`.
- Provisional email MCP: `EMAIL_MCP_URL`, `EMAIL_MCP_TOKEN`, `EMAIL_MCP_TIMEOUT_SECONDS`.
- Delivery bounds and mode: `DELIVERY_CONCURRENCY`, `DELIVERY_RATE_COUNT`, `DELIVERY_RATE_WINDOW_SECONDS`, `DELIVERY_LIMIT_MODE`.
- Verified-read retry policy: `POSTGRES_READ_RETRY_ATTEMPTS`, `POSTGRES_READ_RETRY_BUDGET_SECONDS`, `POSTGRES_READ_RETRY_INITIAL_SECONDS`, `POSTGRES_READ_RETRY_MAX_SECONDS`. No tool is currently allowlisted for retries.
- Existing MCP and replica configuration: `MCP_SERVER_URL`; replica settings include `EMAIL_SERVICE_REPLICAS`, `CUSTOMER_SERVICE_REPLICAS`, `WORKFLOW_SERVICE_REPLICAS`, `ESCALATION_SERVICE_REPLICAS`, `METRICS_SERVICE_REPLICAS`.
- Providers, tracing and models: `OPENAI_API_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`, `MAX_RETRIES`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENABLED`, `GENERATOR_MODEL`, `CRITIC_MODEL`, `REFINER_MODEL`.
- Server: `HOST`, `PORT`, `ENVIRONMENT`, `DEBUG`, `ALLOWED_ORIGINS`.

`PostgresMCPClient` permits HTTP only on loopback and otherwise requires HTTPS; token settings are `SecretStr`. `main.py` mounts `/api/api/workflows`; the process-local scheduler runs every ten minutes only when delivery is ready, which is currently never. The legacy registry setup is not called by startup.

Sources: .python-version, pyproject.toml, requirements.txt, README.md, main.py, app/core/config.py, app/core/scheduler.py, app/mcp/config.py, app/mcp/postgres_client.py, app/services/delivery_readiness.py
Verified: 2026-11-10
