"""
Comprehensive test suite for refiner agent.

Coverage:
- Happy path: feedback → refiner → improved email
- Max refinements: guard against infinite loops
- Loop-back scenario: returns state for critic re-evaluation
- Error handling: missing prerequisites, parsing errors
- Iteration tracking: refinement_count incremented correctly
- Surgical fixes: Refiner doesn't over-improve or invent content
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.graph.state import PipelineState, EmailContent, CriticEvaluation
from app.agents.refiner.node import refiner_node, MAX_REFINEMENTS
from app.schemas.responses import CustomerDetailResponse


@pytest.fixture
def sample_customer_data() -> CustomerDetailResponse:
    """Mock customer with all fields."""
    return CustomerDetailResponse(
        customer_id="cust_12345",
        email="sarah@example.com",
        first_name="Sarah",
        last_name="Johnson",
        customer_name="Sarah Johnson",
        preferred_name="Sarah",
        plan_name="Premium",
    )


@pytest.fixture
def original_email() -> EmailContent:
    """Original email with issues (formal tone, vague CTA)."""
    return EmailContent(
        subject="Welcome to Smoothie",
        body=(
            "Dear Sarah,\n\n"
            "Thank you for joining Smoothie. "
            "We are pleased to have you as a Premium member. "
            "Your subscription includes access to our exclusive smoothie library. "
            "If you wish to get started, please visit our website.\n\n"
            "Regards, The Smoothie Team"
        ),
        personalized_elements=["preferred_name", "plan_name"],
    )


@pytest.fixture
def critic_feedback() -> list[str]:
    """Specific feedback from critic (MODERATE issues)."""
    return [
        "Tone is too formal - make it warmer and more conversational",
        "CTA is vague - tell customer exactly what to do first",
    ]


@pytest.fixture
def pipeline_state(
    sample_customer_data: CustomerDetailResponse,
    original_email: EmailContent,
    critic_feedback: list[str],
) -> PipelineState:
    """Base pipeline state for refiner tests."""
    return PipelineState(
        customer_id="cust_12345",
        customer_data=sample_customer_data,
        generated_email=original_email,
        critic_issues=critic_feedback,
        critic_recommendation="REFINE",
        refinement_count=0,
        correlation_id="test_corr_123",
    )


@pytest.fixture
def mock_llm_response() -> str:
    """
    Mock refined email response from LLM.

    Key features:
    - Warmer, conversational tone (no "Dear", "Regards")
    - Clear, specific CTA (not vague like "visit website")
    - Preserves customer name and plan reference
    - Doesn't invent new benefits/features
    - Reports honest personalization in response
    """
    refined_content = {
        "subject": "Hey Sarah! Welcome to Your Premium Smoothie Journey",
        "body": (
            "Hi Sarah!\n\n"
            "We're so excited you've joined Smoothie Premium! "
            "You're now part of a community getting fresh, delicious smoothies delivered right to your door. "
            "As a Premium member, you have full access to our smoothie library—just browse and pick your favorites.\n\n"
            "Ready to get started? Explore your first smoothie options when you're ready. "
            "It takes just 2 minutes to customize your first week!\n\n"
            "Welcome aboard!\n"
            "The Smoothie Team"
        ),
        "personalized_elements": ["preferred_name", "plan_name"],
    }
    # Wrap in markdown code block (simulating LLM response)
    return f"```json\n{json.dumps(refined_content)}\n```"


class TestRefinerNode:
    """Test refiner node orchestration and loop-back mechanism."""

    @pytest.mark.asyncio
    async def test_refiner_node_success(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test happy path: Refiner receives feedback → improves email → returns refined version.

        Expected:
        - refined_email populated with improved content
        - refinement_count incremented to 1
        - workflow_status = "email_refined"
        - Tone improved (warmer, less formal)
        - CTA improved (specific, not vague)
        """
        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            # Verify refined email returned
            assert "refined_email" in result
            assert result["refined_email"] is not None
            assert isinstance(result["refined_email"], EmailContent)

            # Verify tone improved (warmer language)
            assert "excited" in result["refined_email"].body.lower()
            assert "dear" not in result["refined_email"].body.lower()
            assert "regards" not in result["refined_email"].body.lower()

            # Verify CTA improved (specific, not vague)
            assert "explore" in result["refined_email"].body.lower()
            assert "ready to get started" in result["refined_email"].body.lower()
            assert "visit our website" not in result["refined_email"].body.lower()

            # Verify iteration tracking
            assert result["refinement_count"] == 1
            assert result["workflow_status"] == "email_refined"
            assert result["correlation_id"] == "test_corr_123"

    @pytest.mark.asyncio
    async def test_refiner_node_loop_back_state(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test loop-back mechanism: Refiner output ready for Critic re-evaluation.

        Expected:
        - refined_email populated
        - refiner_last_feedback preserved
        - State ready for Critic to receive and re-evaluate refined_email
        """
        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            # Verify feedback tracked
            assert "refiner_last_feedback" in result
            assert result["refiner_last_feedback"] == pipeline_state["critic_issues"]

            # Verify state ready for Critic to evaluate refined_email
            # (Critic will check state["refined_email"] and re-evaluate)
            assert result["refined_email"] is not None

    @pytest.mark.asyncio
    async def test_refiner_node_max_refinements_exceeded(
        self, pipeline_state: PipelineState
    ):
        """
        Test guard: Prevent infinite loops by enforcing max refinements.

        Setup: refinement_count = 3 (at max)
        Expected:
        - refined_email = None
        - workflow_status = "error_max_refinements_exceeded"
        - No LLM call made (early exit)
        """
        pipeline_state["refinement_count"] = MAX_REFINEMENTS

        result = await refiner_node(pipeline_state)

        # Verify early exit
        assert result["refined_email"] is None
        assert result["workflow_status"] == "error_max_refinements_exceeded"
        assert result["refinement_count"] == MAX_REFINEMENTS

    @pytest.mark.asyncio
    async def test_refiner_node_missing_email(self, pipeline_state: PipelineState):
        """
        Test error handling: Missing generated_email in state.

        Expected:
        - workflow_status = "error_refiner_validation"
        - refined_email = None
        - Error message indicates validation failure
        """
        del pipeline_state["generated_email"]

        result = await refiner_node(pipeline_state)

        assert result["refined_email"] is None
        assert result["workflow_status"] == "error_refiner_validation"
        assert "Missing generated_email" in result.get("error_message", "")

    @pytest.mark.asyncio
    async def test_refiner_node_missing_customer_data(
        self, pipeline_state: PipelineState
    ):
        """
        Test error handling: Missing customer_data in state.

        Expected:
        - workflow_status = "error_refiner_validation"
        - refined_email = None
        """
        del pipeline_state["customer_data"]

        result = await refiner_node(pipeline_state)

        assert result["refined_email"] is None
        assert result["workflow_status"] == "error_refiner_validation"

    @pytest.mark.asyncio
    async def test_refiner_node_llm_parsing_error(self, pipeline_state: PipelineState):
        """
        Test error handling: LLM returns invalid JSON.

        Expected:
        - workflow_status = "error_refiner_validation" (JSON extraction fails)
        - refined_email = None
        - refinement_count NOT incremented (indicates error, not success)
        """
        invalid_response = "This is not valid JSON {broken}"

        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=invalid_response,
        ):
            result = await refiner_node(pipeline_state)

            assert result["refined_email"] is None
            assert result["workflow_status"] == "error_refiner_validation"
            assert result["refinement_count"] == 0  # Not incremented on error

    @pytest.mark.asyncio
    async def test_refiner_node_iteration_2_to_3(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test multi-iteration tracking: Refiner called in iteration 2.

        Setup: refinement_count = 1 (already refined once)
        Expected:
        - refined_email returned
        - refinement_count incremented to 2
        - Ready for second loop-back to Critic
        """
        pipeline_state["refinement_count"] = 1

        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            assert result["refined_email"] is not None
            assert result["refinement_count"] == 2
            assert result["workflow_status"] == "email_refined"

    @pytest.mark.asyncio
    async def test_refiner_node_preserves_personalization(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test personalization preservation: Refiner maintains customer names.

        Expected:
        - refined_email includes customer name usage
        - personalized_elements list matches actual usage
        - Body references Sarah and Premium (don't remove)
        """
        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            refined = result["refined_email"]
            assert refined is not None

            # Verify personalization preserved
            assert "Sarah" in refined.body
            assert "Premium" in refined.body
            assert "preferred_name" in refined.personalized_elements
            assert "plan_name" in refined.personalized_elements

    @pytest.mark.asyncio
    async def test_refiner_node_surgical_fixes_only(
        self, pipeline_state: PipelineState
    ):
        """
        Test surgical fix principle: Only addresses flagged issues, doesn't over-improve.

        Setup: Feedback mentions only CTA clarity
        Expected:
        - Subject NOT changed (wasn't flagged)
        - Body improved for CTA clarity only
        - Original greeting/structure preserved
        """
        # Only one issue: CTA clarity
        pipeline_state["critic_issues"] = [
            "CTA is vague - tell customer exactly what to do first"
        ]

        # Mock response that fixes ONLY CTA, keeps everything else
        cta_only_response = {
            "subject": "Welcome to Smoothie",  # Unchanged
            "body": (
                "Dear Sarah,\n\n"
                "Thank you for joining Smoothie. "
                "We are pleased to have you as a Premium member. "
                "Your subscription includes access to our exclusive smoothie library. "
                "Ready to get started? Explore your first smoothie options when you're ready.\n\n"
                "Regards, The Smoothie Team"  # Still formal, but that wasn't flagged
            ),
            "personalized_elements": ["preferred_name", "plan_name"],
        }
        mock_response = f"```json\n{json.dumps(cta_only_response)}\n```"

        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await refiner_node(pipeline_state)

            refined = result["refined_email"]
            assert refined is not None

            # Verify subject unchanged (not flagged)
            assert refined.subject == "Welcome to Smoothie"

            # Verify CTA improved (was flagged)
            assert "Explore your first smoothie options" in refined.body

    @pytest.mark.asyncio
    async def test_refiner_node_timing_metrics(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test observability: Refinement time tracked.

        Expected:
        - refinement_time_seconds present in result
        - refinement_time_seconds > 0
        """
        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            assert "refinement_time_seconds" in result
            assert result["refinement_time_seconds"] > 0


class TestRefinerEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_refiner_empty_feedback_list(
        self, pipeline_state: PipelineState, mock_llm_response: str
    ):
        """
        Test edge case: Refiner invoked with empty feedback list.

        Expected:
        - Still processes (logs warning)
        - Default message used: "Unspecified improvements requested"
        - refined_email returned
        """
        pipeline_state["critic_issues"] = []

        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_llm_response,
        ):
            result = await refiner_node(pipeline_state)

            assert result["refined_email"] is not None
            assert result["refinement_count"] == 1

    @pytest.mark.asyncio
    async def test_refiner_preserves_original_benefits(
        self, pipeline_state: PipelineState
    ):
        """
        Test constraint: Refiner doesn't invent new benefits/features.

        Setup: Original email mentions "exclusive smoothie library"
        Expected:
        - Refined email keeps that benefit (don't remove)
        - Doesn't add new benefits like "free shipping" or "50+ smoothies"
        """
        # Mock response that preserves original benefits
        preserve_benefits_response = {
            "subject": "Welcome Sarah! Your Premium Smoothie Journey Awaits",
            "body": (
                "Hi Sarah!\n\n"
                "We're thrilled you've joined Smoothie Premium! "
                "You now have access to our exclusive smoothie library with all your favorite options ready to explore.\n\n"
                "Ready to get started? Browse your first smoothie options when you're ready!\n\n"
                "Welcome!\n"
                "The Smoothie Team"
            ),
            "personalized_elements": ["preferred_name", "plan_name"],
        }
        mock_response = f"```json\n{json.dumps(preserve_benefits_response)}\n```"

        with patch(
            "app.agents.refiner.node.call_llm_with_retry",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await refiner_node(pipeline_state)

            refined = result["refined_email"]
            assert refined is not None

            # Verify original benefit preserved
            assert "exclusive smoothie library" in refined.body.lower()

            # Verify no new/invented benefits added
            assert "free" not in refined.body.lower()
            assert "50+" not in refined.body
            assert "unlimited" not in refined.body
