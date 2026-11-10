"""Tests for the disabled registration scheduler."""

from unittest.mock import MagicMock, patch

import pytest

from app.core.scheduler import batch_workflow_job, get_scheduler, initialize_scheduler, shutdown_scheduler


class TestSchedulerLifecycle:
    """Verify disabled startup and safe shutdown."""

    def test_get_scheduler_returns_singleton(self):
        """Return the same scheduler instance."""
        assert get_scheduler() is get_scheduler()

    @pytest.mark.parametrize("ready", [False, True])
    @pytest.mark.asyncio
    async def test_initialize_scheduler_does_not_start(self, monkeypatch, ready):
        """Readiness cannot enable scheduler job registration or startup."""
        import app.core.scheduler as scheduler_module

        scheduler = MagicMock(running=False)
        monkeypatch.setattr(scheduler_module, "_scheduler", scheduler)
        with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready), \
             patch("app.services.postgres_workflows.get_postgres_workflows") as factory:
            await initialize_scheduler()
        scheduler.add_job.assert_not_called()
        scheduler.start.assert_not_called()
        factory.assert_not_called()

    @pytest.mark.parametrize("running", [False, True])
    @pytest.mark.asyncio
    async def test_shutdown_scheduler(self, monkeypatch, running):
        """Shutdown stops running schedulers and leaves stopped ones alone."""
        import app.core.scheduler as scheduler_module

        scheduler = MagicMock(running=running)
        monkeypatch.setattr(scheduler_module, "_scheduler", scheduler)
        await shutdown_scheduler()
        if running:
            scheduler.shutdown.assert_called_once_with(wait=True)
        else:
            scheduler.shutdown.assert_not_called()


class TestBatchWorkflowJob:
    """Verify direct batch invocation cannot mutate data."""

    @pytest.mark.parametrize("ready", [False, True])
    @pytest.mark.asyncio
    async def test_batch_job_never_acquires_adapter(self, ready):
        """Readiness cannot enable batch creation or claims."""
        with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready), \
             patch("app.services.postgres_workflows.get_postgres_workflows") as factory:
            await batch_workflow_job()
        factory.assert_not_called()
