"""
Comprehensive tests for LangGraph workflow orchestration.

Coverage:
- Workflow construction and graph building
- Happy path: Email sent on first try
- Refine loop: Critic → Refiner → Critic (1-2 iterations)
- Max refinements guard: Prevent infinite loops
- Escalation scenarios: CRITICAL, MANUAL_REVIEW, final guard failure
- Error handling: Network errors, parsing failures
- State transitions and routing logic
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from app.graph.state import PipelineState, EmailContent, CriticEvaluation
from app.graph.workflow import (
    get_workflow,
    build_workflow,
    route_after_critic,
    route_after_refiner,
    route_after_final_guardrails,
)
from app.graph.executor import run_email_pipeline
from app.schemas.responses import CustomerDetailResponse
from app.guardrails.input_guards import GuardRailResult
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
    """Valid customer with all required fields"""
    return CustomerDetailResponse(
        customer_id="cust_test_123",
        email="sarah@example.com",
        first_name="Sarah",
        last_name="Smith",
        customer_name="Sarah Smith",
        preferred_name="Sarah",
        plan_name="Weekly",
    )


@pytest.fixture
def valid_generated_email() -> EmailContent:
    """Valid email from generator node."""
    return EmailContent(
        subject="Welcome to Smoothie, Sarah!",
        body="Hi Sarah, welcome to your Weekly smoothie plan. We're exicted to have you!",
        personalized_elements=["first_name_used", "plan_name_mentioned"],
    )


@pytest.fixture
def critic_evaluation_send() -> CriticEvaluation:
    """Critic evaluation recommending SEND"""
    return CriticEvaluation(
        is_valid=True,
        severity="PASS",
        issues=[],
        recommendation="SEND",
        reasoning="Email passes all quality checks and is ready to send.",
    )


@pytest.fixture
def critic_evaluation_refine() -> CriticEvaluation:
    """Critic evaluation recommending REFINE."""
    return CriticEvaluation(
        is_valid=False,
        severity="MODERATE",
        issues=["Tone is too formal", "CTA is unclear"],
        recommendation="REFINE",
        reasoning="Email has quality issues that need refinement.",
    )


@pytest.fixture
def critic_evaluation_critical() -> CriticEvaluation:
    """Critic evaluation with CRITICAL issues."""
    return CriticEvaluation(
        is_valid=False,
        severity="CRITICAL",
        issues=["Email contains PII: customer@example.com exposed"],
        recommendation="MANUAL_REVIEW",
        reasoning="Critical compliance issue detected. Escalating to manual review.",
    )


@pytest.fixture
def guardrail_result_pass() -> GuardRailResult:
    """Guardrail check that passes."""
    return GuardRailResult(
        passed=True,
        violations=[],
        severity="PASS",
        layer="final",
    )


@pytest.fixture
def guardrail_result_fail() -> GuardRailResult:
    """Guardrail check that fails."""
    return GuardRailResult(
        passed=False,
        violations=["Subject contains banned phrase"],
        severity="CRITICAL",
        layer="final",
    )


# ============================================================================
# TEST: WORKFLOW CONSTRUCTION
# ============================================================================


class TestWorkflowConstruction:
    """Verify workflow builds and compiles correctly."""

    def test_build_workflow_returns_state_graph(self):
        """build_workflow() should return a StateGraph instance."""
        workflow = build_workflow()
        assert workflow is not None

    def test_get_workflow_returns_compiled_graph(self):
        """get_workflow() should return compiled callable graph."""
        workflow = get_workflow()
        assert workflow is not None
        # Verify it's callable (has ainvoke method for async execution)
        assert hasattr(workflow, "ainvoke")

    def test_get_workflow_singleton_pattern(self):
        """get_workflow() should return same instance on multiple calls."""
        workflow1 = get_workflow()
        workflow2 = get_workflow()
        assert workflow1 is workflow2


# ============================================================================
# TEST: ROUTING LOGIC
# ============================================================================


class TestRoutingLogic:
    """Test conditional routing functions."""

    def test_route_after_critic_send_goes_to_final_guardrails(self):
        """SEND recommendation should route to final_guardrails."""
        state = PipelineState(
            customer_id="cust_123",
            critic_recommendation="SEND",
            refinement_count=0,
        )
        assert route_after_critic(state) == "final_guardrails"

    def test_route_after_critic_refine_goes_to_refiner(self):
        """REFINE recommendation should route to refiner."""
        state = PipelineState(
            customer_id="cust_123",
            critic_recommendation="REFINE",
            refinement_count=0,
        )
        assert route_after_critic(state) == "refiner"

    def test_route_after_critic_manual_review_escalates(self):
        """MANUAL_REVIEW recommendation should escalate."""
        state = PipelineState(
            customer_id="cust_123",
            critic_recommendation="MANUAL_REVIEW",
            refinement_count=0,
        )
        assert route_after_critic(state) == "escalate"

    def test_route_after_critic_max_refinements_escalates(self):
        """Max refinements reached with REFINE should escalate."""
        state = PipelineState(
            customer_id="cust_123",
            critic_recommendation="REFINE",
            refinement_count=3,
        )
        assert route_after_critic(state) == "escalate"

    def test_route_after_refiner_success_loops_back(self):
        """Successful refiner should loop back to critic."""
        state = PipelineState(
            customer_id="cust_123",
            workflow_status="email_refined",
            refinement_count=1,
        )
        assert route_after_refiner(state) == "critic"

    def test_route_after_refiner_error_escalates(self):
        """Refiner error should escalate."""
        state = PipelineState(
            customer_id="cust_123",
            workflow_status="error_refiner_parsing",
            error_message="Invalid JSON from LLM",
        )
        assert route_after_refiner(state) == "escalate"

    def test_route_after_final_guardrails_pass_sends_email(self):
        """Final guardrail pass should route to send_email."""
        state = PipelineState(
            customer_id="cust_123",
            final_guardrail_passed=True,
        )
        assert route_after_final_guardrails(state) == "send_email"

    def test_route_after_final_guardrails_fail_escalates(self):
        """Final guardrail fail should escalate."""
        state = PipelineState(
            customer_id="cust_123",
            final_guardrail_passed=False,
        )
        assert route_after_final_guardrails(state) == "escalate"


# ============================================================================
# TEST: HAPPY PATH
# ============================================================================


class TestHappyPath:
    """Email sent successfully on first try."""

    @pytest.mark.asyncio
    async def test_happy_path_email_sent(
        self,
        sample_customer,
        valid_generated_email,
        critic_evaluation_send,
        guardrail_result_pass,
    ):
        """
        Happy path: Generator → Critic (SEND) → Final Guardrails (PASS) → Send Email.

        Expected:
        - workflow_status = "SENT"
        - message_id present
        - No refinements
        """
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
                "generation_time_seconds": 2.5,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                mock_critic.return_value = {
                    "critic_recommendation": "SEND",
                    "critic_evaluation": critic_evaluation_send,
                    "critic_issues": [],
                }

                with patch(
                    "app.graph.workflow.final_guardrails_node", new_callable=AsyncMock
                ) as mock_guardrails:
                    mock_guardrails.return_value = {
                        "final_guardrail_passed": True,
                        "final_guardrail_result": guardrail_result_pass,
                        "workflow_status": "READY_TO_SEND",
                    }
                    with patch(
                        "app.graph.workflow.send_email_node", new_callable=AsyncMock
                    ) as mock_send:
                        mock_send.return_value = {
                            "workflow_status": "SENT",
                            "message_id": "msg_abc123def456",
                            "sent_at": "2026-10-07T10:30:00Z",
                        }

                        result = await run_email_pipeline(
                            customer_id=sample_customer.customer_id,
                            customer_data=sample_customer,
                        )
                        # Verify routing
                        assert result["workflow_status"] == "SENT"
                        assert result["message_id"] == "msg_abc123def456"
                        assert result["refinement_count"] == 0
                        assert result["sent_at"] == "2026-10-07T10:30:00Z"

                        # Verify nodes called in correct order
                        mock_gen.assert_called_once()
                        mock_critic.assert_called_once()
                        mock_guardrails.assert_called_once()
                        mock_send.assert_called_once()


# ============================================================================
# TEST: REFINE LOOP
# ============================================================================
class TestRefineLoop:
    """Critic recommends refinement → loop back to critic."""

    @pytest.mark.asyncio
    async def test_single_refine_iteration(
        self,
        sample_customer,
        valid_generated_email,
        critic_evaluation_refine,
        critic_evaluation_send,
        guardrail_result_pass,
    ):
        """
        Single refinement: Gen → Critic (REFINE) → Refiner → Critic (SEND) → Send.

        Expected:
        - Critic called twice (first REFINE, then SEND)
        - Refiner called once
        - refinement_count = 1
        """
        refined_email = EmailContent(
            subject="Welcome to Smoothie, Sarah!",
            body="Hi Sarah! We're thrilled to have you join us on your Premium smoothie plan. Let's get started!",
            personalized_elements=["first_name_used", "plan_name_mentioned"],
        )

        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
                "generation_time_seconds": 2.5,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                # First call: REFINE, Second call: SEND
                mock_critic.side_effect = [
                    {
                        "critic_recommendation": "REFINE",
                        "critic_evaluation": critic_evaluation_refine,
                        "critic_issues": ["Tone too formal", "CTA unclear"],
                    },
                    {
                        "critic_recommendation": "SEND",
                        "critic_evaluation": critic_evaluation_send,
                        "critic_issues": [],
                    },
                ]

                with patch(
                    "app.graph.workflow.refiner_node", new_callable=AsyncMock
                ) as mock_refiner:
                    mock_refiner.return_value = {
                        "refined_email": refined_email,
                        "refinement_count": 1,
                        "refiner_last_feedback": ["Tone too formal", "CTA unclear"],
                        "workflow_status": "email_refined",
                    }
                    with patch(
                        "app.graph.workflow.final_guardrails_node",
                        new_callable=AsyncMock,
                    ) as mock_guardrails:
                        mock_guardrails.return_value = {
                            "final_guardrail_passed": True,
                            "final_guardrail_result": guardrail_result_pass,
                        }

                        with patch(
                            "app.graph.workflow.send_email_node", new_callable=AsyncMock
                        ) as mock_send:
                            mock_send.return_value = {
                                "workflow_status": "SENT",
                                "message_id": "msg_refine_123",
                            }

                            result = await run_email_pipeline(
                                customer_id=sample_customer.customer_id,
                                customer_data=sample_customer,
                            )

                            # Verify single refinement loop
                            assert result["refinement_count"] == 1
                            assert result["workflow_status"] == "SENT"
                            assert mock_critic.call_count == 2  # Called twice
                            mock_refiner.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_refine_iterations(
        self,
        sample_customer,
        valid_generated_email,
        critic_evaluation_refine,
        critic_evaluation_send,
        guardrail_result_pass,
    ):
        """
        Two refinement iterations: Gen → Critic → Refiner 1 → Critic → Refiner 2 → Critic (SEND).

        Expected:
        - Critic called 3 times (initial + after each refiner)
        - Refiner called twice
        - refinement_count = 2
        """
        refined_email_v1 = EmailContent(
            subject="Welcome, Sarah!",
            body="Hi Sarah! Thanks for joining Weekly.",
            personalized_elements=["first_name_used"],
        )
        refined_email_v2 = EmailContent(
            subject="Welcome, Sarah!",
            body="Hi Sarah! We're excited you joined Weekly. Explore your options when ready!",
            personalized_elements=["first_name_used", "plan_name_mentioned"],
        )
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }
            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                # Call 1: REFINE, Call 2: REFINE, Call 3: SEND
                mock_critic.side_effect = [
                    {
                        "critic_recommendation": "REFINE",
                        "critic_evaluation": critic_evaluation_refine,
                        "critic_issues": ["Issue 1"],
                    },
                    {
                        "critic_recommendation": "REFINE",
                        "critic_evaluation": critic_evaluation_refine,
                        "critic_issues": ["Issue 2"],
                    },
                    {
                        "critic_recommendation": "SEND",
                        "critic_evaluation": critic_evaluation_send,
                        "critic_issues": [],
                    },
                ]
                with patch(
                    "app.graph.workflow.refiner_node", new_callable=AsyncMock
                ) as mock_refiner:
                    mock_refiner.side_effect = [
                        {
                            "refined_email": refined_email_v1,
                            "refinement_count": 1,
                            "workflow_status": "email_refined",
                        },
                        {
                            "refined_email": refined_email_v2,
                            "refinement_count": 2,
                            "workflow_status": "email_refined",
                        },
                    ]
                    with patch(
                        "app.graph.workflow.final_guardrails_node",
                        new_callable=AsyncMock,
                    ) as mock_guardrails:
                        mock_guardrails.return_value = {
                            "final_guardrail_passed": True,
                        }

                        with patch(
                            "app.graph.workflow.send_email_node", new_callable=AsyncMock
                        ) as mock_send:
                            mock_send.return_value = {
                                "workflow_status": "SENT",
                                "message_id": "msg_multi_123",
                            }

                            result = await run_email_pipeline(
                                customer_id=sample_customer.customer_id,
                                customer_data=sample_customer,
                            )

                            assert result["refinement_count"] == 2
                            assert result["workflow_status"] == "SENT"
                            assert mock_critic.call_count == 3
                            assert mock_refiner.call_count == 2


# ============================================================================
# TEST: MAX REFINEMENTS GUARD
# ============================================================================
class TestMaxRefinements:
    """Guard against infinite loops: max 3 refinements."""

    @pytest.mark.asyncio
    async def test_max_refinements_escalates(
        self, sample_customer, valid_generated_email, critic_evaluation_refine
    ):
        """
        After 3 refinements, should escalate instead of looping again.

        Flow: Gen → Critic → Refiner 1 → Critic → Refiner 2 → Critic → Refiner 3
              → Critic (still REFINE) → Escalate (due to max guard)

        Expected:
        - refinement_count = 3
        - workflow_status = "MANUAL_REVIEW" (escalated)
        - No 4th call to refiner
        """
        refined_email_v3 = EmailContent(
            subject="Welcome!",
            body="Hi Sarah, welcome to Premium smoothies.",
            personalized_elements=["first_name_used"],
        )
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                # Always recommend REFINE (even after 3 iterations)
                mock_critic.return_value = {
                    "critic_recommendation": "REFINE",
                    "critic_evaluation": critic_evaluation_refine,
                    "critic_issues": ["Still has issues"],
                }

                with patch(
                    "app.graph.workflow.refiner_node", new_callable=AsyncMock
                ) as mock_refiner:
                    mock_refiner.side_effect = [
                        {
                            "refined_email": EmailContent(
                                subject="v1",
                                body="version 1",
                                personalized_elements=[],
                            ),
                            "refinement_count": 1,
                            "workflow_status": "email_refined",
                        },
                        {
                            "refined_email": EmailContent(
                                subject="v2",
                                body="version 2",
                                personalized_elements=[],
                            ),
                            "refinement_count": 2,
                            "workflow_status": "email_refined",
                        },
                        {
                            "refined_email": refined_email_v3,
                            "refinement_count": 3,
                            "workflow_status": "email_refined",
                        },
                    ]
                    with patch(
                        "app.graph.workflow.escalate_node", new_callable=AsyncMock
                    ) as mock_escalate:
                        mock_escalate.return_value = {
                            "workflow_status": "MANUAL_REVIEW",
                        }

                        result = await run_email_pipeline(
                            customer_id=sample_customer.customer_id,
                            customer_data=sample_customer,
                        )

                        # Verify max refinements enforced
                        assert result["refinement_count"] == 3
                        assert result["workflow_status"] == "MANUAL_REVIEW"
                        # Only 3 calls to refiner (not 4)
                        assert mock_refiner.call_count == 3
                        mock_escalate.assert_called_once()


# ============================================================================
# TEST: ESCALATION SCENARIOS
# ============================================================================
class TestEscalation:
    """Various paths leading to manual review or failure."""

    @pytest.mark.asyncio
    async def test_critical_severity_escalates(
        self, sample_customer, valid_generated_email, critic_evaluation_critical
    ):
        """
        CRITICAL issues immediately escalate (no Refiner call, no Jev cost).

        Flow: Gen → Critic (CRITICAL) → Escalate

        Expected:
        - workflow_status = "MANUAL_REVIEW"
        - Refiner never called
        - No final guardrails check
        """
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                mock_critic.return_value = {
                    "critic_recommendation": "MANUAL_REVIEW",
                    "critic_evaluation": critic_evaluation_critical,
                    "critic_issues": ["PII exposed"],
                }

                with patch(
                    "app.graph.workflow.refiner_node", new_callable=AsyncMock
                ) as mock_refiner:
                    with patch(
                        "app.graph.workflow.escalate_node", new_callable=AsyncMock
                    ) as mock_escalate:
                        mock_escalate.return_value = {
                            "workflow_status": "MANUAL_REVIEW",
                        }

                        result = await run_email_pipeline(
                            customer_id=sample_customer.customer_id,
                            customer_data=sample_customer,
                        )

                        assert result["workflow_status"] == "MANUAL_REVIEW"
                        mock_refiner.assert_not_called()
                        mock_escalate.assert_called_once()

    @pytest.mark.asyncio
    async def test_final_guardrail_failure_escalates(
        self,
        sample_customer,
        valid_generated_email,
        critic_evaluation_send,
        guardrail_result_fail,
    ):
        """
        Final guardrails fail → escalate (defense-in-depth).

        Flow: Gen → Critic (SEND) → Final Guardrails (FAIL) → Escalate

        Expected:
        - workflow_status = "MANUAL_REVIEW"
        - Send email never called
        """
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                mock_critic.return_value = {
                    "critic_recommendation": "SEND",
                    "critic_evaluation": critic_evaluation_send,
                }
                with patch(
                    "app.graph.workflow.final_guardrails_node", new_callable=AsyncMock
                ) as mock_guardrails:
                    mock_guardrails.return_value = {
                        "final_guardrail_passed": False,
                        "final_guardrail_result": guardrail_result_fail,
                        "workflow_status": "FINAL_GUARDRAIL_FAILED",
                    }
                    with patch(
                        "app.graph.workflow.send_email_node", new_callable=AsyncMock
                    ) as mock_send:
                        with patch(
                            "app.graph.workflow.escalate_node", new_callable=AsyncMock
                        ) as mock_escalate:
                            mock_escalate.return_value = {
                                "workflow_status": "MANUAL_REVIEW",
                            }

                            result = await run_email_pipeline(
                                customer_id=sample_customer.customer_id,
                                customer_data=sample_customer,
                            )

                            assert result["workflow_status"] == "MANUAL_REVIEW"
                            mock_send.assert_not_called()


# ============================================================================
# TEST: ERROR HANDLING
# ============================================================================
class TestErrorHandling:
    """Network errors, parsing failures, graceful degradation."""

    @pytest.mark.asyncio
    async def test_refiner_error_escalates(
        self, sample_customer, valid_generated_email
    ):
        """
        Refiner encounters error → escalate instead of looping.

        Flow: Gen → Critic (REFINE) → Refiner (ERROR) → Escalate

        Expected:
        - workflow_status = "MANUAL_REVIEW" (escalated)
        - refinement_count unchanged
        """
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                mock_critic.return_value = {
                    "critic_recommendation": "REFINE",
                    "critic_issues": ["Some issue"],
                }
                with patch(
                    "app.graph.workflow.refiner_node", new_callable=AsyncMock
                ) as mock_refiner:
                    mock_refiner.return_value = {
                        "refined_email": None,
                        "refinement_count": 0,
                        "workflow_status": "error_refiner_parsing",
                        "error_message": "Invalid JSON from LLM",
                    }
                    with patch(
                        "app.graph.workflow.escalate_node", new_callable=AsyncMock
                    ) as mock_escalate:
                        mock_escalate.return_value = {
                            "workflow_status": "MANUAL_REVIEW",
                        }

                        result = await run_email_pipeline(
                            customer_id=sample_customer.customer_id,
                            customer_data=sample_customer,
                        )

                        assert result["workflow_status"] == "MANUAL_REVIEW"
                        assert result["refinement_count"] == 0

    @pytest.mark.asyncio
    async def test_send_email_error_fails_gracefully(
        self,
        sample_customer,
        valid_generated_email,
        critic_evaluation_send,
        guardrail_result_pass,
    ):
        """
        Send email error → FAILED status (captured in result, not raised).

        Flow: Gen → Critic (SEND) → Final Guardrails (PASS) → Send Email (ERROR)

        Expected:
        - workflow_status = "FAILED"
        - error_message present
        - No exception raised (caught internally)
        """
        with patch(
            "app.graph.workflow.generator_node", new_callable=AsyncMock
        ) as mock_gen:
            mock_gen.return_value = {
                "generated_email": valid_generated_email,
            }

            with patch(
                "app.graph.workflow.critic_node", new_callable=AsyncMock
            ) as mock_critic:
                mock_critic.return_value = {
                    "critic_recommendation": "SEND",
                    "critic_evaluation": critic_evaluation_send,
                }
                with patch(
                    "app.graph.workflow.final_guardrails_node", new_callable=AsyncMock
                ) as mock_guardrails:
                    mock_guardrails.return_value = {
                        "final_guardrail_passed": True,
                    }

                    with patch(
                        "app.graph.workflow.send_email_node", new_callable=AsyncMock
                    ) as mock_send:
                        mock_send.return_value = {
                            "workflow_status": "FAILED",
                            "error_message": "Resend API timeout",
                        }

                        result = await run_email_pipeline(
                            customer_id=sample_customer.customer_id,
                            customer_data=sample_customer,
                        )

                        assert result["workflow_status"] == "FAILED"
                        assert result["error_message"] == "Resend API timeout"
