"""Tests for authenticated PostgreSQL MCP response handling."""

import asyncio
import secrets
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.mcp.postgres_client import PostgresMCPClient, PostgresMCPError
from app.services.postgres_workflows import PostgresWorkflows


def test_decode_empty_queue_returns_none():
    """Unwrap the server's structured null result."""
    result = SimpleNamespace(is_error=False, structured_content={"result": None})
    assert PostgresMCPClient._decode_result(result) is None


def test_decode_tool_error_does_not_expose_server_text():
    """Map a known server error to its category without leaking details."""
    item = SimpleNamespace(type="text", text="code=not_found; message=synthetic-private-data")
    result = SimpleNamespace(is_error=True, content=[item])
    with pytest.raises(PostgresMCPError) as error:
        PostgresMCPClient._decode_result(result)
    assert error.value.code == "not_found"
    assert "synthetic-private-data" not in str(error.value)


def test_decode_malformed_response_fails_explicitly():
    """A missing structured result is an error, not an empty result."""
    result = SimpleNamespace(is_error=False, structured_content=None)
    with pytest.raises(PostgresMCPError, match="invalid response"):
        PostgresMCPClient._decode_result(result)


@pytest.mark.parametrize("url", ["http://example.test/mcp", "file://localhost/path", "https://user@host/mcp"])
def test_rejects_untrusted_transport_configuration(url):
    """Reject cleartext remote endpoints and credentials embedded in URLs."""
    with pytest.raises(ValueError):
        PostgresMCPClient(url, None, 10)


@pytest.mark.asyncio
async def test_missing_token_fails_before_network_call():
    """Do not connect when service authentication is unavailable."""
    client = PostgresMCPClient("http://127.0.0.1:8001/mcp", None, 10)
    with pytest.raises(PostgresMCPError) as error:
        await client.call("check_database_ready", {})
    assert error.value.code == "unavailable"


@pytest.mark.asyncio
async def test_claim_rejects_wrong_owner():
    """Never process a claim assigned to a different worker."""
    client = AsyncMock()
    client.call.return_value = {
        "id": str(uuid4()), "customer_id": str(uuid4()), "claimed_by": "other",
        "workflow_type": "NEW_REGISTRATION", "status": "RUNNING", "attempt_count": 0,
    }
    with pytest.raises(PostgresMCPError, match="ownership"):
        await PostgresWorkflows(client).claim(str(uuid4()), "expected")


@pytest.mark.asyncio
async def test_stalled_transport_is_bounded_and_not_retried(monkeypatch):
    """A stalled mutation is reported as unknown, without a second attempt."""
    attempts = 0

    @asynccontextmanager
    async def stalled_transport(*args, **kwargs):
        """Simulate a server that never completes transport setup."""
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(10)
        yield ()

    monkeypatch.setattr("app.mcp.postgres_client.streamable_http_client", stalled_transport)
    client = PostgresMCPClient("http://127.0.0.1:8001/mcp", SecretStr(secrets.token_urlsafe(32)), 1)
    with pytest.raises(PostgresMCPError) as error:
        await client.call("claim_registration_workflow", {})
    assert error.value.code == "unknown_outcome"
    assert attempts == 1
