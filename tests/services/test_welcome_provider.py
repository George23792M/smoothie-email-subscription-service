"""Tests of provisional email MCP response handling with fake transports."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

import app.mcp.email_client as email


@pytest.fixture
def email_request():
    """Create a synthetic request."""
    return email.EmailMCPRequest(
        recipient="user@example.com", subject="Hello", html_body="<p>Hello</p>",
        correlation_id=uuid4(),
    )


@pytest.mark.parametrize("status", ["accepted", "rejected", "unknown"])
def test_fake_response_preserves_explicit_status_and_correlation(email_request, status):
    """A valid fake response maps its status without implying real delivery."""
    response = email.parse_fake_response(
        {"status": status, "correlation_id": str(email_request.correlation_id)}, email_request.correlation_id,
    )
    assert response.status == status
    assert response.correlation_id == email_request.correlation_id


@pytest.mark.parametrize("payload", [
    {}, {"status": "delivered"}, {"status": "accepted", "extra": "unexpected"},
])
def test_malformed_fake_response_requires_reconciliation(email_request, payload):
    """Incomplete and unexpected fake responses are not treated as acceptance."""
    with pytest.raises(email.EmailMCPUnknownOutcomeError):
        email.parse_fake_response(payload, email_request.correlation_id)


def test_mismatched_correlation_requires_reconciliation(email_request):
    """An acceptance response for a different request is ambiguous."""
    with pytest.raises(email.EmailMCPUnknownOutcomeError):
        email.parse_fake_response({"status": "accepted", "correlation_id": str(uuid4())},
                                  email_request.correlation_id)


@pytest.mark.parametrize("url", [
    "http://example.test/mcp", "https://user:pass@example.test/mcp",
    "https://example.test/mcp?token=synthetic", "file://localhost/mcp",
])
def test_client_rejects_unsafe_urls(url):
    """Only TLS endpoints or loopback HTTP without URL credentials are allowed."""
    with pytest.raises(ValueError):
        email.EmailMCPClient(url, SecretStr("fake-token"), 1)


def test_request_rejects_header_injection_and_extra_fields(email_request):
    """Request validation rejects header injection and unexpected properties."""
    payload = email_request.model_dump()
    payload.update(subject="hello\r\nBcc: attacker@example.test", extra="unexpected")
    with pytest.raises(ValidationError):
        email.EmailMCPRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_real_gate_refuses_to_invoke_transport(email_request):
    """Normal delivery stays unavailable even if a credential is present."""
    client = email.EmailMCPClient("http://localhost:8002/mcp", SecretStr("fake-token"), 1)
    client._call_once = AsyncMock()
    with pytest.raises(email.EmailMCPUnavailableError):
        await client.send(email_request)
    client._call_once.assert_not_awaited()


@pytest.mark.parametrize("failure", [None, TimeoutError("fake-private"), asyncio.CancelledError()])
@pytest.mark.asyncio
async def test_injected_invocation_closes_gate_and_never_resends(email_request, monkeypatch, failure):
    """Test-only gate injection cannot infer acceptance and always closes after invocation."""
    monkeypatch.setattr(email, "REAL_EMAIL_DELIVERY_VERIFIED", True)
    monkeypatch.setattr(email.delivery_readiness, "is_delivery_ready", lambda: True)
    closed = []
    monkeypatch.setattr(email.delivery_readiness, "close_for_reconciliation", lambda: closed.append(True))
    client = email.EmailMCPClient("http://localhost:8002/mcp", SecretStr("fake-token"), 1)
    client._call_once = AsyncMock(side_effect=failure)

    if failure is None:
        assert (await client.send(email_request)).status == "unknown"
    else:
        expected = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else email.EmailMCPUnknownOutcomeError
        with pytest.raises(expected):
            await client.send(email_request)
    assert client._call_once.await_count == 1
    assert closed == [True]


@pytest.mark.asyncio
async def test_unclassified_transport_failure_is_sanitized_and_requires_reconciliation(
    email_request, monkeypatch,
):
    """Unexpected post-invocation failures must not leak data or imply rejection."""
    monkeypatch.setattr(email, "REAL_EMAIL_DELIVERY_VERIFIED", True)
    monkeypatch.setattr(email.delivery_readiness, "is_delivery_ready", lambda: True)
    closed = []
    monkeypatch.setattr(email.delivery_readiness, "close_for_reconciliation", lambda: closed.append(True))
    client = email.EmailMCPClient("http://localhost:8002/mcp", SecretStr("fake-token"), 1)
    client._call_once = AsyncMock(side_effect=ValueError("fake-private-provider-detail"))

    with pytest.raises(email.EmailMCPUnknownOutcomeError) as error:
        await client.send(email_request)

    assert "fake-private-provider-detail" not in str(error.value)
    assert error.value.__cause__ is None
    assert error.value.__suppress_context__
    assert client._call_once.await_count == 1
    assert closed == [True]


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (ValueError("fake-private"), email.EmailMCPUnknownOutcomeError),
        (TimeoutError("fake-private"), email.EmailMCPUnknownOutcomeError),
        (asyncio.CancelledError(), asyncio.CancelledError),
        (RuntimeError("fake-private"), RuntimeError),
    ],
)
@pytest.mark.asyncio
async def test_uncertain_invocation_blocks_subsequent_send(email_request, monkeypatch, failure, expected):
    """Uncertainty closes the gate, preserves programming errors, and prevents resend."""
    monkeypatch.setattr(email, "REAL_EMAIL_DELIVERY_VERIFIED", True)
    monkeypatch.setattr(email.delivery_readiness, "_requires_reconciliation", False)
    monkeypatch.setattr(
        email.delivery_readiness, "is_delivery_ready",
        lambda: not email.delivery_readiness.requires_reconciliation(),
    )
    client = email.EmailMCPClient("http://localhost:8002/mcp", SecretStr("fake-token"), 1)
    client._call_once = AsyncMock(side_effect=failure)

    with pytest.raises(expected) as caught:
        await client.send(email_request)
    if isinstance(failure, (RuntimeError, asyncio.CancelledError)):
        assert caught.value is failure
    with pytest.raises(email.EmailMCPUnavailableError):
        await client.send(email_request)

    assert email.delivery_readiness.requires_reconciliation()
    client._call_once.assert_awaited_once_with(email_request)
