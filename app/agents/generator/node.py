"""
LangGraph node for generator agent.

Orchestrates: validate → context → prompt → LLM → parse → validate → return.
"""

import logging
import time
from typing import Any, Dict

from app.agents.generator.prompts import render_generation_prompt
from app.agents.generator.llm_client import call_llm_with_retry
from app.agents.utils import (
    build_generation_context,
    generate_correlation_id,
    log_metric,
    log_node_entry,
    log_node_exit,
    parse_llm_response,
)
from app.core.config import settings
from app.graph.state import PipelineState
from app.guardrails.output_guards import OutputGuards

logger = logging.getLogger(__name__)

_node_name = "generator"


async def generator_node(state: PipelineState) -> Dict[str, Any]:
    """
    LangGraph node: Generate personalized email via LLM.

    Flow:
    1. Validate prerequisites (guardrails passed, state complete)
    2. Build context from customer data
    3. Render prompt template with Jinja2
    4. Call LLM with retry + LangSmith tracing
    5. Parse response into EmailContent
    6. Validate output (guardrails)
    7. Return state update (LangGraph merges)

    Args:
        state: LangGraph PipelineState

    Returns:
        Dict for LangGraph to merge into state
    """
    # Setup:
    correlation_id = state.get("correlation_id") or generate_correlation_id()
    start_time = time.time()

    log_node_entry(_node_name, correlation_id, ["customer_id", "customer_data"])

    try:

        # VALIDATE PREREQUISITES
        if not state.get("input_guardrail_passed"):
            logger.warning(
                f"Input guardrail failed, skipped {_node_name}",
                extra={"correlation_id": correlation_id, "node": _node_name},
            )
            return {
                "generated_email": None,
                "output_guardrail_passed": False,
                "workflow_status": "stopped_input_validation_failed",
                "correlation_id": correlation_id,
                "generation_time_seconds": time.time() - start_time,
            }

        if not state.get("customer_data"):
            raise ValueError("Missing customer_data in state")

        # BUILD CONTEXT
        customer_context = build_generation_context(state["customer_data"])

        # RENDER PROMPT
        prompt = render_generation_prompt(customer_context)
        logger.debug(
            f"Prompt rendered ({len(prompt)} chars)",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )

        # CALL LLM
        response = await call_llm_with_retry(
            prompt,
            correlation_id,
            model=settings.GENERATOR_MODEL,
        )

        # PARSE RESPONSE
        email_content = parse_llm_response(response)
        logger.info(
            f"Email parsed: subject={email_content.subject[:50]}...",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )

        # VALIDATED OUTPUT
        guardrail_result = await OutputGuards.validate_generated_email(
            email_content.subject, email_content.body
        )

        if not guardrail_result.passed:
            logger.warning(
                f"Output guardrails failed: {guardrail_result.violations}",
                extra={"correlation_id": correlation_id, "node": _node_name},
            )
            return {
                "generated_email": email_content,
                "output_guardrail_result": guardrail_result,
                "output_guardrail_passed": False,
                "generation_time_seconds": time.time() - start_time,
                "correlation_id": correlation_id,
                "workflow_status": "stopped_output_validation_failed",
            }

        # SUCCESS - Return state update
        generation_time = time.time() - start_time
        log_metric("email_generated_success", correlation_id, 1)
        logger.info(
            f"Email generation successful ({generation_time:.2f}s)",
            extra={
                "correlation_id": correlation_id,
                "node": _node_name,
                "generation_time_seconds": generation_time,
            },
        )

        return {
            "generated_email": email_content,
            "output_guardrail_result": guardrail_result,
            "output_guardrail_passed": True,
            "generation_time_seconds": generation_time,
            "correlation_id": correlation_id,
            "workflow_status": "email_generated",
        }

    except ValueError as e:
        generation_time = time.time() - start_time
        logger.warning(
            f"Validation error in {_node_name}: {str(e)}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )
        return {
            "generated_email": None,
            "output_guardrail_passed": False,
            "generation_time_seconds": generation_time,
            "correlation_id": correlation_id,
            "workflow_status": f"error_{_node_name}_validation",
        }

    except Exception as e:
        generation_time = time.time() - start_time
        logger.exception(
            f"Unexpected error in {_node_name}: {type(e).__name__}",
            extra={"correlation_id": correlation_id, "node": _node_name},
        )
        return {
            "generated_email": None,
            "output_guardrail_passed": False,
            "generation_time_seconds": generation_time,
            "correlation_id": correlation_id,
            "workflow_status": f"error_{_node_name}_unexpected",
        }
