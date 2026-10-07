"""
Jev decision model client for email quality classification.

Replaces expensive GPT-4 calls with ultra-fast, cost-effective classification.
Uses LangSmith Gateway (typesafe/ prefix) to route through workspace secrets.

Key metrics:
- Cost: $0.042/M input tokens (vs GPT-4's $30/M = 700x cheaper)
- Latency: 100-500ms (vs GPT-4's 2-5s = 10x faster)
- Output: Typed primitives (guaranteed, no parsing errors)
"""

import os
import logging
from typing import TypedDict, Literal

try:
    from typesafe_sdk import Choice, Score, TypeSafeClient, Noul

    TYPESAFE_SDK_AVAILABLE = True
except ImportError:
    TYPESAFE_SDK_AVAILABLE = False

    # Dummy classes for testing/development
    class Choice:
        pass

    class Score:
        pass

    class Noul:
        pass

    class TypeSafeClient:
        pass


logger = logging.getLogger(__name__)


class JevDecision(TypedDict):
    """Typed response from Jev classification."""

    recommendation: Literal["SEND", "REFINE", "MANUAL_REVIEW"]
    confidence: float  # 0.0 to 1.0
    quality_score: float | None  # 0-4 scale
    has_pii: float  # Probability 0-1


async def classify_email_with_jev(
    subject: str,
    body: str,
    deterministic_severity: Literal["CRITICAL", "MODERATE", "MINOR", "PASS"],
    correlation_id: str,
) -> JevDecision:
    """
    Use Jev to classify email quality and recommend routing.

    This replaces the expensive GPT-4 evaluation in critic_node().
    Runs deterministic checks first, then uses Jev only for MODERATE issues.

    Args:
        subject: Email subject line
        body: Email body text
        deterministic_severity: Severity from regex checks (CRITICAL/MODERATE/MINOR/PASS)
        correlation_id: Workflow correlation ID for logging

    Returns:
        JevDecision with routing recommendation and confidence scores

    Raises:
        ValueError: If API key not configured
        Exception: If Jev API call fails (logged, not raised)

    Design:
    - Jev is called ONLY when deterministic checks find MODERATE issues
    - For CRITICAL/PASS/MINOR, Jev is skipped (no LLM cost)
    - Confidence scores help with observability and alerting
    """
    try:
        # Check if SDK is available (in production, should be installed)
        if not TYPESAFE_SDK_AVAILABLE:
            logger.warning(
                "typesafe-sdk not installed, using mock response",
                extra={"correlation_id": correlation_id},
            )
            # Development/test fallback
            return JevDecision(
                recommendation="SEND",
                confidence=0.5,
                quality_score=3.0,
                has_pii=0.0,
            )

        # Get API key from environment
        langsmith_api_key = os.environ.get("LANGSMITH_API_KEY")
        if not langsmith_api_key:
            raise ValueError(
                "LANGSMITH_API_KEY not set in environment. "
                "Required for Jev classification via LangSmith Gateway."
            )

        # Initialize Jev client via LangSmith Gateway
        # Using "typesafe/" prefix routes through workspace's TypeSafe provider secret
        client = TypeSafeClient(
            api_key=langsmith_api_key,
            base_url="https://gateway.smith.langchain.com",
        )

        # Build state context for Jev (structured, not prose)
        email_state = f"""
Subject: {subject}

Body (first 500 chars):
{body[:500]}

Deterministic Severity: {deterministic_severity}
"""

        # Define Jev questions (3 types: Choice, Score, Noul)
        questions = {
            # Question 1: Routing decision (3-class classification)
            "recommendation": Choice(
                instructions=(
                    "Based on email quality and deterministic checks, should we "
                    "SEND this email, ask to REFINE it, or escalate to MANUAL_REVIEW?"
                ),
                options=[
                    {
                        "name": "SEND",
                        "description": "Email passes quality checks and is ready to send",
                    },
                    {
                        "name": "REFINE",
                        "description": "Email has quality issues that need refinement",
                    },
                    {
                        "name": "MANUAL_REVIEW",
                        "description": "Email has critical compliance/quality issues",
                    },
                ],
            ),
            # Question 2: Quality scoring (5-level Likert)
            "quality_score": Score(
                instructions="Rate the overall quality of this email on a 0-4 scale",
                levels=[
                    {"level": 0, "description": "Poor - multiple critical issues"},
                    {"level": 1, "description": "Below average - significant issues"},
                    {"level": 2, "description": "Average - acceptable quality"},
                    {"level": 3, "description": "Good - high quality"},
                    {"level": 4, "description": "Excellent - exceptional quality"},
                ],
            ),
            # Question 3: PII probability (continuous boolean)
            "pii_exposure": Noul(
                instructions=(
                    "What is the probability that this email exposes "
                    "personally identifiable information?"
                ),
            ),
        }

        # Call Jev with "typesafe/" prefix (routes through LangSmith workspace secret)
        response = client.system_one(
            state=email_state,
            model="typesafe/jev-1.13.0",  # ← "typesafe/" prefix triggers workspace routing
            questions=questions,
        )

        # Extract typed answers from response
        recommendation = response.answers["recommendation"].choice
        recommendation_confidence = response.answers["recommendation"].confidence
        quality_score = response.answers["quality_score"].score
        pii_probability = response.answers["pii_exposure"].probability

        # Log classification result
        logger.info(
            f"Jev classification complete: {recommendation}",
            extra={
                "correlation_id": correlation_id,
                "node": "critic",
                "jev_recommendation": recommendation,
                "jev_confidence": recommendation_confidence,
                "jev_quality_score": quality_score,
                "jev_pii_probability": pii_probability,
            },
        )

        return JevDecision(
            recommendation=recommendation,
            confidence=recommendation_confidence,
            quality_score=quality_score,
            has_pii=pii_probability,
        )

    except ValueError as e:
        # Configuration error (missing API key)
        logger.error(
            f"Jev configuration error: {str(e)}",
            extra={"correlation_id": correlation_id, "node": "critic"},
        )
        raise

    except Exception as e:
        # Unexpected error (API timeout, network, etc.)
        logger.error(
            f"Jev classification failed (will escalate to manual review): {type(e).__name__}",
            extra={
                "correlation_id": correlation_id,
                "node": "critic",
                "error_detail": str(e),
            },
        )
        # Fallback: escalate to manual review if Jev unavailable
        # This is safer than failing silently
        return JevDecision(
            recommendation="MANUAL_REVIEW",
            confidence=0.0,
            quality_score=None,
            has_pii=0.5,
        )
