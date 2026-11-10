# Smoothie email subscription service

The service accesses subscription, workflow and batch data exclusively through
the authenticated postgres-mcp service. It does not open PostgreSQL connections.
The existing administrative API path remains `/api/api/workflows`.

## Important delivery limitation

Workflow execution and email delivery are unconditionally disabled, even if a
delivery readiness predicate reports ready. Trigger requests return HTTP 503
before acquiring claims; scheduler startup and direct batch invocation do not
create batches or claim work. The live application does not invoke the legacy
agent graph, fetch templates, or send email. Legacy agent and graph files and
their tests are retained, but are not part of the live execution path.

Template retrieval and sending through the separate email MCP service are
deferred to a future integration. The external service contracts, provider
semantics, and reconciliation procedures remain unverified release
prerequisites. Provider acceptance is not inbox delivery, and no automatic
recovery of uncertain work is provided. `/health` is liveness; `/health/ready`
returns 503 with email unavailable even when the database check succeeds.

## Proposed welcome template contract (unverified)

The application proposes calling PostgreSQL MCP tool
`get_active_email_template` with `{"template_name": "welcome"}`. Its proposed
response is `{"found": false}` when absent, or
`{"found": true, "template": {"active": true, "subject": "...", "html_body": "..."}}`
for an active template. Subject and HTML are limited to 200 and 65,536
characters respectively; unexpected fields, inactive records, malformed
responses, and failures are rejected without fallback. Identifiers, versions,
active-selection semantics, and the actual tool and schema are not agreed
with the external service owner. This proposed operation is not enabled for
retries and no delivery integration is verified.

## Setup

Use Python 3.11 or later and install with
`python -m pip install -r requirements.txt`. The interoperability check used Python 3.14.6 with
`mcp` 2.3.0 and `httpx2` 2.12.0 against postgres-mcp Python 3.12.13 and `mcp`
1.30.0. Follow the postgres-mcp README to apply the registration schema and
migrations 002 and 003 explicitly before running. Never use a production
database for tests.

Configure these environment variables using a secret manager or an untracked
`.env` file:

| Variable | Purpose |
| --- | --- |
| `POSTGRES_MCP_URL` | Trusted postgres-mcp streamable HTTP URL; HTTPS is required except for loopback. Defaults to `http://127.0.0.1:8001/mcp`. |
| `POSTGRES_MCP_TOKEN` | Postgres MCP bearer credential, at least 32 characters. |
| `OPERATOR_API_TOKEN` | Separate operator bearer credential, at least 32 characters. |
| `MCP_REQUEST_TIMEOUT_SECONDS` | Timeout for the complete MCP call; default 10 seconds. |
| `MAX_WORKFLOWS_PER_BATCH` | Maximum scheduled claims per run; default 10. |
| `MCP_SERVER_URL`, `OPENAI_API_KEY`, `RESEND_API_KEY`, `SENDER_EMAIL`, `MAX_RETRIES`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` | Existing application configuration required by settings. |

Run `python main.py`. All workflow routes require the operator bearer token;
the token grants administrative access and does not identify individual
customers. Protect the service with TLS and network restrictions. The built-in
60 requests per minute limit is process-local, not a deployment-wide security
control: configure a shared gateway rate limit and concurrency limits across
all replicas. Restrict access to the postgres-mcp endpoint and grant its
database role only the permissions documented in that service.

## Operator recovery

Do not blindly retry a timed-out mutation, reclaim a running workflow, or
resend a possibly delivered email. For existing uncertain work, use postgres-mcp
`get_subscription_claim_status` with the request ID and batch history with the
batch ID, then follow that server's reconciliation procedure. A missing claim
record can still represent an in-flight transaction. Confirm provider delivery
and preserve an audit trail before any manual repair; there is no exactly-once
delivery guarantee.

Run tests with `python -m pytest -q`. Database integration and real email
delivery require separately provisioned test infrastructure; the delivery gate
must remain in place until the future integration is verified.
To run the optional real-protocol test, set `POSTGRES_MCP_TEST_ROOT` to a local
postgres-mcp checkout and `POSTGRES_MCP_TEST_PYTHON` to its Python executable,
then run `python -m pytest tests/mcp/test_postgres_protocol.py`. The test starts
a loopback-only server with a fake database and does not send email.