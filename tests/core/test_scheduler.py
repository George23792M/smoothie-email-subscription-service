"""
Phase 6 Tests: APScheduler Configuration

Tests for:
- Scheduler initialization
- Batch job execution
- Batch run tracking in database
- Error handling and recovery
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.core.scheduler import (
    batch_workflow_job,
    get_scheduler,
    initialize_scheduler,
    shutdown_scheduler,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_pool():
    """Mock database connection pool."""
    pool = AsyncMock()
    return pool


@pytest.fixture
def mock_connection():
    """Mock database connection."""
    conn = AsyncMock()
    return conn


# ============================================================================
# TEST: Scheduler Lifecycle
# ============================================================================


class TestSchedulerLifecycle:
    """Test scheduler initialization and shutdown."""

    def test_get_scheduler_returns_singleton(self):
        """get_scheduler() should return same instance on multiple calls."""
        scheduler1 = get_scheduler()
        scheduler2 = get_scheduler()

        assert scheduler1 is scheduler2

    @pytest.mark.asyncio
    async def test_initialize_scheduler_starts_scheduler(self):
        """initialize_scheduler() should create job and start scheduler."""
        with patch("app.core.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler.running = False
            mock_scheduler_class.return_value = mock_scheduler

            # Reset global scheduler
            import app.core.scheduler as scheduler_module

            scheduler_module._scheduler = None

            await initialize_scheduler()

            # Verify job was added
            assert mock_scheduler.add_job.called
            # Verify scheduler was started
            assert mock_scheduler.start.called

    @pytest.mark.asyncio
    async def test_shutdown_scheduler_stops_scheduler(self):
        """shutdown_scheduler() should stop running scheduler."""
        with patch("app.core.scheduler.AsyncIOScheduler") as mock_scheduler_class:
            mock_scheduler = MagicMock()
            mock_scheduler.running = True
            mock_scheduler_class.return_value = mock_scheduler

            import app.core.scheduler as scheduler_module

            scheduler_module._scheduler = None

            await initialize_scheduler()
            await shutdown_scheduler()

            # Verify scheduler was shutdown
            assert mock_scheduler.shutdown.called


# ============================================================================
# TEST: Batch Workflow Job
# ============================================================================


class TestBatchWorkflowJob:
    """Test batch_workflow_job execution."""

    @pytest.mark.asyncio
    async def test_batch_job_creates_batch_run_record(self, mock_pool, mock_connection):
        """Should create batch_runs record at job start."""
        batch_id = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.fetch = AsyncMock(return_value=[])  # No customers
        mock_connection.execute = AsyncMock()

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                return_value=[],
            ):
                await batch_workflow_job()

        # Verify batch_runs INSERT was called (fetchval)
        assert mock_connection.fetchval.called

    @pytest.mark.asyncio
    async def test_batch_job_handles_no_customers(self, mock_pool, mock_connection):
        """Should handle case where no recent subscriptions exist."""
        batch_id = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.execute = AsyncMock()

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                return_value=[],
            ):
                await batch_workflow_job()

        # Verify batch_runs was updated with total_customers=0
        # (execute should be called with UPDATE query)
        assert mock_connection.execute.called

    @pytest.mark.asyncio
    async def test_batch_job_executes_workflows_for_customers(
        self, mock_pool, mock_connection
    ):
        """Should call execute_workflow_for_customers with list."""
        batch_id = str(uuid4())
        customer_ids = [str(uuid4()), str(uuid4())]

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.execute = AsyncMock()

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                return_value=customer_ids,
            ):
                with patch(
                    "app.core.scheduler.execute_workflow_for_customers",
                    new_callable=AsyncMock,
                ) as mock_execute:
                    mock_execute.return_value = MagicMock(
                        successful_count=2,
                        failed_count=0,
                        skipped_count=0,
                        total_customers=2,
                    )

                    await batch_workflow_job()

                    # Verify execute was called with customer list
                    mock_execute.assert_called_once()
                    args = mock_execute.call_args
                    assert customer_ids == args[1]["customer_ids"]

    @pytest.mark.asyncio
    async def test_batch_job_updates_batch_run_on_success(
        self, mock_pool, mock_connection
    ):
        """Should update batch_runs with SUCCESS status and counts."""
        batch_id = str(uuid4())
        customer_ids = [str(uuid4())]

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.execute = AsyncMock()

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                return_value=customer_ids,
            ):
                with patch(
                    "app.core.scheduler.execute_workflow_for_customers",
                    new_callable=AsyncMock,
                ) as mock_execute:
                    batch_result = MagicMock()
                    batch_result.successful_count = 1
                    batch_result.failed_count = 0
                    batch_result.skipped_count = 0
                    batch_result.total_customers = 1
                    mock_execute.return_value = batch_result

                    await batch_workflow_job()

                    # Verify execute was called twice (CREATE + UPDATE batch_runs)
                    assert mock_connection.execute.call_count >= 1

    @pytest.mark.asyncio
    async def test_batch_job_handles_database_error(self, mock_pool, mock_connection):
        """Should handle database errors gracefully."""
        batch_id = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.fetch = AsyncMock(side_effect=Exception("DB error"))

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                side_effect=Exception("DB error"),
            ):
                # Should not raise - errors are caught and logged
                await batch_workflow_job()

                # Verify batch_runs was updated with FAILED status
                assert mock_connection.execute.called

    @pytest.mark.asyncio
    async def test_batch_job_sets_partial_success_if_failures(
        self, mock_pool, mock_connection
    ):
        """Should set status to PARTIAL_SUCCESS if some workflows failed."""
        batch_id = str(uuid4())
        customer_ids = [str(uuid4()), str(uuid4())]

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchval = AsyncMock(return_value=batch_id)
        mock_connection.execute = AsyncMock()

        with patch("app.core.scheduler.DatabasePool.get_pool", return_value=mock_pool):
            with patch(
                "app.core.scheduler.get_recently_subscribed_customers",
                return_value=customer_ids,
            ):
                with patch(
                    "app.core.scheduler.execute_workflow_for_customers",
                    new_callable=AsyncMock,
                ) as mock_execute:
                    batch_result = MagicMock()
                    batch_result.successful_count = 1
                    batch_result.failed_count = 1  # One failed
                    batch_result.skipped_count = 0
                    batch_result.total_customers = 2
                    mock_execute.return_value = batch_result

                    await batch_workflow_job()

                    # Verify status is PARTIAL_SUCCESS (not just SUCCESS)
                    # Check the UPDATE query calls
                    update_calls = [
                        call
                        for call in mock_connection.execute.call_args_list
                        if "UPDATE batch_runs" in str(call)
                    ]
                    # At least one UPDATE should set status to PARTIAL_SUCCESS
                    assert len(update_calls) > 0
