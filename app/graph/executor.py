"""
Phase 4 Executor: Main entry point for email pipeline orchestration.

Usage:
    from app.graph.executor import run_email_pipeline

    result = await run_email_pipeline(
        customer_id="cust_123",
        customer_data=customer_detail_response
    )

    if result["workflow_status"] == "sent":
        message_id = result["message_id"]
    elif result["workflow_status"] == "manual_review":
        # Handle escalation
        pass

PYTHON CONCEPT: Entry Point Function
- Single responsibility: orchestrate workflow execution
- Async wrapper around LangGraph
- Handles initialization, error catching, logging
- Returns final state with all results
"""

import logging
from typing import Optional

from app.graph.state import PipelineState, get_final_email
from app.graph.workflow import get_workflow
from app.agents.utils import generate_correlation_id
from app.schemas.responses import CustomerDetailResponse

logger = logging.getLogger(__name__)


async def run_email_pipeline(
    customer_id: str,
    customer_data: CustomerDetailResponse,
    correlation_id: Optional[str] = None,
) -> PipelineState:
    """
    Execute the complete email generation and delivery pipeline.

    PYTHON CONCEPT: Async Entry Point
    - Takes business inputs (customer_id, data)
    - Initializes state
    - Runs compiled LangGraph workflow
    - Returns final state (success or error)

    Flow:
    1. Generate correlation ID (tracing)
    2. Initialize PipelineState with inputs
    3. Get compiled workflow
    4. Execute workflow (Generator → Critic → [Refiner loop] → Send/Escalate)
    5. Log results
    6. Return final state

    Args:
        customer_id: Customer identifier for email
        customer_data: Customer details (name, email, plan, preferences)
        correlation_id: Optional tracing ID (generated if not provided)

    Returns:
        PipelineState: Final state after workflow execution with:
        - workflow_status: "sent", "manual_review", or "FAILED"
        - message_id: Resend API message ID (if sent)
        - error_message: Error details (if failed)
        - All intermediate results (generated_email, critic_evaluation, etc.)

    Raises:
        No exceptions raised. All errors captured in state["error_message"]
    """

    # Generate or use provided correlation ID
    if not correlation_id:
        correlation_id = generate_correlation_id()

    logger.info(
        f"Starting email pipeline for customer {customer_id}",
        extra={"correlation_id": correlation_id},
    )

    # === INITITALIZE STATE ===
    initial_state: PipelineState = {
        "customer_id": customer_id,
        "customer_data": customer_data,
        "correlation_id": correlation_id,
        "refinement_count": 0,
        "workflow_status": "PROCESSING",
    }

    try:
        # === RUN WORKFLOW ===
        workflow = get_workflow()
        final_state = await workflow.ainvoke(initial_state)

        # === LOG RESULTS  ====
        final_email = get_final_email(final_state)
        logger.info(
            f"Pipeline completed: {final_state.get('workflow_status')}",
            extra={
                "correlation_id": correlation_id,
                "customer_id": customer_id,
                "status": final_state.get("workflow_status"),
                "refinements": final_state.get("refinement_count", 0),
                "email_subject": final_email.subject[:50] if final_email else None,
            },
        )
        return final_state

    except Exception as e:
        logger.exception(
            f"Unexpected error in pipeline: {str(e)}",
            extra={"correlation_id": correlation_id, "customer_id": customer_id},
        )
        return {
            "customer_id": customer_id,
            "customer_data": customer_data,
            "correlation_id": correlation_id,
            "workflow_status": "FAILED",
            "error_message": str(e),
        }
