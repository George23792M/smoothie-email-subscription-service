"""Optional cross-version MCP protocol integration against the server project."""

import asyncio
import os
import secrets
import socket
import subprocess

import pytest
from pydantic import SecretStr

from app.mcp.postgres_client import PostgresMCPClient, PostgresMCPError
from app.services.postgres_workflows import PostgresWorkflows

SERVER_ROOT = os.environ.get("POSTGRES_MCP_TEST_ROOT")
SERVER_PYTHON = os.environ.get("POSTGRES_MCP_TEST_PYTHON")
SERVER_SCRIPT = """
import os
from datetime import datetime, timezone
from uuid import UUID
import uvicorn
from app.config import Settings
import app.server as server
import app.tools.subscription_tools as tools
import app.repositories.subscription_repository as repository
from app.schemas_subscription import SubscriptionCustomer, WorkflowHistoryEntry
async def noop(*args, **kwargs): pass
class Pool:
    async def fetchval(self, query): return 1
async def customer(pool, customer_id):
    return SubscriptionCustomer(customer_id=customer_id, first_name="Test", last_name="User",
        preferred_name=None, email="test@example.com", plan_name="Trial")
async def claim(pool, request_id, worker_id, customer_id): return None
async def history(pool, customer_id, workflow_type, limit):
    return [WorkflowHistoryEntry(id=UUID(int=2), customer_id=customer_id,
        workflow_type="NEW_REGISTRATION", status="PENDING", email_status="PENDING",
        attempt_count=0, started_at=datetime.now(timezone.utc), completed_at=None,
        validation_errors=None)]
server.create_pool = noop
server.close_pool = noop
tools.get_pool = lambda: Pool()
repository.customer_context = customer
repository.claim_registration = claim
repository.workflow_history = history
config = Settings(_env_file=None, db_user="probe", db_password=os.environ["PROBE_TOKEN"],
    db_host="127.0.0.1", db_port=5432, db_name="probe",
    mcp_host="127.0.0.1", mcp_port=int(os.environ["PROBE_PORT"]),
    mcp_auth_token=os.environ["PROBE_TOKEN"])
uvicorn.run(server.create_server(config).streamable_http_app(),
    host="127.0.0.1", port=int(os.environ["PROBE_PORT"]), log_level="critical")
"""


async def _wait_for_server(port: int, process: subprocess.Popen) -> None:
    """Wait for the dedicated loopback server without hiding startup failure."""
    for _ in range(200):
        if process.poll() is not None:
            raise RuntimeError("Test MCP server exited during startup")
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError("Test MCP server did not start")


@pytest.mark.skipif(not SERVER_ROOT or not SERVER_PYTHON, reason="Cross-repository MCP test not configured")
@pytest.mark.asyncio
async def test_real_authenticated_protocol_response_shapes():
    """Exercise customer, empty claim, history and safe errors on real HTTP."""
    assert SERVER_ROOT is not None and SERVER_PYTHON is not None
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(32)
    env = os.environ.copy()
    env.update(PROBE_PORT=str(port), PROBE_TOKEN=token)
    process = subprocess.Popen(
        [SERVER_PYTHON, "-c", SERVER_SCRIPT], cwd=SERVER_ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        await _wait_for_server(port, process)
        await _check_protocol(port, token)
    finally:
        process.terminate()
        process.wait(timeout=10)


async def _check_protocol(port: int, token: str) -> None:
    """Verify typed responses and sanitized validation errors."""
    client = PostgresMCPClient(f"http://127.0.0.1:{port}/mcp", SecretStr(token), 15)
    adapter = PostgresWorkflows(client)
    customer_id = "00000000-0000-0000-0000-000000000001"
    assert await adapter.ready()
    customer = await adapter.customer(customer_id)
    assert customer.customer_id == customer_id and customer.plan_name == "Trial"
    assert await adapter.claim(customer_id, "probe") is None
    history = await adapter.history(customer_id, None, 10)
    assert len(history) == 1 and history[0]["customer_id"] == customer_id
    with pytest.raises(PostgresMCPError) as error:
        await client.call("get_customer_profile", {"customer_id": "invalid-synthetic-input"})
    assert error.value.code == "invalid_input"
    assert "invalid-synthetic-input" not in str(error.value)
    unauthorized = PostgresMCPClient(
        f"http://127.0.0.1:{port}/mcp", SecretStr(secrets.token_urlsafe(32)), 15
    )
    with pytest.raises(PostgresMCPError) as error:
        await unauthorized.call("check_database_ready", {})
    assert error.value.code == "authorization"
