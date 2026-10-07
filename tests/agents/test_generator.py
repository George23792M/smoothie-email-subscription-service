"""
Unit tests for app/agents/generator/node.py

Focus: Happy path + Input validation

Test Coverage:
- Success: Complete email generation
- Input validation: Missing/invalid customer data
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.generator.node import generator_node
from app.agents.utils import generate_correlation_id
from app.guardrails.input_guards import GuardRailResult
from app.schemas.responses import CustomerDetailResponse
from app.graph.state import PipelineState, EmailContent

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_customer_data() -> CustomerDetailResponse:
    """Valid customer data from database."""
    return CustomerDetailResponse(
        customer_id="cust_12345",
        first_name="Sarah",
        last_name="Smith",
        customer_name="Sarah Smith",
        preferred_name="Sarah",
        email="sarah@example.com",
        plan_name="Premium",
        signup_date="2024-01-15",
    )


@pytest.fixture
def pipeline_state(sample_customer_data: CustomerDetailResponse) -> PipelineState:
    """Initial PipelineState for testing (LangGraph state)."""
    return PipelineState(
        customer_id=sample_customer_data.customer_id,
        customer_data=sample_customer_data,
        correlation_id=generate_correlation_id(),
        input_guardrail_passed=True,  # Prerequisites met
        input_guardrail_result=GuardRailResult(
            passed=True,
            violations=[],
            severity="PASS",
            layer="input",
            details=None,
        ),
    )


@pytest.fixture
def mock_llm_response() -> str:
    """Mock ChatOpenAI response (markdown JSON block)."""
    return """```json
{
  "subject": "Welcome to Smoothie, Sarah!",
  "body": "Hi Sarah,\\n\\nThank you for joining Smoothie! We're thrilled to have you as a Premium subscriber.\\n\\nYou're now part of a vibrant community.\\n\\nCheers,\\nThe Smoothie Team",
  "personalized_elements": ["preferred_name_used", "plan_name_mentioned"]
}
```"""


@pytest.fixture
def mock_output_guards() -> AsyncMock:
    """Mock OutputGuards validation (all checks pass)."""
    mock = AsyncMock()
    mock.return_value = GuardRailResult(
        passed=True,
        violations=[],
        severity="PASS",
        layer="output",
        details=None,
    )
    return mock


# ============================================================================
# HAPPY PATH TEST
# ============================================================================


@pytest.mark.asyncio
async def test_generator_node_success(
    pipeline_state: PipelineState,
    mock_llm_response: str,
    mock_output_guards: AsyncMock,
) -> None:
    """
    Test successful email generation.

    Steps:
    1. Validate prerequisites (input guardrails passed)
    2. Build context from customer data
    3. Render prompt template
    4. Call LLM
    5. Parse JSON response
    6. Validate output with guardrails
    7. Return generated email

    Expected: generated_email returned with subject, body, personalized_elements.
    """
    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_output_guards,
        ):
            result = await generator_node(pipeline_state)

    # Assertions
    assert result is not None
    assert "generated_email" in result
    assert result["generated_email"] is not None
    assert isinstance(result["generated_email"], EmailContent)
    assert result["generated_email"].subject == "Welcome to Smoothie, Sarah!"
    assert "Premium subscriber" in result["generated_email"].body
    assert "preferred_name_used" in result["generated_email"].personalized_elements
    assert result["output_guardrail_passed"] is True


# ============================================================================
# INPUT VALIDATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_generator_node_missing_customer_data() -> None:
    """
    Test error when customer_data is missing from state.

    Expected: Returns with error status (node catches and logs).
    """
    state = PipelineState(
        customer_id="cust_123",
        customer_data=None,  # Missing!
        correlation_id=generate_correlation_id(),
        input_guardrail_passed=True,
    )

    result = await generator_node(state)

    # Node catches ValueError and returns error status
    assert result["workflow_status"] == "error_generator_validation"
    assert result["generated_email"] is None


@pytest.mark.asyncio
async def test_generator_node_input_guardrail_failed(
    pipeline_state: PipelineState,
) -> None:
    """
    Test error handling when input guardrails failed.

    Expected: Early exit with workflow_status = stopped_input_validation_failed.
    """
    pipeline_state["input_guardrail_passed"] = False

    result = await generator_node(pipeline_state)

    # Should return early without calling LLM
    assert result["workflow_status"] == "stopped_input_validation_failed"
    assert result["generated_email"] is None
    assert result["output_guardrail_passed"] is False


@pytest.mark.asyncio
async def test_generator_node_llm_timeout_error(
    pipeline_state: PipelineState,
) -> None:
    """
    Test error handling when LLM call times out.

    Expected: Node catches error and returns error status.
    """
    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.side_effect = TimeoutError("LLM request timed out after 30s")

        result = await generator_node(pipeline_state)

    # Node catches and handles timeout
    assert result["workflow_status"] == "error_generator_unexpected"
    assert result["generated_email"] is None


@pytest.mark.asyncio
async def test_generator_node_guardrail_failure(
    pipeline_state: PipelineState,
    mock_llm_response: str,
) -> None:
    """
    Test error handling when output guardrails fail.

    Expected: Return with output_guardrail_passed=False.
    """
    mock_guards = AsyncMock()
    mock_guards.return_value = GuardRailResult(
        passed=False,
        violations=["subject_too_long"],
        severity="CRITICAL",
        layer="output",
        details={"subject_length": 150},
    )

    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_guards,
        ):
            result = await generator_node(pipeline_state)

    # Should return with guardrail failure
    assert result["output_guardrail_passed"] is False
    assert result["workflow_status"] == "stopped_output_validation_failed"
    assert (
        result["generated_email"] is not None
    )  # Email was generated but failed validation


# ============================================================================
# INVALID JSON RESPONSE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_generator_node_invalid_json_response(
    pipeline_state: PipelineState,
) -> None:
    """
    Test error handling when LLM returns invalid JSON.

    Expected: Node catches ValueError from parse_llm_response and returns error.
    """
    invalid_json = "```json\n{invalid json, no quotes}\n```"

    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = invalid_json

        result = await generator_node(pipeline_state)

    # Should handle parsing error gracefully
    assert result["workflow_status"] == "error_generator_validation"
    assert result["generated_email"] is None
    assert result["output_guardrail_passed"] is False


@pytest.mark.asyncio
async def test_generator_node_missing_required_fields(
    pipeline_state: PipelineState,
) -> None:
    """
    Test error handling when JSON is missing required fields.

    Expected: Pydantic validation fails, node catches ValueError.
    """
    invalid_response = """```json
{
  "subject": "Welcome!",
  "body": "Thank you for joining"
}
```"""  # Missing personalized_elements

    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = invalid_response

        result = await generator_node(pipeline_state)

    # Should handle validation error gracefully
    assert result["workflow_status"] == "error_generator_validation"
    assert result["generated_email"] is None


@pytest.mark.asyncio
async def test_generator_node_empty_llm_response(
    pipeline_state: PipelineState,
) -> None:
    """
    Test error handling when LLM returns empty response.

    Expected: ValueError raised, caught by exception handler.
    """
    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = ""

        result = await generator_node(pipeline_state)

    # Should handle empty response gracefully
    assert result["workflow_status"] == "error_generator_validation"
    assert result["generated_email"] is None


# ============================================================================
# PERFORMANCE & METRICS TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_generator_node_tracks_timing(
    pipeline_state: PipelineState,
    mock_llm_response: str,
    mock_output_guards: AsyncMock,
) -> None:
    """
    Test that generation time is properly tracked.

    Expected: generation_time_seconds is recorded and > 0.
    """
    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_output_guards,
        ):
            result = await generator_node(pipeline_state)

    # Verify timing is tracked
    assert "generation_time_seconds" in result
    assert result["generation_time_seconds"] >= 0.0


@pytest.mark.asyncio
async def test_generator_node_preserves_correlation_id(
    pipeline_state: PipelineState,
    mock_llm_response: str,
    mock_output_guards: AsyncMock,
) -> None:
    """
    Test that correlation_id is preserved through workflow.

    Expected: correlation_id in result matches input.
    """
    original_correlation_id = pipeline_state["correlation_id"]

    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_output_guards,
        ):
            result = await generator_node(pipeline_state)

    # Verify correlation_id is preserved
    assert result["correlation_id"] == original_correlation_id


@pytest.mark.asyncio
async def test_generator_node_generates_correlation_id_if_missing(
    sample_customer_data: CustomerDetailResponse,
    mock_llm_response: str,
    mock_output_guards: AsyncMock,
) -> None:
    """
    Test that generator generates correlation_id if not provided in state.

    Expected: correlation_id is generated and present in result.
    """
    state = PipelineState(
        customer_id=sample_customer_data.customer_id,
        customer_data=sample_customer_data,
        correlation_id=None,  # Not provided
        input_guardrail_passed=True,
    )

    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_output_guards,
        ):
            result = await generator_node(state)

    # Verify correlation_id was generated
    assert result["correlation_id"] is not None
    assert len(result["correlation_id"]) > 0
    assert result["workflow_status"] == "email_generated"


# ============================================================================
# STATE UPDATE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_generator_node_returns_state_update_dict(
    pipeline_state: PipelineState,
    mock_llm_response: str,
    mock_output_guards: AsyncMock,
) -> None:
    """
    Test that generator returns proper state update dictionary.

    Expected: Result is a dict (not EmailContent), with all required fields.
    """
    with patch("app.agents.generator.node.call_llm_with_retry") as mock_llm:
        mock_llm.return_value = mock_llm_response

        with patch(
            "app.agents.generator.node.OutputGuards.validate_generated_email",
            new=mock_output_guards,
        ):
            result = await generator_node(pipeline_state)

    # Verify structure is correct for LangGraph merge
    assert isinstance(result, dict)
    assert "generated_email" in result
    assert "output_guardrail_passed" in result
    assert "output_guardrail_result" in result
    assert "generation_time_seconds" in result
    assert "correlation_id" in result
    assert "workflow_status" in result


# ============================================================================
# RUN TESTS
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
