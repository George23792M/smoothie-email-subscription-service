"""Application-level workflow authorization and readiness tests."""

import secrets
import time
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
import app.mcp.email_client as email
import app.api.workflows as workflows
from app.api.auth import MAX_REQUESTS_PER_MINUTE, _requests


def test_production_workflow_route_rejects_unauthorized_requests(monkeypatch):
    """Both missing and incorrect credentials are rejected."""
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr(token))
    client = TestClient(main.app)
    path = "/api/api/workflows/trigger"
    payload = {"customer_ids": [str(uuid4())]}

    assert client.post(path, json=payload).status_code == 401
    assert client.post(path, json=payload, headers={"Authorization": "Bearer incorrect"}).status_code == 401


@pytest.mark.parametrize("ready", [False, True])
def test_disabled_delivery_returns_503_without_claim(monkeypatch, ready):
    """Authorized triggering cannot claim work even if readiness is mocked."""
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr(token))
    _requests.clear()
    client = TestClient(main.app)
    with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready), \
         patch("app.services.postgres_workflows.get_postgres_workflows") as factory:
        response = client.post(
            "/api/api/workflows/trigger",
            json={"customer_ids": [str(uuid4())]},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 503
    factory.assert_not_called()


@pytest.mark.parametrize("ready", [False, True])
def test_readiness_remains_unavailable_with_healthy_database(ready):
    """Healthy data and mocked delivery readiness cannot enable execution."""
    adapter = AsyncMock()
    adapter.ready.return_value = True
    with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready), \
         patch("main.get_postgres_workflows", return_value=adapter):
        response = TestClient(main.app).get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy", "database": "connected", "email_delivery": "unavailable",
    }
    adapter.ready.assert_awaited_once()


def test_application_rejects_invalid_customer_ids(monkeypatch):
    """Malformed customer IDs fail request validation."""
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr(token))
    _requests.clear()
    response = TestClient(main.app).post(
        "/api/api/workflows/trigger", json={"customer_ids": ["invalid"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_authenticated_workflow_requests_are_rate_limited(monkeypatch):
    """The per-process limit applies to valid operator credentials."""
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr(token))
    _requests.clear()
    client = TestClient(main.app)
    headers = {"Authorization": f"Bearer {token}"}
    try:
        _requests.extend([time.monotonic()] * (MAX_REQUESTS_PER_MINUTE - 1))
        assert client.post("/api/api/workflows/trigger", json={}, headers=headers).status_code == 422
        assert client.post("/api/api/workflows/trigger", json={}, headers=headers).status_code == 429
    finally:
        _requests.clear()


def test_unexpected_provider_error_closes_gate_and_api_hides_details(monkeypatch, caplog):
    """An injected provider programming error propagates to a sanitized HTTP boundary."""
    token = secrets.token_urlsafe(32)
    monkeypatch.setattr(main.settings, "OPERATOR_API_TOKEN", SecretStr(token))
    monkeypatch.setattr(email, "REAL_EMAIL_DELIVERY_VERIFIED", True)
    monkeypatch.setattr(email.delivery_readiness, "_requires_reconciliation", False)
    monkeypatch.setattr(email.delivery_readiness, "is_delivery_ready", lambda: True)
    provider = email.EmailMCPClient("http://localhost:8002/mcp", SecretStr("fake-token"), 1)
    provider._call_once = AsyncMock(side_effect=RuntimeError("fake-private-provider-detail"))
    request = email.EmailMCPRequest(
        recipient="user@example.com", subject="Hello", html_body="<p>Hello</p>",
        correlation_id=uuid4(),
    )

    async def injected_execution(**kwargs):
        return await provider.send(request)

    monkeypatch.setattr(workflows, "execute_workflow_for_customers", injected_execution)
    _requests.clear()
    try:
        response = TestClient(main.app).post(
            "/api/api/workflows/trigger",
            json={"customer_ids": [str(uuid4())]},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _requests.clear()

    assert response.status_code == 500
    assert response.json() == {"detail": "Workflow execution failed"}
    assert "fake-private-provider-detail" not in response.text
    assert "fake-private-provider-detail" not in caplog.text
    assert email.delivery_readiness.requires_reconciliation()
    provider._call_once.assert_awaited_once_with(request)
