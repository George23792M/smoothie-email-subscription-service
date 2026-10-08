"""
Phase 6 Task 2: APScheduler Configuration

Background job scheduling for batch workflow execution.

PYTHON CONCEPT: Singleton Pattern + Context Manager
- Global scheduler instance (initialized once)
- start() called during app startup
- stop() called during app shutdown
- Ensures only one batch job runs at a time (max_instances=1)

Configuration:
- Trigger: Cron, every 10 minutes
- Coalesce: True (skip missed runs if batch takes >10 mins)
- Max instances: 1 (prevent overlapping runs)
- Job: Execute NEW_REGISTRATION workflow for recently subscribed customers
"""

import logging
from typing import Optional
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.workflow_execution import (
    execute_workflow_for_customers,
    get_recently_subscribed_customers,
)
from app.services.db_pool import DatabasePool
from app.exceptions.database_exception import DatabaseExecutionException

logger = logging.getLogger(__name__)

# Global scheduler instance (singleton)
_scheduler: Optional[AsyncIOScheduler] = None


# ============================================================================
# BATCH JOB
# ============================================================================


async def batch_workflow_job() -> None:
    """
    Background job: Execute NEW_REGISTRATION workflow for recent subscriptions.

    Called every 10 minutes by APScheduler.

    MCP Integration (Phase 7):
    - TODO: Replace get_recently_subscribed_customers() with MCP call
    - TODO: Replace batch_runs create/update with workflow_service MCP tools

    Flow:
    1. Query customers subscribed in last 10 minutes
    2. Execute workflow for all customers
    3. Update batch_runs table
    4. Log results
    """
    batch_id = None
    try:
        # ===== Create batch_runs record =====
        pool = await DatabasePool.get_pool()

        async with pool.acquire() as connection:
            batch_id = await connection.fetchval(
                """
                INSERT INTO batch_runs 
                (batch_type, started_at, status)
                VALUES ($1, $2, $3)
                RETURNING id;
                """,
                "NEW_REGISTRATION",
                datetime.utcnow(),
                "RUNNING",
            )

        logger.info(
            f"Batch job started",
            extra={"batch_id": batch_id, "batch_type": "NEW_REGISTRATION"},
        )

        # ===== Get recently subscribed customers =====
        customer_ids = await get_recently_subscribed_customers()

        if not customer_ids:
            logger.info(
                "No recently subscribed customers found",
                extra={"batch_id": batch_id},
            )
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE batch_runs
                    SET status = $1,
                        completed_at = $2,
                        total_customers = $3
                    WHERE id = $4;
                    """,
                    "SUCCESS",
                    datetime.utcnow(),
                    0,
                    batch_id,
                )
            return

        logger.info(
            f"Processing {len(customer_ids)} recently subscribed customers",
            extra={"batch_id": batch_id},
        )

        # ===== Execute workflow for all customers =====
        batch_result = await execute_workflow_for_customers(
            customer_ids=customer_ids,
            workflow_type="NEW_REGISTRATION",
        )

        # ===== Update batch_runs with results =====
        async with pool.acquire() as connection:
            await connection.execute(
                """
                UPDATE batch_runs
                SET status = $1,
                    completed_at = $2,
                    total_customers = $3,
                    successful_count = $4,
                    failed_count = $5,
                    skipped_count = $6
                WHERE id = $7;
                """,
                "SUCCESS" if batch_result.failed_count == 0 else "PARTIAL_SUCCESS",
                datetime.utcnow(),
                batch_result.total_customers,
                batch_result.successful_count,
                batch_result.failed_count,
                batch_result.skipped_count,
                batch_id,
            )

        logger.info(
            f"Batch job completed",
            extra={
                "batch_id": batch_id,
                "successful": batch_result.successful_count,
                "failed": batch_result.failed_count,
                "skipped": batch_result.skipped_count,
            },
        )

    except DatabaseExecutionException as ex:
        logger.error(
            f"Database error during batch job",
            exc_info=True,
            extra={"batch_id": batch_id},
        )
        # Update batch_runs to FAILED
        try:
            pool = await DatabasePool.get_pool()
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE batch_runs
                    SET status = $1,
                        completed_at = $2,
                        error_message = $3
                    WHERE id = $4;
                    """,
                    "FAILED",
                    datetime.utcnow(),
                    str(ex),
                    batch_id,
                )
        except Exception as ex2:
            logger.error(
                f"Failed to update batch_runs to FAILED",
                exc_info=True,
                extra={"batch_id": batch_id},
            )

    except Exception as ex:
        logger.error(
            f"Unexpected error during batch job",
            exc_info=True,
            extra={"batch_id": batch_id},
        )
        try:
            pool = await DatabasePool.get_pool()
            async with pool.acquire() as connection:
                await connection.execute(
                    """
                    UPDATE batch_runs
                    SET status = $1,
                        completed_at = $2,
                        error_message = $3
                    WHERE id = $4;
                    """,
                    "FAILED",
                    datetime.utcnow(),
                    str(ex),
                    batch_id,
                )
        except Exception as ex2:
            logger.error(
                f"Failed to update batch_runs to FAILED",
                exc_info=True,
                extra={"batch_id": batch_id},
            )


# ============================================================================
# SCHEDULER LIFECYCLE
# ============================================================================


def get_scheduler() -> AsyncIOScheduler:
    """Get global scheduler instance (create if not exists)."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


async def initialize_scheduler() -> None:
    """
    Initialize and start APScheduler.

    Call this during application startup.

    Configuration:
    - Trigger: Cron, every 10 minutes (0, 10, 20, 30, etc.)
    - Coalesce: True (skip missed runs if batch takes >10 mins)
    - Max instances: 1 (prevent overlapping batch jobs)
    """
    scheduler = get_scheduler()

    if scheduler.running:
        logger.warning("Scheduler already running")
        return

    try:
        # Add batch job: every 10 minutes
        scheduler.add_job(
            batch_workflow_job,
            trigger=CronTrigger(minute="*/10"),  # Every 10 minutes
            coalesce=True,  # Skip missed runs
            max_instances=1,  # Only one job at a time
            id="batch-new-registration-workflow",
            name="Batch NEW_REGISTRATION Workflow",
            misfire_grace_time=60,  # Grace period: 1 minute
        )

        scheduler.start()
        logger.info("APScheduler started successfully")

    except Exception as ex:
        logger.error("Failed to initialize scheduler", exc_info=True)
        raise


async def shutdown_scheduler() -> None:
    """
    Shutdown APScheduler gracefully.

    Call this during application shutdown.
    """
    scheduler = get_scheduler()

    if not scheduler.running:
        logger.warning("Scheduler not running")
        return

    try:
        scheduler.shutdown(wait=True)
        logger.info("APScheduler shutdown successfully")
    except Exception as ex:
        logger.error("Error shutting down scheduler", exc_info=True)
        raise
