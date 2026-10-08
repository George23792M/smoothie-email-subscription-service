"""
Tests for WorkflowService layer with dependency injection.

Tests the service abstraction that orchestrates DAOs and transforms data.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4

from app.services.workflow_service import WorkflowService
from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.dao.batch_runs_dao import BatchRunsDAO
from app.api.schemas.responses import WorkflowHistoryItem, BatchRunItem
from app.exceptions.database_exception import DatabaseExecutionException


class TestWorkflowServiceGetHistory:
    """Test WorkflowService.get_workflow_history()."""

    @pytest.mark.asyncio
    async def test_get_workflow_history_returns_items(self):
        """Should fetch and transform workflow history."""
        customer_id = str(uuid4())
        workflow_run_id = str(uuid4())

        mock_rows = [
            {
                "id": workflow_run_id,
                "customer_id": customer_id,
                "workflow_type": "NEW_REGISTRATION",
                "status": "SUCCESS",
                "email_status": "SENT",
                "attempt_count": 1,
                "started_at": datetime.utcnow(),
                "completed_at": datetime.utcnow(),
                "validation_errors": None,
            }
        ]

        # Inject mock DAOs
        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_workflow_dao.get_workflow_history = AsyncMock(return_value=mock_rows)
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        history = await service.get_workflow_history(
            customer_id=customer_id,
            workflow_type=None,
            limit=10,
        )

        assert len(history) == 1
        assert isinstance(history[0], WorkflowHistoryItem)
        assert history[0].customer_id == customer_id
        assert history[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_get_workflow_history_filters_by_type(self):
        """Should pass workflow_type filter to DAO."""
        customer_id = str(uuid4())

        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_workflow_dao.get_workflow_history = AsyncMock(return_value=[])
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        await service.get_workflow_history(
            customer_id=customer_id,
            workflow_type="NEW_REGISTRATION",
            limit=10,
        )

        # Verify DAO was called with workflow_type
        mock_workflow_dao.get_workflow_history.assert_called_once()
        call_kwargs = mock_workflow_dao.get_workflow_history.call_args[1]
        assert call_kwargs["workflow_type"] == "NEW_REGISTRATION"

    @pytest.mark.asyncio
    async def test_get_workflow_history_returns_empty_list(self):
        """Should return empty list if no records found."""
        customer_id = str(uuid4())

        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_workflow_dao.get_workflow_history = AsyncMock(return_value=[])
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        history = await service.get_workflow_history(customer_id=customer_id)

        assert history == []

    @pytest.mark.asyncio
    async def test_get_workflow_history_handles_dao_exception(self):
        """Should re-raise DatabaseExecutionException from DAO."""
        customer_id = str(uuid4())

        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_workflow_dao.get_workflow_history = AsyncMock(
            side_effect=DatabaseExecutionException("DB error")
        )
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        with pytest.raises(DatabaseExecutionException):
            await service.get_workflow_history(customer_id=customer_id)


class TestWorkflowServiceGetBatchStatus:
    """Test WorkflowService.get_batch_status()."""

    @pytest.mark.asyncio
    async def test_get_batch_status_returns_items(self):
        """Should fetch and transform batch status."""
        batch_id = str(uuid4())

        mock_rows = [
            {
                "id": batch_id,
                "batch_type": "NEW_REGISTRATION",
                "status": "SUCCESS",
                "total_customers": 10,
                "successful_count": 10,
                "failed_count": 0,
                "skipped_count": 0,
                "started_at": datetime.utcnow(),
                "completed_at": datetime.utcnow(),
                "error_message": None,
            }
        ]

        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)
        mock_batch_dao.get_batch_status = AsyncMock(return_value=mock_rows)

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        batch_status = await service.get_batch_status(limit=10)

        assert len(batch_status) == 1
        assert isinstance(batch_status[0], BatchRunItem)
        assert batch_status[0].batch_type == "NEW_REGISTRATION"
        assert batch_status[0].status == "SUCCESS"

    @pytest.mark.asyncio
    async def test_get_batch_status_respects_limit(self):
        """Should pass limit parameter to DAO."""
        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)
        mock_batch_dao.get_batch_status = AsyncMock(return_value=[])

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        await service.get_batch_status(limit=5)

        # Verify DAO was called with limit
        mock_batch_dao.get_batch_status.assert_called_once_with(limit=5)

    @pytest.mark.asyncio
    async def test_get_batch_status_returns_empty_list(self):
        """Should return empty list if no records found."""
        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)
        mock_batch_dao.get_batch_status = AsyncMock(return_value=[])

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        batch_status = await service.get_batch_status()

        assert batch_status == []

    @pytest.mark.asyncio
    async def test_get_batch_status_handles_dao_exception(self):
        """Should re-raise DatabaseExecutionException from DAO."""
        mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
        mock_batch_dao = MagicMock(spec=BatchRunsDAO)
        mock_batch_dao.get_batch_status = AsyncMock(
            side_effect=DatabaseExecutionException("DB error")
        )

        service = WorkflowService(
            workflow_runs_dao=mock_workflow_dao,
            batch_runs_dao=mock_batch_dao,
        )

        with pytest.raises(DatabaseExecutionException):
            await service.get_batch_status()
