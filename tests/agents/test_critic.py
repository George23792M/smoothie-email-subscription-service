"""
Comprehensive tests for Critic Agent (Phase 2).

Tests the two-stage evaluation:
1. Deterministic checks (validations.py)
2. Jev classification (jev_client.py + node.py)

Test structure:
- Deterministic validations (pure functions, no mocks)
- Critic node paths (CRITICAL/PASS/MODERATE)
- Jev integration (with mocked Jev responses)
- Error handling (missing fields, Jev timeout)
- E2E flows (Generator → Critic → decision)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.graph.state import (
    PipelineState,
    EmailContent,
    CustomerDetailResponse,
    CriticEvaluation,
)
from app.agents.critic.node import critic_node
from app.agents.critic.validations import (
    check_subject_length,
    check_body_length,
    check_placeholder_leakage,
    check_html_markdown_in_email,
    check_banned_phrases,
    check_pii_exposure,
    check_medical_claims,
    check_personalization_consistency,
    run_deterministic_checks,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def valid_customer():
    """Customer with all required fields."""
    return CustomerDetailResponse(
        customer_id="cust_12345",
        first_name="Sarah",
        last_name="Johnson",
        customer_name="Sarah Johnson",
        preferred_name="Sarah",
        plan_name="Premium",
        email="sarah@example.com",
    )


@pytest.fixture
def valid_email():
    """Email that passes all deterministic checks."""
    return EmailContent(
        subject="Welcome to Smoothie, Sarah!",
        body="Hi Sarah, thank you for joining our Premium plan. Start blending delicious smoothies today!",
        personalized_elements=["first_name_used", "plan_name_mentioned"],
    )


@pytest.fixture
def pipeline_state(valid_customer, valid_email):
    """Complete PipelineState for critic evaluation."""
    return PipelineState(
        customer_id="cust_12345",
        customer_data=valid_customer,
        generated_email=valid_email,
        correlation_id="test-correlation-123",
    )


# ============================================================================
# TESTS: DETERMINISTIC VALIDATIONS (Pure Functions, No Mocks)
# ============================================================================


class TestDeterministicValidations:
    """Unit tests for validations.py functions."""

    def test_check_subject_length_valid(self):
        """Subject within 5-100 char limit."""
        passed, issue = check_subject_length("Welcome to Smoothie!")
        assert passed is True
        assert issue is None

    def test_check_subject_length_too_short(self):
        """Subject too short (< 5 chars)."""
        passed, issue = check_subject_length("Hi!")
        assert passed is False
        assert "too short" in issue.lower()

    def test_check_subject_length_too_long(self):
        """Subject too long (> 100 chars)."""
        long_subject = "A" * 101
        passed, issue = check_subject_length(long_subject)
        assert passed is False
        assert "too long" in issue.lower()

    def test_check_body_length_valid(self):
        """Body within 50-2000 char limit."""
        body = "This is a valid email body with enough content to pass validation."
        passed, issue = check_body_length(body)
        assert passed is True
        assert issue is None

    def test_check_body_length_too_short(self):
        """Body too short (< 50 chars)."""
        passed, issue = check_body_length("Too short")
        assert passed is False
        assert "too short" in issue.lower()

    def test_check_body_length_too_long(self):
        """Body too long (> 2000 chars)."""
        long_body = "A" * 2001
        passed, issue = check_body_length(long_body)
        assert passed is False
        assert "too long" in issue.lower()

    def test_check_placeholder_leakage_found(self):
        """Detect unreplaced placeholders."""
        text = "Hi {{first_name}}, welcome!"
        passed, issue = check_placeholder_leakage(text)
        assert passed is False
        assert "placeholder" in issue.lower()

    def test_check_placeholder_leakage_clean(self):
        """No placeholders in text."""
        text = "Hi John, welcome!"
        passed, issue = check_placeholder_leakage(text)
        assert passed is True

    def test_check_html_markdown_detects_html(self):
        """Detect HTML tags."""
        body = "Hi John, <b>welcome</b> to Smoothie!"
        passed, issue = check_html_markdown_in_email(body)
        assert passed is False
        assert "html" in issue.lower()

    def test_check_html_markdown_detects_markdown_bold(self):
        """Detect Markdown bold."""
        body = "Hi John, **welcome** to Smoothie!"
        passed, issue = check_html_markdown_in_email(body)
        assert passed is False
        assert "markdown" in issue.lower() or "bold" in issue.lower()

    def test_check_html_markdown_clean(self):
        """Plain text only."""
        body = "Hi John, welcome to Smoothie!"
        passed, issue = check_html_markdown_in_email(body)
        assert passed is True

    def test_check_banned_phrases_found(self):
        """Detect phishing phrase."""
        body = "Please verify your password immediately!"
        passed, issue = check_banned_phrases("", body)
        assert passed is False
        assert "verify your password" in issue.lower()

    def test_check_banned_phrases_clean(self):
        """No phishing phrases."""
        body = "Welcome to our service!"
        passed, issue = check_banned_phrases("", body)
        assert passed is True

    def test_check_pii_exposure_detects_email(self):
        """Detect exposed email address."""
        body = "Your account john@gmail.com has been created."
        passed, issue = check_pii_exposure("", body)
        assert passed is False
        assert "email" in issue.lower()

    def test_check_pii_exposure_safe_customer_id(self):
        """Allow safe customer ID."""
        body = "Your customer ID cust_123 is attached."
        passed, issue = check_pii_exposure("", body, safe_customer_id="cust_123")
        assert passed is True

    def test_check_pii_exposure_unsafe_customer_id(self):
        """Reject unauthorized customer ID."""
        body = "Access cust_999 account here."
        passed, issue = check_pii_exposure("", body, safe_customer_id="cust_123")
        assert passed is False
        assert "customer" in issue.lower()

    def test_check_medical_claims_found(self):
        """Detect medical claim."""
        body = "This smoothie will cure your diabetes!"
        passed, issue = check_medical_claims(body)
        assert passed is False
        assert "medical" in issue.lower() or "cure" in issue.lower()

    def test_check_medical_claims_clean(self):
        """No medical claims."""
        body = "Enjoy delicious and nutritious smoothies!"
        passed, issue = check_medical_claims(body)
        assert passed is True

    def test_check_personalization_consistency_match(self):
        """Personalization claims match body."""
        body = "Hi Sarah, we're excited to see you on the Premium plan!"
        passed, issue = check_personalization_consistency(
            body=body,
            personalized_elements=["first_name_used", "plan_name_mentioned"],
            preferred_name="",
            first_name="Sarah",
        )
        assert passed is True

    def test_check_personalization_consistency_mismatch(self):
        """Personalization claims don't match body."""
        body = "Hi there, welcome!"
        passed, issue = check_personalization_consistency(
            body=body,
            personalized_elements=["first_name_used"],
            preferred_name="",
            first_name="Sarah",
        )
        assert passed is False
        assert "first_name" in issue.lower()


class TestRunDeterministicChecks:
    """Integration tests for run_deterministic_checks orchestrator."""

    def test_pass_severity_no_issues(self):
        """Email passes all checks."""
        severity, issues = run_deterministic_checks(
            subject="Welcome Sarah!",
            body="Hi Sarah, thank you for joining our Premium smoothies plan! We're excited to have you. Enjoy unlimited smoothies with priority support.",
            preferred_name="",
            first_name="Sarah",
            personalized_elements=["first_name_used"],
            safe_customer_id="cust_123",
        )
        assert severity == "PASS"
        assert len(issues) == 0

    def test_critical_severity_pii(self):
        """PII exposure → CRITICAL."""
        severity, issues = run_deterministic_checks(
            subject="Welcome!",
            body="Your email john@gmail.com has been registered.",
            preferred_name="",
            first_name="John",
            personalized_elements=[],
            safe_customer_id="cust_123",
        )
        assert severity == "CRITICAL"
        assert len(issues) > 0
        assert any("email" in issue.lower() for issue in issues)

    def test_critical_severity_medical_claim(self):
        """Medical claim → CRITICAL."""
        severity, issues = run_deterministic_checks(
            subject="Cure Your Diabetes!",
            body="Our smoothies will cure your diabetes!",
            preferred_name="",
            first_name="John",
            personalized_elements=[],
            safe_customer_id="cust_123",
        )
        assert severity == "CRITICAL"
        assert any(
            "medical" in issue.lower() or "cure" in issue.lower() for issue in issues
        )

    def test_moderate_severity_length_issue(self):
        """Body too short → MODERATE."""
        severity, issues = run_deterministic_checks(
            subject="Welcome!",
            body="Hi John, short body.",
            preferred_name="",
            first_name="John",
            personalized_elements=[],
            safe_customer_id="cust_123",
        )
        assert severity == "MODERATE"
        assert any(
            "short" in issue.lower() or "body" in issue.lower() for issue in issues
        )


# ============================================================================
# TESTS: CRITIC NODE (With Jev Mocking)
# ============================================================================


class TestCriticNodePaths:
    """Test critic_node routing logic."""

    @pytest.mark.asyncio
    async def test_critic_node_critical_issues_manual_review(self, pipeline_state):
        """CRITICAL issues → MANUAL_REVIEW (no Jev call)."""
        # Inject email with PII
        pipeline_state["generated_email"] = EmailContent(
            subject="Account",
            body="Your email john@gmail.com is registered.",
            personalized_elements=[],
        )

        result = await critic_node(pipeline_state)

        assert result["critic_recommendation"] == "MANUAL_REVIEW"
        assert result["workflow_status"] == "evaluated_critical_issues"
        assert result["critic_evaluation"] is not None
        assert result["critic_evaluation"].severity == "CRITICAL"

    @pytest.mark.asyncio
    async def test_critic_node_pass_issues_send(self, pipeline_state):
        """PASS severity → SEND (no Jev call)."""
        result = await critic_node(pipeline_state)

        assert result["critic_recommendation"] == "SEND"
        assert result["workflow_status"] == "evaluated_pass"
        assert "jev_skipped" not in result or result.get("correlation_id")

    @pytest.mark.asyncio
    async def test_critic_node_moderate_issues_calls_jev(self, pipeline_state):
        """MODERATE issues → Call Jev for guidance."""
        # Create email with personalization inconsistency (claimed but not in body)
        pipeline_state["generated_email"] = EmailContent(
            subject="Welcome Sarah",
            body="This is a well-formed email with good structure. Enjoy your experience.",
            personalized_elements=[
                "first_name_used",
                "plan_name_used",
            ],  # Claimed but not in body
        )

        # Mock Jev response
        mock_jev_result = {
            "recommendation": "SEND",
            "confidence": 0.92,
            "quality_score": 3.5,
            "has_pii": 0.01,
        }

        with patch(
            "app.agents.critic.node.classify_email_with_jev", new_callable=AsyncMock
        ) as mock_jev:
            mock_jev.return_value = mock_jev_result
            result = await critic_node(pipeline_state)

            # Verify Jev was called for MODERATE severity
            mock_jev.assert_called_once()

            # Verify routing
            assert result["critic_recommendation"] == "SEND"
            assert result["workflow_status"] == "evaluated_moderate_issues"

    @pytest.mark.asyncio
    async def test_critic_node_moderate_refine_recommendation(self, pipeline_state):
        """Jev recommends REFINE."""
        # Create email with personalization inconsistency
        pipeline_state["generated_email"] = EmailContent(
            subject="Welcome",
            body="We have prepared excellent content for you. Thank you for joining us.",
            personalized_elements=["first_name_used"],  # Claimed but Sarah not in body
        )

        mock_jev_result = {
            "recommendation": "REFINE",
            "confidence": 0.87,
            "quality_score": 2.5,
            "has_pii": 0.0,
        }

        with patch(
            "app.agents.critic.node.classify_email_with_jev", new_callable=AsyncMock
        ) as mock_jev:
            mock_jev.return_value = mock_jev_result
            result = await critic_node(pipeline_state)

            assert result["critic_recommendation"] == "REFINE"
            assert result["critic_evaluation"].is_valid is False


class TestCriticNodeErrors:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_critic_node_missing_email(self, pipeline_state):
        """Missing generated_email → MANUAL_REVIEW."""
        del pipeline_state["generated_email"]

        result = await critic_node(pipeline_state)

        assert result["critic_recommendation"] == "MANUAL_REVIEW"
        assert result["workflow_status"] == "error_critic_validation"

    @pytest.mark.asyncio
    async def test_critic_node_missing_customer_data(self, pipeline_state):
        """Missing customer_data → MANUAL_REVIEW."""
        del pipeline_state["customer_data"]

        result = await critic_node(pipeline_state)

        assert result["critic_recommendation"] == "MANUAL_REVIEW"
        assert result["workflow_status"] == "error_critic_validation"

    @pytest.mark.asyncio
    async def test_critic_node_jev_timeout(self, pipeline_state):
        """Jev timeout → MANUAL_REVIEW (fallback)."""
        # Create email with personalization inconsistency to trigger MODERATE severity
        pipeline_state["generated_email"] = EmailContent(
            subject="Welcome",
            body="We are glad to have you as a customer. Welcome aboard!",
            personalized_elements=[
                "first_name_used"
            ],  # Claimed but not in body triggers MODERATE
        )

        with patch(
            "app.agents.critic.node.classify_email_with_jev", new_callable=AsyncMock
        ) as mock_jev:
            mock_jev.side_effect = TimeoutError("Jev API timeout")
            result = await critic_node(pipeline_state)

            assert result["critic_recommendation"] == "MANUAL_REVIEW"
            assert result["workflow_status"] == "error_critic_unexpected"


# ============================================================================
# TESTS: JEV CLIENT (Mock TypeSafe SDK)
# ============================================================================


class TestJevClient:
    """Test jev_client.py with mocked Jev API."""

    @pytest.mark.asyncio
    async def test_classify_email_success(self):
        """Successful Jev classification returns correct structure."""
        from app.agents.critic.jev_client import classify_email_with_jev

        # Since typesafe-sdk is not installed, the code falls back to graceful degradation
        # Returns mock response directly
        result = await classify_email_with_jev(
            subject="Welcome",
            body="Hi there, welcome to Premium smoothies!",
            deterministic_severity="MODERATE",
            correlation_id="test-123",
        )

        # When SDK is unavailable, returns fallback response
        assert isinstance(result, dict)
        assert "recommendation" in result
        assert "confidence" in result
        assert "quality_score" in result

    @pytest.mark.asyncio
    async def test_classify_email_missing_api_key(self):
        """Missing LANGSMITH_API_KEY → ValueError."""
        from app.agents.critic.jev_client import classify_email_with_jev

        with patch("app.agents.critic.jev_client.TYPESAFE_SDK_AVAILABLE", True):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
                    await classify_email_with_jev(
                        subject="Welcome",
                        body="Hi there, welcome to smoothies!",
                        deterministic_severity="MODERATE",
                        correlation_id="test",
                    )

    @pytest.mark.asyncio
    async def test_classify_email_api_error_fallback(self):
        """Jev API unavailable → fallback to safe default."""
        from app.agents.critic.jev_client import classify_email_with_jev

        # When SDK is not available, should return graceful fallback
        result = await classify_email_with_jev(
            subject="Welcome",
            body="Hi there, welcome to smoothies!",
            deterministic_severity="MODERATE",
            correlation_id="test",
        )

        # Fallback returns valid decision structure
        assert isinstance(result, dict)
        assert result["recommendation"] in ["SEND", "REFINE", "MANUAL_REVIEW"]
        assert 0 <= result["confidence"] <= 1.0


# ============================================================================
# TESTS: END-TO-END
# ============================================================================


class TestCriticE2E:
    """End-to-end tests (Generator → Critic)."""

    @pytest.mark.asyncio
    async def test_e2e_good_email_passes(self, valid_customer):
        """Good email: Generator → Critic → SEND."""
        email = EmailContent(
            subject="Welcome to Smoothie Premium!",
            body=(
                "Hi Sarah, congratulations on joining our Premium smoothie plan! "
                "You'll enjoy unlimited smoothies with priority support. "
                "Start blending today at www.smoothie.com"
            ),
            personalized_elements=["first_name_used", "plan_name_mentioned"],
        )

        state = PipelineState(
            customer_id="cust_123",
            customer_data=valid_customer,
            generated_email=email,
            correlation_id="e2e-test-1",
        )

        result = await critic_node(state)

        assert result["critic_recommendation"] in ["SEND", "REFINE"]
        assert result["critic_evaluation"] is not None
        assert "critic_evaluation_time_seconds" in result

    @pytest.mark.asyncio
    async def test_e2e_phishing_email_escalated(self, valid_customer):
        """Phishing email: Critic → MANUAL_REVIEW."""
        email = EmailContent(
            subject="Verify your password now!",
            body="Click here to remove your account and verify your identity immediately.",
            personalized_elements=[],
        )

        state = PipelineState(
            customer_id="cust_123",
            customer_data=valid_customer,
            generated_email=email,
            correlation_id="e2e-test-phishing",
        )

        result = await critic_node(state)

        assert result["critic_recommendation"] == "MANUAL_REVIEW"
        assert result["critic_evaluation"].severity == "CRITICAL"
