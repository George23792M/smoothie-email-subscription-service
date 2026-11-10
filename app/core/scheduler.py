"""Keep scheduled workflow processing disabled until integration."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def batch_workflow_job() -> None:
    """Decline direct batch execution without acquiring an adapter."""
    logger.warning("Scheduled workflow processing disabled: email delivery unavailable")


def get_scheduler() -> AsyncIOScheduler:
    """Return the process-local scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def initialize_scheduler() -> None:
    """Decline to register or start scheduled workflow processing."""
    logger.warning("Scheduler disabled until workflow execution is integrated")


async def shutdown_scheduler() -> None:
    """Stop the scheduler if it was started."""
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
