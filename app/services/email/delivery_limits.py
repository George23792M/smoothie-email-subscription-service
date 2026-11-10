"""Process-local welcome-delivery concurrency and rolling-rate limits."""

import asyncio
import math
import time
from collections import deque
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from app.core.config import settings


class DeliveryLimits:
    """Share independent batch, concurrency, and rolling-rate bounds in a process."""

    def __init__(
        self, batch_size: int, concurrency: int, rate_count: int, window_seconds: float
    ) -> None:
        """Validate limits and initialize the process-local coordination state."""
        integers = (batch_size, concurrency, rate_count)
        if any(isinstance(value, bool) or not isinstance(value, int) for value in integers):
            raise ValueError("Invalid delivery limits")
        if not (1 <= batch_size <= 1000 and 1 <= concurrency <= 50 and 1 <= rate_count <= 1000):
            raise ValueError("Invalid delivery limits")
        if not math.isfinite(window_seconds) or not 1 <= window_seconds <= 3600:
            raise ValueError("Invalid delivery limits")
        self.batch_size = batch_size
        self._rate_count = rate_count
        self._window = window_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._in_flight = asyncio.Semaphore(concurrency)

    def validate_batch_size(self, count: int) -> None:
        """Reject batches outside the configured independent batch bound."""
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= self.batch_size:
            raise ValueError("Invalid delivery batch size")

    @asynccontextmanager
    async def send_slot(self) -> AsyncIterator[None]:
        """Reserve an in-flight slot and one rolling-window send allowance."""
        async with self._in_flight:
            await self._reserve_rate()
            yield

    async def _reserve_rate(self) -> None:
        """Reserve one allowance atomically, asynchronously waiting when necessary."""
        while True:
            async with self._lock:
                now = time.monotonic()
                while self._timestamps and self._timestamps[0] <= now - self._window:
                    self._timestamps.popleft()
                if len(self._timestamps) < self._rate_count:
                    self._timestamps.append(now)
                    return
                delay = self._timestamps[0] + self._window - now
            await asyncio.sleep(delay)


@lru_cache(maxsize=1)
def get_delivery_limits() -> DeliveryLimits:
    """Return one set of process-local controls for all welcome entry points."""
    if settings.DELIVERY_LIMIT_MODE != "single_worker_exclusive":
        raise ValueError("Delivery limit deployment mode is not configured")
    return DeliveryLimits(
        settings.MAX_WORKFLOWS_PER_BATCH, settings.DELIVERY_CONCURRENCY,
        settings.DELIVERY_RATE_COUNT, settings.DELIVERY_RATE_WINDOW_SECONDS,
    )
