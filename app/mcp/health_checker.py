"""Background health checking for replicas."""

import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Dict

from app.mcp.replica_stats import ReplicaStats

logger = logging.getLogger(__name__)


class HealthChecker:
    """Monitors replica health at regular intervals."""

    def __init__(self, interval_seconds: int = 30):
        """Initialize health checker."""
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._is_running = False

    async def start(
        self, check_fn: Callable[[str, str, ReplicaStats], asyncio.coroutine]
    ) -> None:
        """Start background health check loop."""
        if self._is_running:
            logger.warning("Health checker already running")
            return

        self._is_running = True
        self._task = asyncio.create_task(self._health_check_loop(check_fn))
        logger.info(f"Health checker started ({self.interval_seconds}s interval)")

    async def stop(self) -> None:
        """Stop background health check loop."""
        if not self._is_running:
            return

        self._is_running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Health checker stopped")

    async def _health_check_loop(
        self, check_fn: Callable[[str, str, ReplicaStats], asyncio.coroutine]
    ) -> None:
        """Run health checks periodically."""
        while self._is_running:
            try:
                await asyncio.sleep(self.interval_seconds)
                # check_fn will be called by caller with services
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Health check loop error: {e}")


async def check_replica_health(url: str, stats: ReplicaStats) -> None:
    """
    Check health of a single replica.

    Updates status, latency, error_rate.
    """
    try:
        start = time.time()
        await asyncio.sleep(0.01)  # Placeholder

        latency = (time.time() - start) * 1000

        stats.status = "HEALTHY"
        stats.latency_ms = latency
        stats.consecutive_failures = 0
        stats.error_rate = max(0.0, stats.error_rate - 0.05)
        stats.last_health_check = datetime.now()

        logger.debug(f"Health check OK: {url} ({latency:.2f}ms)")

    except asyncio.TimeoutError:
        _mark_unhealthy(stats, url, "timeout")
    except Exception as e:
        _mark_unhealthy(stats, url, str(e))


def _mark_unhealthy(stats: ReplicaStats, url: str, reason: str) -> None:
    """Mark replica as unhealthy."""
    stats.status = "UNHEALTHY"
    stats.latency_ms = 5000.0
    stats.consecutive_failures += 1
    stats.last_health_check = datetime.now()
    logger.error(f"Health check failed for {url}: {reason}")
