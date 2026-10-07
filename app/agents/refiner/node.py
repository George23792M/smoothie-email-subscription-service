"""
LangGraph node for refiner agent (feedback-focused surgical improvement).

Flow:
1. Validate prerequisites (generated_email, critic_issues exist)
2. Check iteration limit (max 3 refinements)
3. Build context: original email + critic feedback + customer context
4. Call LLM with focus on fixing ONLY mentioned issues
5. Parse response into improved EmailContent
6. Increment refinement counter
7. Return state update for loop-back to Critic

Principle: Email + Feedback → Improved Email (surgical fixes only, no invention)
"""

import json
import logging
import time
from typing import Any, Dict

from app.agents.generator.prompts import get_system_prompt
from app.agents.generator.llm_client import call_llm_with_retry
from app.agents.utils import (
    extract_json_from_text,
    generate_correlation_id,
    log_metric,
    log_node_entry,
)
from app.core.config import settings
from app.graph.state import PipelineState, EmailContent
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_node_name = "refiner"
MAX_REFINEMENTS = 3


async def refiner_node(state: PipelineState) -> Dict[str, Any]:
    """
    LangGraph node: Improve email via surgical feedback application.

    NOT an autonomous agent. Takes Email + Feedback and applies targeted fixes.
    Does not invent content, benefits, or personalization beyond what was present.

    Flow:
    1. Validate prerequisites (generated_email, critic_issues exist)
    2. Guard: Check max refinements not exceeded
    3. Extract feedback, original email, and customer context
    4. Build context: System + Task + Feedback + Original Email + Customer Data
    5. Call LLM to fix ONLY mentioned issues
    6. Parse response into EmailContent
    7. Increment refinement_count
    8. Return state update with refined_email
    9. LangGraph routes back to Critic for re-evaluation

    Args:
        state: LangGraph PipelineState with:
            - generated_email (EmailContent): Current email version
            - critic_issues (List[str]): Specific feedback from Critic
            - customer_data (CustomerDetailResponse): For personalization context
            - refinement_count (int): Iteration tracking

    Returns:
        Dict for LangGraph to merge with:
            - refined_email (EmailContent|None): Improved email or None on error
            - refinement_count (int): Incremented counter
            - workflow_status (str): Processing status
            - refinement_time_seconds (float): Execution time

    Design Principles:
        - Surgical fixes: Address ONLY flagged issues, don't over-improve
        - No invention: Don't add benefits, features, or claims
        - Honest personalization: Report what was actually used
        - Python validation: Delegate length/format/banned-phrase checks to guardrails
        - Focused scope: Email + Feedback → Improved Email

    Note:
        Max refinements = 3 to prevent infinite loops.
        After max, escalate to MANUAL_REVIEW.
    """
    # Setup:
    correlation_id = state.get("correlation_id") or generate_correlation_id()
    start_time = time.time()

    log_node_entry(
        _node_name,
        correlation_id,
        ["generated_email", "critic_issues", "refinement_count"],
    )

    try:
        # GUARD: Check max refinements not exceeded
        refinement_count = state.get("refinement_count", 0)
        if refinement_count >= MAX_REFINEMENTS:
            refinement_time = time.time() - start_time
            logger.warning(
                f"Max refinements ({MAX_REFINEMENTS}) exceeded, escalating to manual review",
                extra={"correlation_id": correlation_id, "node": _node_name},
            )
            return {
                "refined_email": None,
                "refinement_count": refinement_count,
                "workflow_status": "error_max_refinements_exceeded",
                "correlation_id": correlation_id,
                "refinement_time_seconds": refinement_time,
            }

        # VALIDATE PREREQUISITES:
        if not state.get("generated_email"):
            raise ValueError("Missing generated_email in state")

        generated_email: EmailContent = state["generated_email"]
        critic_issues = state.get("critic_issues", [])
        customer_data = state.get("customer_data")

        if not customer_data:
            raise ValueError("Missing customer_data in state")

        if not critic_issues:
            logger.warning(
                "Refiner invoked without critic issues (unexpected)",
                extra={"correlation_id": correlation_id, "node": _node_name},
            )
            critic_issues = ["Unspecified improvements requested"]

        # Extract customer context (safe data only)
        preferred_name = customer_data.preferred_name
        first_name = customer_data.first_name
        plan_name = customer_data.plan_name

        logger.info(
            f"Starting refinement iteration {refinement_count + 1}/{MAX_REFINEMENTS}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )

        # BUILD REFINER PROMPT:
        system_prompt = get_system_prompt()

        with open("app/templates/email/refiner_task.txt", "r", encoding="utf-8") as f:
            refiner_task = f.read()

        # Format feedback (convert list to readable format)
        feedback_text = "\n".join(f"- {issue}" for issue in critic_issues)

        # Runtime context: original email + feedback + customer data
        context_section = f""" === IMPROVEMENT FEEDBACK ===

Issues to fix:
{feedback_text}

=== ORIGINAL EMAIL TO IMPROVE ===

Subject: {generated_email.subject}

Body:
{generated_email.body}

Personalized Elements Used: {json.dumps(generated_email.personalized_elements)}

=== CUSTOMER CONTEXT (For Personalization Reference) ===

preferred_name: {preferred_name or "(not provided)"}
first_name: {first_name}
plan_name: {plan_name}"""

        # Combine: system -> Task -> context -> feedback
        full_prompt = f"""{system_prompt}

{refiner_task}

{context_section}"""

        logger.debug(
            f"Refiner prompt rendered ({len(full_prompt)} chars)",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )

        # Call LLM for refinement (can use cheaper model)
        response = await call_llm_with_retry(
            full_prompt,
            correlation_id,
            model=settings.REFINER_MODEL,
        )

        # Parse LLM Response (extract_json_from_text returns dict, not string)
        response_dict = extract_json_from_text(response)

        # Strict Pydantic validation
        refined_email = EmailContent(
            subject=response_dict["subject"],
            body=response_dict["body"],
            personalized_elements=response_dict.get("personalized_elements", []),
        )

        logger.info(
            f"Email refined successfully (iteration {refinement_count + 1})",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )

        # SUCCESS - Return state update
        refinement_time = time.time() - start_time
        log_metric("email_refined", correlation_id, 1)

        return {
            "refined_email": refined_email,
            "refinement_count": refinement_count + 1,
            "refiner_last_feedback": critic_issues,
            "correlation_id": correlation_id,
            "workflow_status": "email_refined",
            "refinement_time_seconds": refinement_time,
        }

    except ValueError as e:
        refinement_time = time.time() - start_time
        logger.warning(
            f"Validation error in {_node_name}: {str(e)}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )
        return {
            "refined_email": None,
            "refinement_count": state.get("refinement_count", 0),
            "workflow_status": f"error_{_node_name}_validation",
            "correlation_id": correlation_id,
            "error_message": str(e),
            "refinement_time_seconds": refinement_time,
        }

    except ValidationError as e:
        refinement_time = time.time() - start_time
        logger.warning(
            f"Refiner email parsing error: {str(e)}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )
        return {
            "refined_email": None,
            "refinement_count": state.get("refinement_count", 0),
            "workflow_status": "error_refiner_parsing",
            "correlation_id": correlation_id,
            "error_message": "Invalid LLM response format",
            "refinement_time_seconds": refinement_time,
        }

    except Exception as e:
        refinement_time = time.time() - start_time
        logger.exception(
            f"Unexpected error in {_node_name}: {type(e).__name__}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )
        return {
            "refined_email": None,
            "refinement_count": state.get("refinement_count", 0),
            "workflow_status": "error_refiner_unexpected",
            "correlation_id": correlation_id,
            "error_message": str(e),
            "refinement_time_seconds": refinement_time,
        }
