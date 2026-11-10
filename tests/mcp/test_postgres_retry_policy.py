"""Focused tests of provisional PostgreSQL read retry and mutation safety."""

import asyncio
import errno
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx2
import pytest
from pydantic import SecretStr

import app.mcp.postgres_client as postgres
from app.services.postgres_workflows import PostgresWorkflows


@pytest.fixture
def client():
    """Create a client without making network connections."""
    return postgres.PostgresMCPClient(
        "http://localhost:8001/mcp", SecretStr("fake-token"), 2,
        retry_attempts=3, retry_budget=2, retry_initial=0.001, retry_max=0.001,
    )


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("fake-private"), ConnectionRefusedError(errno.ECONNREFUSED, "fake-private"),
     ExceptionGroup("transient", [TimeoutError(), ConnectionRefusedError()])],
)
@pytest.mark.asyncio
async def test_verified_read_retries_transient_failures_and_returns_result(client, monkeypatch, failure):
    """A test-only verified read retries classified failures and returns the result."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    client._call_once = AsyncMock(side_effect=[failure, SimpleNamespace(
        is_error=False, structured_content={"result": {"value": 7}},
    )])

    result = await client.call("fake_read", {})

    assert result == {"value": 7}
    assert client._call_once.await_count == 2


@pytest.mark.parametrize("failure", [
    httpx2.ConnectError("fake-private"),
    OSError("fake-private"),
    ExceptionGroup("mixed", [TimeoutError(), ValueError("fake-private")]),
])
@pytest.mark.asyncio
async def test_verified_read_does_not_retry_unproven_failures(client, monkeypatch, caplog, failure):
    """Generic and mixed failures remain non-retryable and do not leak details."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    client._call_once = AsyncMock(side_effect=failure)

    with pytest.raises(postgres.PostgresMCPError) as error:
        await client.call("fake_read", {})

    assert error.value.code == "unknown_outcome"
    assert client._call_once.await_count == 1
    assert "fake-private" not in str(error.value) + caplog.text
    assert error.value.__suppress_context__


@pytest.mark.asyncio
async def test_authorization_in_nested_group_takes_precedence_over_timeout(client, monkeypatch):
    """An authorization rejection is never retried, even alongside a timeout."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    request = httpx2.Request("GET", "https://example.test")
    response = httpx2.Response(403, request=request)
    auth = httpx2.HTTPStatusError("fake-private", request=request, response=response)
    client._call_once = AsyncMock(side_effect=ExceptionGroup("mixed", [TimeoutError(), auth]))

    with pytest.raises(postgres.PostgresMCPError) as error:
        await client.call("fake_read", {})

    assert error.value.code == "authorization"
    assert client._call_once.await_count == 1


@pytest.mark.asyncio
async def test_cancellation_inside_group_propagates_without_retry(client, monkeypatch):
    """Cancellation takes priority over other errors and stops retries."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    client._call_once = AsyncMock(side_effect=BaseExceptionGroup(
        "mixed", [TimeoutError(), asyncio.CancelledError()],
    ))

    with pytest.raises(asyncio.CancelledError):
        await client.call("fake_read", {})

    assert client._call_once.await_count == 1


@pytest.mark.asyncio
async def test_verified_database_unavailable_exhausts_retry_budget_by_attempt_count(client, monkeypatch):
    """A classified database outage stops after the configured total attempts."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    result = SimpleNamespace(is_error=True, content=[
        SimpleNamespace(type="text", text="code=database_unavailable; fake-private"),
    ])
    client._call_once = AsyncMock(return_value=result)

    with pytest.raises(postgres.RetryablePostgresReadError) as error:
        await client.call("fake_read", {})

    assert error.value.code == "transient_read"
    assert client._call_once.await_count == 3
    assert "fake-private" not in str(error.value)


@pytest.mark.parametrize("tool", [
    "get_subscription_customer", "get_active_email_template", "claim_registration_workflow",
    "complete_registration_workflow", "create_subscription_batch",
    "complete_subscription_batch", "unknown_tool",
])
@pytest.mark.asyncio
async def test_unverified_reads_mutations_and_unknown_tools_are_called_once(client, tool):
    """Unverified operations, including side effects, are never blindly retried."""
    assert not postgres.VERIFIED_READ_TOOLS
    client._call_once = AsyncMock(side_effect=TimeoutError("fake-private"))

    with pytest.raises(postgres.PostgresMCPError) as error:
        await client.call(tool, {})

    assert error.value.code == "unknown_outcome"
    assert client._call_once.await_count == 1


@pytest.mark.asyncio
async def test_mutation_database_unavailable_has_unknown_outcome_without_retry(client):
    """A server outage response on a mutation still requires reconciliation."""
    client._call_once = AsyncMock(return_value=SimpleNamespace(
        is_error=True, content=[SimpleNamespace(type="text", text="code=database_unavailable")],
    ))
    with pytest.raises(postgres.PostgresMCPError) as error:
        await client.call("create_subscription_batch", {})
    assert error.value.code == "unknown_outcome"
    assert client._call_once.await_count == 1


@pytest.mark.asyncio
async def test_backoff_that_exceeds_deadline_does_not_start_another_attempt(client, monkeypatch):
    """A retry delay longer than the remaining budget is rejected without sleeping."""
    monkeypatch.setattr(postgres, "VERIFIED_READ_TOOLS", frozenset({"fake_read"}))
    monkeypatch.setattr(postgres, "wait_random_exponential", lambda **kwargs: lambda state: 3)
    client._call_once = AsyncMock(side_effect=TimeoutError())
    with pytest.raises(postgres.RetryablePostgresReadError):
        await client.call("fake_read", {})
    assert client._call_once.await_count == 1


@pytest.mark.parametrize("payload", [
    None, {}, {"found": 0}, {"found": False, "template": None},
    {"found": True, "template": {"active": False, "subject": "Hi", "html_body": "<p>Hi</p>"}},
    {"found": True, "template": {"active": True, "subject": "", "html_body": "<p>Hi</p>"}},
    {"found": True, "template": {"active": True, "subject": "Hi", "html_body": "<p>Hi</p>", "extra": 1}},
])
@pytest.mark.asyncio
async def test_template_adapter_rejects_malformed_or_ambiguous_payloads(payload):
    """A malformed active-template contract never falls back to local content."""
    client = AsyncMock()
    client.call.return_value = payload
    with pytest.raises(postgres.PostgresMCPError) as error:
        await PostgresWorkflows(client).active_welcome_template()
    assert error.value.code == "invalid_response"
    client.call.assert_awaited_once_with("get_active_email_template", {"template_name": "welcome"})


@pytest.mark.parametrize("payload, expected", [
    ({"found": False}, None),
    ({"found": True, "template": {"active": True, "subject": "Hi", "html_body": "<p>Hi</p>"}}, "Hi"),
])
@pytest.mark.asyncio
async def test_template_adapter_maps_found_and_absent(payload, expected):
    """The proposed fake contract distinguishes a valid active record from absence."""
    client = AsyncMock()
    client.call.return_value = payload
    result = await PostgresWorkflows(client).active_welcome_template()
    assert (result.subject if result else None) == expected
