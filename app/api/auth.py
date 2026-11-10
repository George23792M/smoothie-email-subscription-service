"""Authenticate and throttle administrative workflow operations."""

import hmac
import time
from collections import deque

from fastapi import Header, HTTPException, status

from app.core.config import settings

MAX_REQUESTS_PER_MINUTE = 60
REQUEST_WINDOW_SECONDS = 60
_requests: deque[float] = deque()


async def require_operator(authorization: str = Header(default="")) -> None:
    """Require the configured bearer token and apply a process-local rate limit."""
    token = settings.OPERATOR_API_TOKEN
    if token is None:
        raise HTTPException(status_code=503, detail="Operator authentication unavailable")
    scheme, separator, supplied = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or len(supplied) > 4096:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not hmac.compare_digest(token.get_secret_value().encode(), supplied.encode()):
        raise HTTPException(status_code=401, detail="Unauthorized")
    _check_rate_limit()


def _check_rate_limit() -> None:
    """Bound requests in the current process over a rolling time window."""
    now = time.monotonic()
    while _requests and _requests[0] <= now - REQUEST_WINDOW_SECONDS:
        _requests.popleft()
    if len(_requests) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
    _requests.append(now)
