"""
Tests for email pipeline executor (executor.py).

Coverage:
- Entry point function
- State initialization
- Correlation ID generation and preservation
- Error handling
- Final state structure and validation
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.graph.executor import run_email_pipeline
from app.graph.state import PipelineState, EmailContent, CriticEvaluation
from app.schemas.responses import CustomerDetailResponse
import app.graph.workflow as workflow_module

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_workflow_singleton():
    """Reset workflow singleton before each test to allow mocking."""
    workflow_module._workflow = None
    yield
    workflow_module._workflow = None


@pytest.fixture
def sample_customer() -> CustomerDetailResponse:
    """Valid customer for testing."""
    return CustomerDetailResponse(
        customer_id="cust_exec_test_123",
        email="test@example.com",
        first_name="TestUser",
        last_name="TestLast",
        customer_name="TestUser TestLast",
        preferred_name="TestUser",
        plan_name="Basic",
    )


@pytest.fixture
async def mock_workflow_success():
    """Mock successful workflow execution."""
    return {
        "customer_id": "cust_exec_test_123",
        "correlation_id": "test_corr_123",
        "workflow_status": "SENT",
        "message_id": "msg_success_123",
        "sent_at": "2026-10-07T10:00:00Z",
        "generated_email": EmailContent(
            subject="Test Subject",
            body="Test body content",
            personalized_elements=[],
        ),
        "refinement_count": 0,
    }


@pytest.fixture
async def mock_workflow_escalation():
    """Mock workflow that escalates to manual review."""
    return {
        "customer_id": "cust_exec_test_123",
        "correlation_id": "test_corr_123",
        "workflow_status": "MANUAL_REVIEW",
        "generated_email": EmailContent(
            subject="Test Subject",
            body="Test body with PII",
            personalized_elements=[],
        ),
        "critic_issues": ["PII exposed"],
        "refinement_count": 0,
    }


@pytest.fixture
async def mock_workflow_error():
    """Mock workflow that fails."""
    return {
        "customer_id": "cust_exec_test_123",
        "correlation_id": "test_corr_123",
        "workflow_status": "FAILED",
        "error_message": "Unexpected error occurred",
    }


# ============================================================================
# TEST: EXECUTOR ENTRY POINT
# ============================================================================


class TestExecutor:
    """Test run_email_pipeline entry point function."""

    @pytest.mark.asyncio
    async def test_entry_point_happy_path(self, sample_customer, mock_workflow_success):
        """
        Entry point should execute full pipeline and return final state.

        Expected:
        - Result has workflow_status = "SENT"
        - Result has message_id
        - No exceptions raised
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_success)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            assert result["workflow_status"] == "SENT"
            assert result["message_id"] == "msg_success_123"
            mock_workflow.ainvoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_correlation_id_generated_if_not_provided(
        self, sample_customer, mock_workflow_success
    ):
        """
        If no correlation_id provided, executor should generate one.

        Expected:
        - Result has correlation_id field
        - correlation_id is not None and not empty
        """
        with (
            patch("app.graph.executor.get_workflow") as mock_get_workflow,
            patch("app.graph.executor.generate_correlation_id") as mock_gen_id,
        ):
            mock_gen_id.return_value = "generated_corr_123"

            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_success)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
                # No correlation_id provided
            )

            # Verify correlation_id was generated
            mock_gen_id.assert_called_once()

    @pytest.mark.asyncio
    async def test_correlation_id_preserved_if_provided(
        self, sample_customer, mock_workflow_success
    ):
        """
        If correlation_id provided, executor should use it (not generate).

        Expected:
        - Provided correlation_id is preserved in state
        - generate_correlation_id NOT called
        """
        provided_id = "custom_corr_abc123"

        with (
            patch("app.graph.executor.get_workflow") as mock_get_workflow,
            patch("app.graph.executor.generate_correlation_id") as mock_gen_id,
        ):
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_success)
            mock_get_workflow.return_value = mock_workflow

            await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
                correlation_id=provided_id,
            )

            # Should NOT generate new ID if provided
            mock_gen_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_entry_point_escalation_handled(
        self, sample_customer, mock_workflow_escalation
    ):
        """
        Entry point should handle escalation (MANUAL_REVIEW) normally.

        Expected:
        - Result has workflow_status = "MANUAL_REVIEW"
        - No exception raised
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_escalation)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            assert result["workflow_status"] == "MANUAL_REVIEW"
            assert result["critic_issues"] == ["PII exposed"]

    @pytest.mark.asyncio
    async def test_entry_point_error_handling(
        self, sample_customer, mock_workflow_error
    ):
        """
        Entry point should catch errors and return error state (not raise).

        Expected:
        - Result has workflow_status = "FAILED"
        - Result has error_message
        - No exception propagated
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_error)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            assert result["workflow_status"] == "FAILED"
            assert result["error_message"] == "Unexpected error occurred"

    @pytest.mark.asyncio
    async def test_entry_point_workflow_exception_caught(self, sample_customer):
        """
        Entry point should catch workflow exceptions and return error state.

        Expected:
        - Even if workflow.ainvoke() raises, executor catches it
        - Result has workflow_status = "FAILED"
        - Result has error_message with exception details
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(side_effect=Exception("Network error"))
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            assert result["workflow_status"] == "FAILED"
            assert "Network error" in result["error_message"]


# ============================================================================
# TEST: FINAL STATE STRUCTURE
# ============================================================================


class TestFinalStateStructure:
    """Verify final state has required fields for all scenarios."""

    @pytest.mark.asyncio
    async def test_final_state_has_required_fields_success(
        self, sample_customer, mock_workflow_success
    ):
        """
        Success state should have all required fields.

        Expected fields:
        - workflow_status
        - message_id (for SENT)
        - sent_at (for SENT)
        - generated_email
        - customer_id
        - correlation_id
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_success)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            # Required fields for success
            assert "workflow_status" in result
            assert "message_id" in result
            assert "sent_at" in result
            assert "generated_email" in result
            assert "customer_id" in result
            assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_final_state_has_required_fields_escalation(
        self, sample_customer, mock_workflow_escalation
    ):
        """
        Escalation state should have all required fields.

        Expected fields:
        - workflow_status = "MANUAL_REVIEW"
        - critic_issues (reason for escalation)
        - customer_id
        - correlation_id
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_escalation)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            # Required fields for escalation
            assert result["workflow_status"] == "MANUAL_REVIEW"
            assert "critic_issues" in result
            assert "customer_id" in result
            assert "correlation_id" in result

    @pytest.mark.asyncio
    async def test_final_state_has_required_fields_failure(
        self, sample_customer, mock_workflow_error
    ):
        """
        Failure state should have all required fields.

        Expected fields:
        - workflow_status = "FAILED"
        - error_message (reason for failure)
        - customer_id
        - correlation_id
        """
        with patch("app.graph.executor.get_workflow") as mock_get_workflow:
            mock_workflow = AsyncMock()
            mock_workflow.ainvoke = AsyncMock(return_value=mock_workflow_error)
            mock_get_workflow.return_value = mock_workflow

            result = await run_email_pipeline(
                customer_id=sample_customer.customer_id,
                customer_data=sample_customer,
            )

            # Required fields for failure
            assert result["workflow_status"] == "FAILED"
            assert "error_message" in result
            assert "customer_id" in result
            assert "correlation_id" in result
