"""
LangGraph node for critic agent (hybrid: deterministic + Jev evaluation).

Two-stage evaluation:
1. Deterministic checks (fast, rule-based): PII, phishing, medical claims, structure
2. Jev classification (ultra-cheap, fast): tone, personalization, quality, routing decision

Routing outcomes:
- CRITICAL issues → MANUAL_REVIEW (escalate immediately)
- PASS/MINOR issues → SEND (quality sufficient, skip expensive Jev call)
- MODERATE issues → Call Jev for guidance (SEND or REFINE)

Cost impact: Jev saves ~700x on critic evaluations ($90/month → $0.042)
"""

import logging
import time
from typing import Any, Dict

from app.agents.critic.validations import run_deterministic_checks
from app.agents.critic.jev_client import classify_email_with_jev
from app.agents.utils import generate_correlation_id, log_node_entry, log_metric
from app.graph.state import PipelineState, CriticEvaluation, EmailContent

logger = logging.getLogger(__name__)

_node_name = "critic"


async def critic_node(state: PipelineState) -> Dict[str, Any]:
    """
    LangGraph node: Evaluate generated email (deterministic + Jev).

    Two-stage evaluation:
    Stage 1: Deterministic checks (length, PII, phishing, medical claims, HTML/Markdown)
    Stage 2: Jev classification (ONLY if Stage 1 finds MODERATE issues)

    Routing logic:
    - CRITICAL issues found → MANUAL_REVIEW (exit early, don't call Jev)
    - PASS/MINOR issues → SEND (no Jev call, save cost/latency)
    - MODERATE issues → Call Jev for routing decision (SEND or REFINE)

    Args:
        state: LangGraph PipelineState

    Returns:
        Dict for LangGraph to merge into state
    """
    # Setup
    correlation_id = state.get("correlation_id") or generate_correlation_id()
    start_time = time.time()

    log_node_entry(
        _node_name,
        correlation_id,
        ["generated_email", "customer_data"],
    )

    try:
        # ===== VALIDATE PREREQUISITES =====
        if not state.get("generated_email"):
            raise ValueError("Missing generated_email in state")

        generated_email: EmailContent = state["generated_email"]
        customer_data = state.get("customer_data")

        if not customer_data:
            raise ValueError("Missing customer_data in state")

        # Extract safe customer context (no email, no full ID patterns)
        preferred_name = customer_data.preferred_name or ""
        first_name = customer_data.first_name or ""
        plan_name = customer_data.plan_name or ""
        safe_customer_id = customer_data.customer_id

        # ===== STAGE 1: DETERMINISTIC CHECKS =====
        severity, deterministic_issues = run_deterministic_checks(
            subject=generated_email.subject,
            body=generated_email.body,
            preferred_name=preferred_name,
            first_name=first_name,
            personalized_elements=generated_email.personalized_elements,
            safe_customer_id=safe_customer_id,
        )

        logger.info(
            f"Deterministic checks complete: severity={severity}, issues={len(deterministic_issues)}",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
                "deterministic_severity": severity,
            },
        )

        # ===== EARLY EXIT: CRITICAL ISSUES =====
        if severity == "CRITICAL":
            evaluation_time = time.time() - start_time
            logger.warning(
                f"CRITICAL issues detected, escalating to manual review",
                extra={
                    "correlation_id": correlation_id,
                    "node": _node_name,
                    "issues": deterministic_issues,
                },
            )

            critic_evaluation = CriticEvaluation(
                is_valid=False,
                severity="CRITICAL",
                issues=deterministic_issues,
                recommendation="MANUAL_REVIEW",
                reasoning=(
                    f"Critical compliance issues detected: {deterministic_issues[0]}"
                    if deterministic_issues
                    else "Unknown critical issue"
                ),
            )

            log_metric("email_evaluated_critical_issues", correlation_id, 1)

            return {
                "critic_evaluation": critic_evaluation,
                "critic_issues": deterministic_issues,
                "critic_recommendation": "MANUAL_REVIEW",
                "critic_evaluation_time_seconds": evaluation_time,
                "correlation_id": correlation_id,
                "workflow_status": "evaluated_critical_issues",
            }

        # ===== FAST PATH: PASS/MINOR (Skip Jev, save cost) =====
        if severity in ["PASS", "MINOR"]:
            evaluation_time = time.time() - start_time

            critic_evaluation = CriticEvaluation(
                is_valid=True,
                severity=severity,
                issues=deterministic_issues,
                recommendation="SEND",
                reasoning=(
                    "Email passes all structural checks and is ready to send. "
                    "No quality issues detected."
                ),
            )

            logger.info(
                f"Email ready to send (severity={severity}), skipped Jev call",
                extra={
                    "correlation_id": correlation_id,
                    "node": _node_name,
                    "jev_skipped": True,
                },
            )

            log_metric("email_evaluated_pass", correlation_id, 1)

            return {
                "critic_evaluation": critic_evaluation,
                "critic_issues": deterministic_issues,
                "critic_recommendation": "SEND",
                "critic_evaluation_time_seconds": evaluation_time,
                "correlation_id": correlation_id,
                "workflow_status": "evaluated_pass",
            }

        # ===== MODERATE PATH: Call Jev for quality guidance =====
        logger.info(
            f"Moderate issues found, calling Jev for classification",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
                "deterministic_issues": len(deterministic_issues),
            },
        )

        jev_result = await classify_email_with_jev(
            subject=generated_email.subject,
            body=generated_email.body,
            deterministic_severity=severity,
            correlation_id=correlation_id,
        )

        # Merge deterministic + Jev feedback
        all_issues = deterministic_issues.copy()
        jev_recommendation = jev_result["recommendation"]
        jev_confidence = jev_result["confidence"]
        jev_quality = jev_result.get("quality_score")

        evaluation_time = time.time() - start_time

        critic_evaluation = CriticEvaluation(
            is_valid=(jev_recommendation == "SEND"),
            severity=severity,
            issues=all_issues,
            recommendation=jev_recommendation,
            reasoning=(
                f"Jev classification: {jev_recommendation} "
                f"(confidence: {jev_confidence:.2f}, quality: {jev_quality})"
            ),
        )

        logger.info(
            f"Jev evaluation complete: {jev_recommendation}",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
                "jev_recommendation": jev_recommendation,
                "jev_confidence": jev_confidence,
            },
        )

        log_metric("email_evaluated_moderate_issues", correlation_id, 1)

        return {
            "critic_evaluation": critic_evaluation,
            "critic_issues": all_issues,
            "critic_recommendation": jev_recommendation,
            "critic_evaluation_time_seconds": evaluation_time,
            "correlation_id": correlation_id,
            "workflow_status": "evaluated_moderate_issues",
        }

    except ValueError as e:
        # Validation errors (missing fields, etc.)
        evaluation_time = time.time() - start_time
        logger.warning(
            f"Validation error in {_node_name}: {str(e)}",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
            },
        )

        return {
            "critic_evaluation": None,
            "critic_issues": [],
            "critic_recommendation": "MANUAL_REVIEW",
            "critic_evaluation_time_seconds": evaluation_time,
            "correlation_id": correlation_id,
            "workflow_status": f"error_{_node_name}_validation",
        }

    except Exception as e:
        # Unexpected errors (Jev timeout, network, etc.)
        evaluation_time = time.time() - start_time
        logger.exception(
            f"Unexpected error in {_node_name}: {type(e).__name__}",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
            },
        )

        return {
            "critic_evaluation": None,
            "critic_issues": [],
            "critic_recommendation": "MANUAL_REVIEW",
            "critic_evaluation_time_seconds": evaluation_time,
            "correlation_id": correlation_id,
            "workflow_status": f"error_{_node_name}_unexpected",
        }
