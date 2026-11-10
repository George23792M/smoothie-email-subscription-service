"""Independent regressions for the disabled production execution boundary."""

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from app.api.auth import _requests
from app.mcp.postgres_client import PostgresMCPClient, PostgresMCPError
from app.services.postgres_workflows import PostgresWorkflows
from app.services.workflow_execution import DeliveryUnavailableError, execute_claim


LEGACY_IMPORT_PROBE = """
import asyncio
import importlib.abc
import sys
class BlockLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "app.graph" or fullname.startswith("app.graph.") or fullname == "app.agents" or fullname.startswith("app.agents."):
            raise AssertionError("legacy import attempted: " + fullname)
sys.meta_path.insert(0, BlockLegacy())
import main
from fastapi.testclient import TestClient
from app.core.scheduler import batch_workflow_job
from app.services.workflow_execution import execute_claim, DeliveryUnavailableError
async def exercise():
    await batch_workflow_job()
    try:
        await execute_claim(None, None)
    except DeliveryUnavailableError:
        pass
    else:
        raise AssertionError("direct claim was accepted")
asyncio.run(exercise())
with TestClient(main.app) as client:
    response = client.post("/api/api/workflows/trigger",
        json={"customer_ids": ["00000000-0000-0000-0000-000000000001"]},
        headers={"Authorization": "Bearer " + "x" * 32})
    assert response.status_code == 503
assert not any(name == "app.graph" or name.startswith("app.graph.") or name == "app.agents" or name.startswith("app.agents.") for name in sys.modules)
"""


class Untouchable:
    """Fail if disabled execution inspects a supplied object."""

    def __getattribute__(self, name):
        """Reject every attribute read by disabled execution."""
        raise AssertionError(f"disabled execution accessed {name}")


@pytest.mark.parametrize("ready", [False, True])
@pytest.mark.asyncio
async def test_direct_claim_rejects_without_inspecting_inputs(monkeypatch, ready):
    """Neither supplied claim nor adapter is read, regardless of readiness."""
    monkeypatch.setattr("app.services.delivery_readiness.is_delivery_ready", lambda: ready)
    with pytest.raises(DeliveryUnavailableError, match="unavailable"):
        await execute_claim(Untouchable(), Untouchable())


def test_fresh_production_import_and_execution_never_load_legacy_agents(monkeypatch):
    """A fresh production process cannot import agents or graph on disabled paths."""
    for key, value in {
        "MCP_SERVER_URL": "http://127.0.0.1:8001",
        "OPENAI_API_KEY": "fake-key",
        "RESEND_API_KEY": "fake-key",
        "SENDER_EMAIL": "test@example.com",
        "MAX_RETRIES": "1",
        "LANGSMITH_API_KEY": "fake-key",
        "LANGSMITH_PROJECT": "test",
        "OPERATOR_API_TOKEN": "x" * 32,
    }.items():
        monkeypatch.setenv(key, value)
    script = LEGACY_IMPORT_PROBE
    result = subprocess.run(
        [sys.executable, "-c", script], env=os.environ.copy(),
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_application_lifespan_starts_and_stops_without_database(monkeypatch):
    """Application startup and shutdown do not acquire a database adapter."""
    initialize, shutdown = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main, "initialize_scheduler", initialize)
    monkeypatch.setattr(main, "shutdown_scheduler", shutdown)
    factory = AsyncMock()
    monkeypatch.setattr(main, "get_postgres_workflows", factory)
    with TestClient(main.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}
        initialize.assert_awaited_once()
        shutdown.assert_not_awaited()
    shutdown.assert_awaited_once()
    factory.assert_not_called()


@pytest.mark.parametrize("failure", [
    PostgresMCPError("authorization", "fake-private-detail"),
    PostgresMCPError("invalid_response", "fake-private-detail"),
    PostgresMCPError("unknown_outcome", "fake-private-detail"),
])
def test_database_readiness_errors_return_sanitized_503(monkeypatch, caplog, failure):
    """Known database failures never reveal the underlying error text."""
    adapter = AsyncMock()
    adapter.ready.side_effect = failure
    monkeypatch.setattr(main, "get_postgres_workflows", lambda: adapter)
    response = TestClient(main.app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy", "database": "disconnected", "email_delivery": "unavailable",
    }
    assert "fake-private-detail" not in response.text + caplog.text
    adapter.ready.assert_awaited_once()


@pytest.mark.asyncio
async def test_unexpected_database_readiness_error_propagates(monkeypatch):
    """An unexpected programming error is not disguised as an ordinary outage."""
    adapter = AsyncMock()
    adapter.ready.side_effect = RuntimeError("fake-bug")
    monkeypatch.setattr(main, "get_postgres_workflows", lambda: adapter)
    with pytest.raises(RuntimeError, match="fake-bug"):
        await main.readiness_check()
    adapter.ready.assert_awaited_once()


@pytest.mark.parametrize("payload", [
    {"customer_ids": []},
    {"customer_ids": ["' OR 1=1 --"]},
    {"customer_ids": ["<script>alert(1)</script>"]},
    {"customer_ids": [str(uuid4())], "workflow_type": "UNKNOWN"},
    {"customer_ids": [str(uuid4())] * 101},
])
def test_invalid_trigger_payload_never_acquires_adapter(monkeypatch, payload):
    """Empty, oversized, injection and unsupported inputs are rejected."""
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr("x" * 32))
    factory = AsyncMock()
    monkeypatch.setattr("app.services.postgres_workflows.get_postgres_workflows", factory)
    _requests.clear()
    try:
        response = TestClient(main.app).post(
            "/api/api/workflows/trigger", json=payload,
            headers={"Authorization": "Bearer " + "x" * 32},
        )
    finally:
        _requests.clear()
    assert response.status_code == 422
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_readiness_real_transport_timeout_is_unavailable_without_retry(monkeypatch):
    """A real deadline yields sanitized 503 and only one transport attempt."""
    attempts = []

    @asynccontextmanager
    async def stalled_transport(*args, **kwargs):
        """Block the transport until the deadline expires."""
        attempts.append(1)
        await asyncio.Event().wait()
        yield ()

    monkeypatch.setattr("app.mcp.postgres_client.streamable_http_client", stalled_transport)
    client = PostgresMCPClient("http://127.0.0.1:8001/mcp", SecretStr("fake-token"), 0.02)
    monkeypatch.setattr(main, "get_postgres_workflows", lambda: PostgresWorkflows(client))
    response = await main.readiness_check()
    assert response.status_code == 503
    assert b'"database":"disconnected"' in response.body
    assert b'"email_delivery":"unavailable"' in response.body
    assert attempts == [1]


@pytest.mark.asyncio
async def test_caller_cancellation_of_readiness_propagates_without_retry(monkeypatch):
    """Independent caller cancellation is not converted into a timeout or retried."""
    started = asyncio.Event()
    attempts = []

    @asynccontextmanager
    async def stalled_transport(*args, **kwargs):
        """Block the transport until its caller is cancelled."""
        attempts.append(1)
        started.set()
        await asyncio.Event().wait()
        yield ()

    monkeypatch.setattr("app.mcp.postgres_client.streamable_http_client", stalled_transport)
    client = PostgresMCPClient("http://127.0.0.1:8001/mcp", SecretStr("fake-token"), 10)
    monkeypatch.setattr(main, "get_postgres_workflows", lambda: PostgresWorkflows(client))
    task = asyncio.create_task(main.readiness_check())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert attempts == [1]
