"""Provisional email MCP contract; real acceptance semantics are unverified."""

import math
import unicodedata
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

import anyio
import httpx2
from mcp import MCPError, ClientSession
from mcp.client.streamable_http import StreamableHTTPError, streamable_http_client
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, ValidationError, field_validator

from app.services import delivery_readiness

REAL_EMAIL_DELIVERY_VERIFIED = False


class EmailMCPUnavailableError(Exception):
    """Represent a disabled or unconfigured email transport."""


class EmailMCPUnknownOutcomeError(Exception):
    """Represent an email invocation requiring manual reconciliation."""


class EmailMCPRequest(BaseModel):
    """Propose bounded send_email inputs; the remote contract is unverified."""

    model_config = ConfigDict(extra="forbid")
    recipient: EmailStr
    subject: str = Field(min_length=1, max_length=200)
    html_body: str = Field(min_length=1, max_length=65536)
    correlation_id: UUID

    @field_validator("subject", "html_body")
    @classmethod
    def reject_controls(cls, value: str) -> str:
        """Reject control characters in outbound content."""
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Invalid email content")
        return value


class EmailMCPResponse(BaseModel):
    """Represent only the locally proposed fake response shape."""

    model_config = ConfigDict(extra="forbid")
    status: Literal["accepted", "rejected", "unknown"]
    correlation_id: UUID


def parse_fake_response(payload: object, correlation_id: UUID) -> EmailMCPResponse:
    """Validate a fake response without asserting remote provider semantics."""
    try:
        response = EmailMCPResponse.model_validate(payload)
    except ValidationError:
        raise EmailMCPUnknownOutcomeError("Email outcome requires reconciliation") from None
    if response.correlation_id != correlation_id:
        raise EmailMCPUnknownOutcomeError("Email outcome requires reconciliation")
    return response


class EmailMCPClient:
    """Call the proposed tool once, while refusing unverified real acceptance."""

    def __init__(self, url: str, token: SecretStr | None, timeout: float) -> None:
        """Validate a separately configured authenticated endpoint and timeout."""
        parsed = urlparse(url)
        loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.query:
            raise ValueError("Invalid email MCP URL")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("Email MCP requires HTTPS outside loopback")
        if not math.isfinite(timeout) or not 0 < timeout <= 60:
            raise ValueError("Invalid email MCP timeout")
        self._url, self._token, self._timeout = url, token, timeout

    async def send(self, request: EmailMCPRequest) -> EmailMCPResponse:
        """Refuse delivery until readiness is verified; never assert real acceptance."""
        if (
            not REAL_EMAIL_DELIVERY_VERIFIED
            or not delivery_readiness.is_delivery_ready()
            or self._token is None
        ):
            raise EmailMCPUnavailableError("Email delivery is unavailable")
        try:
            await self._call_once(request)
        except (
            TimeoutError, ValueError, httpx2.HTTPError, MCPError, StreamableHTTPError,
            anyio.BrokenResourceError, anyio.ClosedResourceError, anyio.EndOfStream,
        ):
            # Transport failures may follow a provider side effect.
            raise EmailMCPUnknownOutcomeError("Email outcome requires reconciliation") from None
        finally:
            delivery_readiness.close_for_reconciliation()
        return EmailMCPResponse(status="unknown", correlation_id=request.correlation_id)

    async def _call_once(self, request: EmailMCPRequest) -> None:
        """Invoke the proposed send tool once under a whole-call timeout."""
        headers = {"Authorization": f"Bearer {self._token.get_secret_value()}"}
        with anyio.fail_after(self._timeout):
            async with httpx2.AsyncClient(headers=headers, timeout=self._timeout) as client:
                async with streamable_http_client(self._url, http_client=client) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        await session.call_tool("send_email", request.model_dump(mode="json"))
