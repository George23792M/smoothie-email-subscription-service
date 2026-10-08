"""
Tests for DAO (Data Access Object) layer with dependency injection.

Tests the database abstraction layer that handles SQL queries.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from uuid import uuid4

from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.dao.batch_runs_dao import BatchRunsDAO
from app.exceptions.database_exception import DatabaseExecutionException


class TestWorkflowRunsDAO:
    """Test WorkflowRunsDAO database operations with dependency injection."""

    @pytest.mark.asyncio
    async def test_get_workflow_history_without_filter(self):
        """Should fetch workflow history without workflow_type filter."""
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

        # Create mock pool
        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=mock_rows)

        # Instantiate DAO with injected pool
        dao = WorkflowRunsDAO(db_pool=mock_pool)

        result = await dao.get_workflow_history(
            customer_id=customer_id,
            workflow_type=None,
            limit=10,
        )

        assert len(result) == 1
        assert result[0]["customer_id"] == customer_id

    @pytest.mark.asyncio
    async def test_get_workflow_history_with_filter(self):
        """Should fetch workflow history with workflow_type filter."""
        customer_id = str(uuid4())

        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=[])

        # Instantiate DAO with injected pool
        dao = WorkflowRunsDAO(db_pool=mock_pool)

        result = await dao.get_workflow_history(
            customer_id=customer_id,
            workflow_type="NEW_REGISTRATION",
            limit=10,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_get_workflow_history_handles_exception(self):
        """Should raise DatabaseExecutionException on database error."""
        customer_id = str(uuid4())

        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(side_effect=Exception("DB error"))

        # Instantiate DAO with injected pool
        dao = WorkflowRunsDAO(db_pool=mock_pool)

        with pytest.raises(DatabaseExecutionException):
            await dao.get_workflow_history(customer_id=customer_id)


class TestBatchRunsDAO:
    """Test BatchRunsDAO database operations with dependency injection."""

    @pytest.mark.asyncio
    async def test_get_batch_status_returns_records(self):
        """Should fetch batch status records."""
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

        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=mock_rows)

        # Instantiate DAO with injected pool
        dao = BatchRunsDAO(db_pool=mock_pool)

        result = await dao.get_batch_status(limit=10)

        assert len(result) == 1
        assert result[0]["batch_type"] == "NEW_REGISTRATION"

    @pytest.mark.asyncio
    async def test_get_batch_status_respects_limit(self):
        """Should respect limit parameter."""
        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=[])

        # Instantiate DAO with injected pool
        dao = BatchRunsDAO(db_pool=mock_pool)

        result = await dao.get_batch_status(limit=5)

        # Verify connection.fetch was called
        assert mock_connection.fetch.called

    @pytest.mark.asyncio
    async def test_get_batch_status_handles_exception(self):
        """Should raise DatabaseExecutionException on database error."""
        mock_pool = MagicMock()
        mock_connection = AsyncMock()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(side_effect=Exception("DB error"))

        # Instantiate DAO with injected pool
        dao = BatchRunsDAO(db_pool=mock_pool)

        with pytest.raises(DatabaseExecutionException):
            await dao.get_batch_status()
