"""
Phase 6 Tests: Workflow Execution Service

Tests for:
- Workflow execution for single/multiple customers
- Skipping already-processed workflows
- Error handling and recovery
- Batch result aggregation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from uuid import uuid4

from app.services.workflow_execution import (
    execute_workflow_for_customers,
    get_recently_subscribed_customers,
    WorkflowExecutionResult,
    BatchExecutionResult,
)
from app.exceptions.database_exception import DatabaseExecutionException
from app.exceptions.customer_exception import CustomerNotFoundException

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


@pytest.fixture
def mock_customer_data():
    """Mock customer response."""
    from app.schemas.responses import CustomerDetailResponse

    return CustomerDetailResponse(
        customer_id="cust_123",
        first_name="John",
        last_name="Doe",
        customer_name="John Doe",
        preferred_name="John",
        email="john@example.com",
        plan_name="Premium",
    )


@pytest.fixture
def mock_workflow_state():
    """Mock LangGraph workflow state result."""
    return {
        "customer_id": "cust_123",
        "workflow_status": "sent",
        "generated_email": {"subject": "Welcome", "body": "Hello"},
        "error_message": None,
    }


# ============================================================================
# TEST: Batch Execution Result Aggregation
# ============================================================================


class TestBatchExecutionResult:
    """Test BatchExecutionResult data structure."""

    def test_add_result_increments_successful_count(self):
        """Should increment successful_count when adding SUCCESS result."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        result = WorkflowExecutionResult(
            customer_id="cust_1",
            status="SUCCESS",
            message="Success",
        )
        batch.add_result(result)

        assert batch.successful_count == 1
        assert batch.failed_count == 0
        assert len(batch.results) == 1

    def test_add_result_increments_failed_count(self):
        """Should increment failed_count when adding FAILED result."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        result = WorkflowExecutionResult(
            customer_id="cust_1",
            status="FAILED",
            message="Failed",
            error_message="Error",
        )
        batch.add_result(result)

        assert batch.failed_count == 1
        assert batch.successful_count == 0

    def test_add_result_increments_skipped_count(self):
        """Should increment skipped_count when adding SKIPPED result."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        result = WorkflowExecutionResult(
            customer_id="cust_1",
            status="SKIPPED",
            message="Skipped",
        )
        batch.add_result(result)

        assert batch.skipped_count == 1
        assert batch.successful_count == 0
        assert batch.failed_count == 0

    def test_add_multiple_results_aggregates_correctly(self):
        """Should correctly aggregate multiple mixed results."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION", total_customers=4)
        batch.add_result(
            WorkflowExecutionResult(
                customer_id="cust_1", status="SUCCESS", message="OK"
            )
        )
        batch.add_result(
            WorkflowExecutionResult(
                customer_id="cust_2", status="SUCCESS", message="OK"
            )
        )
        batch.add_result(
            WorkflowExecutionResult(
                customer_id="cust_3",
                status="FAILED",
                message="Error",
                error_message="E",
            )
        )
        batch.add_result(
            WorkflowExecutionResult(
                customer_id="cust_4", status="SKIPPED", message="Skip"
            )
        )

        assert batch.total_customers == 4
        assert batch.successful_count == 2
        assert batch.failed_count == 1
        assert batch.skipped_count == 1
        assert len(batch.results) == 4


# ============================================================================
# TEST: Workflow Execution Service
# ============================================================================


class TestWorkflowExecutionService:
    """Test execute_workflow_for_customers function."""

    @pytest.mark.asyncio
    async def test_execute_workflow_skips_existing_workflow_run(
        self, mock_pool, mock_connection, mock_customer_data
    ):
        """Should skip customer if workflow_runs record already exists."""
        workflow_run_id = str(uuid4())

        # Mock pool.acquire()
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # Mock fetchrow to return existing workflow
        mock_connection.fetchrow = AsyncMock(return_value={"id": workflow_run_id})

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            batch_result = await execute_workflow_for_customers(
                customer_ids=["cust_123"],
                workflow_type="NEW_REGISTRATION",
            )

        assert batch_result.skipped_count == 1
        assert batch_result.successful_count == 0
        assert batch_result.failed_count == 0
        assert batch_result.results[0].status == "SKIPPED"

    @pytest.mark.asyncio
    async def test_execute_workflow_creates_workflow_run(
        self, mock_pool, mock_connection, mock_customer_data, mock_workflow_state
    ):
        """Should create workflow_runs record if not exists."""
        workflow_run_id = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # First call: fetchrow returns None (no existing)
        # Then: fetchval returns new workflow_run_id
        mock_connection.fetchrow = AsyncMock(return_value=None)
        mock_connection.fetchval = AsyncMock(return_value=workflow_run_id)
        mock_connection.execute = AsyncMock()

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            with patch(
                "app.services.workflow_execution.fetch_customer_subscription_details_from_db",
                return_value=mock_customer_data,
            ):
                with patch(
                    "app.services.workflow_execution.run_email_pipeline",
                    return_value=mock_workflow_state,
                ):
                    batch_result = await execute_workflow_for_customers(
                        customer_ids=["cust_123"],
                        workflow_type="NEW_REGISTRATION",
                    )

        assert batch_result.successful_count == 1
        # Verify workflow_runs was created (fetchval called)
        assert mock_connection.fetchval.called

    @pytest.mark.asyncio
    async def test_execute_workflow_handles_customer_not_found(
        self, mock_pool, mock_connection
    ):
        """Should handle CustomerNotFoundException gracefully."""
        workflow_run_id = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_connection.fetchrow = AsyncMock(return_value=None)
        mock_connection.fetchval = AsyncMock(return_value=workflow_run_id)
        mock_connection.execute = AsyncMock()

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            with patch(
                "app.services.workflow_execution.fetch_customer_subscription_details_from_db",
                side_effect=CustomerNotFoundException(
                    customer_id="cust_123",
                    error_message="Not found",
                ),
            ):
                batch_result = await execute_workflow_for_customers(
                    customer_ids=["cust_123"],
                    workflow_type="NEW_REGISTRATION",
                )

        assert batch_result.failed_count == 1
        assert batch_result.results[0].status == "FAILED"

    @pytest.mark.asyncio
    async def test_execute_workflow_continues_on_individual_failure(
        self, mock_pool, mock_connection, mock_customer_data, mock_workflow_state
    ):
        """Should continue processing other customers if one fails."""
        workflow_run_id_1 = str(uuid4())
        workflow_run_id_2 = str(uuid4())

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        # First customer: no existing, create, then LangGraph fails
        # Second customer: no existing, create, succeeds
        mock_connection.fetchrow = AsyncMock(return_value=None)
        mock_connection.fetchval = AsyncMock(
            side_effect=[workflow_run_id_1, workflow_run_id_2]
        )
        mock_connection.execute = AsyncMock()

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            with patch(
                "app.services.workflow_execution.fetch_customer_subscription_details_from_db",
                return_value=mock_customer_data,
            ):
                with patch(
                    "app.services.workflow_execution.run_email_pipeline",
                    side_effect=[
                        Exception("Workflow error"),
                        mock_workflow_state,
                    ],
                ):
                    batch_result = await execute_workflow_for_customers(
                        customer_ids=["cust_1", "cust_2"],
                        workflow_type="NEW_REGISTRATION",
                    )

        # One failed, one succeeded
        assert batch_result.failed_count == 1
        assert batch_result.successful_count == 1
        assert len(batch_result.results) == 2


# ============================================================================
# TEST: Recently Subscribed Customers
# ============================================================================


class TestGetRecentlySubscribedCustomers:
    """Test get_recently_subscribed_customers function."""

    @pytest.mark.asyncio
    async def test_returns_customer_list(self, mock_pool, mock_connection):
        """Should return list of customer UUIDs."""
        customer_ids = [str(uuid4()), str(uuid4()), str(uuid4())]
        rows = [{"customer_id": cid} for cid in customer_ids]

        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=rows)

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            result = await get_recently_subscribed_customers()

        assert len(result) == 3
        assert result == customer_ids

    @pytest.mark.asyncio
    async def test_returns_empty_list_if_no_recent_subscriptions(
        self, mock_pool, mock_connection
    ):
        """Should return empty list if no recent subscriptions."""
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(return_value=[])

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            result = await get_recently_subscribed_customers()

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_on_database_error(self, mock_pool, mock_connection):
        """Should raise DatabaseExecutionException on DB error."""
        mock_pool.acquire = MagicMock()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(
            return_value=mock_connection
        )
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_connection.fetch = AsyncMock(side_effect=Exception("DB error"))

        with patch(
            "app.services.workflow_execution.DatabasePool.get_pool",
            return_value=mock_pool,
        ):
            with pytest.raises(DatabaseExecutionException):
                await get_recently_subscribed_customers()
