"""Authenticated MCP transport for PostgreSQL domain tools."""

import asyncio
import errno
import logging
import math
import time
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import SecretStr
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.exceptions.service_exception import ServiceException

logger = logging.getLogger(__name__)
AUTHORIZATION_STATUS_CODES = frozenset({401, 403})
# External read-only contracts have not yet been verified.
VERIFIED_READ_TOOLS: frozenset[str] = frozenset()


class PostgresMCPError(ServiceException):
    """Represent a safe database-tool or transport failure."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        """Store the safe failure category and retryability."""
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RetryablePostgresReadError(PostgresMCPError):
    """Represent a proven transient failure of a verified read-only tool."""

    def __init__(self) -> None:
        """Create a sanitized transient failure."""
        super().__init__("transient_read", "PostgreSQL MCP read unavailable", True)


class PostgresMCPClient:
    """Call PostgreSQL MCP tools with an isolated authenticated session."""

    def __init__(
        self, url: str, token: SecretStr | None, timeout: int, *,
        retry_attempts: int = 3, retry_budget: float = 20,
        retry_initial: float = 0.25, retry_max: float = 2,
    ) -> None:
        """Validate connection settings without opening a network connection."""
        parsed = urlparse(url)
        is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid PostgreSQL MCP URL")
        if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
            raise ValueError("PostgreSQL MCP requires HTTPS outside loopback")
        if timeout <= 0:
            raise ValueError("PostgreSQL MCP timeout must be positive")
        self._url = url
        self._token = token
        self._timeout = timeout
        self._set_retry_policy(retry_attempts, retry_budget, retry_initial, retry_max)

    def _set_retry_policy(self, attempts: int, budget: float, initial: float, maximum: float) -> None:
        """Validate and store the complete bounded read retry policy."""
        values = (budget, initial, maximum)
        if (isinstance(attempts, bool) or not isinstance(attempts, int)
                or not 1 <= attempts <= 5 or not all(math.isfinite(value) for value in values)
                or not 1 <= budget <= 60 or not 0 < initial <= maximum <= budget):
            raise ValueError("Invalid PostgreSQL read retry policy")
        self._retry_attempts = attempts
        self._retry_budget = budget
        self._retry_initial = initial
        self._retry_max = maximum

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Retry only internally verified reads; call every other tool once."""
        if self._token is None:
            raise PostgresMCPError("unavailable", "PostgreSQL MCP is not configured")
        if tool in VERIFIED_READ_TOOLS:
            return await self._call_verified_read(tool, arguments)
        return await self._call_classified(tool, arguments, self._timeout, 1)

    async def _call_classified(
        self, tool: str, arguments: dict[str, Any], timeout: float, attempt: int
    ) -> Any:
        """Call once and classify errors according to the internal allowlist."""
        rejected: list[int] = []
        try:
            result = await self._call_once(tool, arguments, rejected, timeout)
        except (Exception, BaseExceptionGroup) as error:
            _raise_transport_error(error, bool(rejected), tool in VERIFIED_READ_TOOLS, attempt)
        return self._decode_result(result, tool in VERIFIED_READ_TOOLS)

    async def _call_verified_read(self, tool: str, arguments: dict[str, Any]) -> Any:
        """Apply one deadline to attempts, session cleanup, and retry backoff."""
        deadline = time.monotonic() + self._retry_budget
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(RetryablePostgresReadError),
            stop=stop_after_attempt(self._retry_attempts),
            wait=wait_random_exponential(multiplier=self._retry_initial, max=self._retry_max),
            before_sleep=lambda state: _check_retry_delay(state, deadline),
            reraise=True,
        )
        try:
            with anyio.fail_after(self._retry_budget):
                async for attempt in retrying:
                    with attempt:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise RetryablePostgresReadError() from None
                        return await self._call_classified(
                            tool, arguments, min(self._timeout, remaining),
                            attempt.retry_state.attempt_number,
                        )
        except TimeoutError:
            raise RetryablePostgresReadError() from None
        raise RetryablePostgresReadError() from None

    async def _call_once(
        self, tool: str, arguments: dict[str, Any], rejected: list[int], timeout: float
    ) -> Any:
        """Execute one bounded authenticated MCP session."""
        headers = {"Authorization": f"Bearer {self._token.get_secret_value()}"}

        # The MCP SDK hides HTTP statuses behind a generic error, so record auth rejections here.
        async def record_rejection(response: httpx2.Response) -> None:
            """Record only authorization status codes."""
            if response.status_code in AUTHORIZATION_STATUS_CODES:
                rejected.append(response.status_code)

        with anyio.fail_after(timeout):
            async with httpx2.AsyncClient(
                headers=headers,
                timeout=timeout,
                event_hooks={"response": [record_rejection]},
            ) as client:
                async with streamable_http_client(self._url, http_client=client) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        return await session.call_tool(tool, arguments)

    @staticmethod
    def _decode_result(result: Any, verified_read: bool = False) -> Any:
        """Validate MCP tool output and translate safe server errors."""
        if result.is_error:
            message = next((item.text for item in result.content if item.type == "text"), "")
            code = message.split(";", 1)[0].removeprefix("code=")
            known = {"not_found", "conflict", "database_unavailable", "invalid_input"}
            if code not in known:
                code = "tool_error"
            if code == "database_unavailable":
                if verified_read:
                    raise RetryablePostgresReadError() from None
                code = "unknown_outcome"
            raise PostgresMCPError(code, "PostgreSQL MCP tool failed") from None
        payload = result.structured_content
        if not isinstance(payload, dict):
            raise PostgresMCPError("invalid_response", "PostgreSQL MCP returned an invalid response")
        if set(payload) == {"result"}:
            return payload["result"]
        return payload


def _is_authorization_error(error: BaseException) -> bool:
    """Recognize authentication failures nested in transport task groups."""
    return any(
        isinstance(item, httpx2.HTTPStatusError)
        and item.response.status_code in AUTHORIZATION_STATUS_CODES
        for item in _exception_tree(error)
    )


def _exception_tree(error: BaseException, seen: set[int] | None = None) -> list[BaseException]:
    """Collect nested exceptions and explicit or implicit causes without cycles."""
    seen = set() if seen is None else seen
    if id(error) in seen:
        return []
    seen.add(id(error))
    children = list(error.exceptions) if isinstance(error, BaseExceptionGroup) else []
    if error.__cause__ is not None:
        children.append(error.__cause__)
    elif (error.__context__ is not None and not error.__suppress_context__
          and not _is_timeout_cancellation_context(error)):
        children.append(error.__context__)
    return [error, *(item for child in children for item in _exception_tree(child, seen))]


def _is_transient_read_failure(error: BaseException, seen: set[int] | None = None) -> bool:
    """Accept only homogeneous timeouts or demonstrably refused connections."""
    seen = set() if seen is None else seen
    if id(error) in seen:
        return False
    seen.add(id(error))
    cause = error.__cause__
    if cause is None and not error.__suppress_context__ and not _is_timeout_cancellation_context(error):
        cause = error.__context__
    if isinstance(error, BaseExceptionGroup):
        children = list(error.exceptions) + ([cause] if cause is not None else [])
        return all(_is_transient_read_failure(child, seen.copy()) for child in children)
    is_transient = isinstance(error, (TimeoutError, httpx2.TimeoutException, ConnectionRefusedError))
    is_transient = is_transient or isinstance(error, OSError) and error.errno == errno.ECONNREFUSED
    if isinstance(error, httpx2.ConnectError) and cause is not None:
        return _is_transient_read_failure(cause, seen)
    return bool(is_transient and (cause is None or _is_transient_read_failure(cause, seen)))


def _is_timeout_cancellation_context(error: BaseException) -> bool:
    """Ignore AnyIO's internal cancellation when it has become a timeout."""
    return isinstance(error, TimeoutError) and isinstance(error.__context__, asyncio.CancelledError)


def _check_retry_delay(state: RetryCallState, deadline: float) -> None:
    """Reject a retry when its jittered backoff cannot finish within budget."""
    if state.next_action is None or state.next_action.sleep >= deadline - time.monotonic():
        raise RetryablePostgresReadError() from None
    logger.warning("PostgreSQL MCP read retry: attempt=%s reason=transient", state.attempt_number)


def _raise_transport_error(
    error: BaseException, rejected: bool, verified_read: bool, attempt: int
) -> None:
    """Translate transport failures without exposing their original details."""
    for item in _exception_tree(error):
        if isinstance(item, asyncio.CancelledError):
            raise item from None
    if rejected or _is_authorization_error(error):
        logger.warning("PostgreSQL MCP request failed: attempt=%s reason=authorization", attempt)
        raise PostgresMCPError("authorization", "PostgreSQL MCP authorization failed") from None
    if verified_read and _is_transient_read_failure(error):
        logger.warning("PostgreSQL MCP read failed: attempt=%s reason=transient", attempt)
        raise RetryablePostgresReadError() from None
    logger.warning("PostgreSQL MCP request failed: attempt=%s reason=unknown_outcome", attempt)
    raise PostgresMCPError(
        "unknown_outcome", "PostgreSQL MCP request could not be confirmed"
    ) from None
