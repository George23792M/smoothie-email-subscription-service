"""Tests for MCP-backed registration workflow execution."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.postgres_workflows import RegistrationClaim
from app.services.workflow_execution import (
    BatchExecutionResult, DeliveryUnavailableError, WorkflowExecutionResult,
    execute_claim, execute_workflow_for_customers,
)


@pytest.fixture
def claim():
    """Provide one owned synthetic registration claim."""
    return RegistrationClaim(
        id=uuid4(), customer_id=uuid4(), claimed_by="test-worker",
        workflow_type="NEW_REGISTRATION", status="RUNNING", attempt_count=0,
    )


class TestBatchExecutionResult:
    """Check outcome aggregation independently of external services."""

    def test_add_result_increments_successful_count(self):
        """A successful workflow increments only successful_count."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        batch.add_result(WorkflowExecutionResult("customer", "SUCCESS", "ok"))
        assert (batch.successful_count, batch.failed_count, batch.skipped_count) == (1, 0, 0)

    def test_add_result_increments_failed_count(self):
        """A failed workflow increments only failed_count."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        batch.add_result(WorkflowExecutionResult("customer", "FAILED", "failed"))
        assert (batch.successful_count, batch.failed_count, batch.skipped_count) == (0, 1, 0)

    def test_add_result_increments_skipped_count(self):
        """A skipped workflow increments only skipped_count."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION")
        batch.add_result(WorkflowExecutionResult("customer", "SKIPPED", "skipped"))
        assert (batch.successful_count, batch.failed_count, batch.skipped_count) == (0, 0, 1)

    def test_add_multiple_results_aggregates_correctly(self):
        """Multiple outcomes aggregate without changing the configured total."""
        batch = BatchExecutionResult(batch_type="NEW_REGISTRATION", total_customers=3)
        for status in ("SUCCESS", "FAILED", "SKIPPED"):
            batch.add_result(WorkflowExecutionResult("customer", status, status))
        assert (batch.total_customers, batch.successful_count, batch.failed_count, batch.skipped_count) == (3, 1, 1, 1)


class TestWorkflowExecutionService:
    """Verify the disabled execution boundary."""

    @pytest.mark.parametrize("ready", [False, True])
    @pytest.mark.asyncio
    async def test_targeted_execution_never_acquires_adapter(self, ready):
        """A readiness override cannot enable targeted claims."""
        with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready), \
             patch("app.services.postgres_workflows.get_postgres_workflows") as factory:
            with pytest.raises(DeliveryUnavailableError):
                await execute_workflow_for_customers([str(uuid4())])
        factory.assert_not_called()

    @pytest.mark.parametrize("ready", [False, True])
    @pytest.mark.asyncio
    async def test_direct_claim_has_no_side_effects(self, claim, ready):
        """A supplied claim and adapter are never touched."""
        adapter = AsyncMock()
        with patch("app.services.delivery_readiness.is_delivery_ready", return_value=ready):
            with pytest.raises(DeliveryUnavailableError):
                await execute_claim(adapter, claim)
        assert adapter.mock_calls == []
