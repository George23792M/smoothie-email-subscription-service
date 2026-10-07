"""
Phase 4: LangGraph Orchestration - Email Pipeline Workflow

Workflow:
  Generator → Critic → [Conditional Routing]
                ├─ SEND → FinalGuardrails → SendEmail → END
                ├─ REFINE → Refiner → [loop back to Critic, max 3x]
                └─ MANUAL_REVIEW → Escalate → END

Design Pattern: State Machine with Chain of Responsibility
- LangGraph StateGraph manages state transitions
- Conditional edges route based on critic recommendation
- Each node is independent async function taking/returning state updates
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, START, END

from app.graph.state import PipelineState, get_final_email
from app.guardrails.output_guards import OutputGuards
from app.agents.generator.node import generator_node
from app.agents.critic.node import critic_node
from app.agents.refiner.node import refiner_node, MAX_REFINEMENTS
from app.mcp import mcp_client
from app.exceptions.service_exception import ServiceException

logger = logging.getLogger(__name__)


def route_after_critic(
    state: PipelineState,
) -> Literal["final_guardrails", "refiner", "escalate"]:
    """
    Route to next node based on critic evaluation.

    PYTHON CONCEPT: Function Routing
    - Called by LangGraph's add_conditional_edges()
    - Returns node name to execute next
    - Replaces complex if/elif chains with data-driven logic

    Decision Tree:
    1. If max refinements exceeded → escalate (prevent infinite loop)
    2. If recommendation is SEND → final guardrails
    3. If recommendation is REFINE → refiner (will loop back)
    4. Otherwise (MANUAL_REVIEW) → escalate

    Args:
        state: Current pipeline state

    Returns:
        Next node name to execute
    """
    recommendation = state.get("critic_recommendation")
    refinement_count = state.get("refinement_count", 0)

    if refinement_count >= MAX_REFINEMENTS and recommendation == "REFINE":
        logger.warning(
            f"Max retries ({MAX_REFINEMENTS}) reached, escalating to manual review",
            extra={
                "customer_id": state.get("customer_id"),
                "correlation_id": state.get("correlation_id"),
            },
        )
        return "escalate"

    # Route based on critic recommendation
    if recommendation == "SEND":
        return "final_guardrails"
    elif recommendation == "REFINE":
        return "refiner"
    else:  # MANUAL REVIEW or unexpected
        return "escalate"


def route_after_refiner(state: PipelineState) -> Literal["critic", "escalate"]:
    """
    Route after refiner completes (loop-back to critic or exit).

    PYTHON CONCEPT: Conditional Edge Function
    - Refiner updates state and returns new version
    - This function decides: critic again (loop) or escalate (exit loop)
    - Checks for errors in refiner output

    Logic:
    - If refiner succeeded → loop back to critic for re-evaluation
    - If refiner failed → escalate (error handling)

    Args:
        state: State after refiner execution

    Returns:
        Next node: "critic" (loop) or "escalate" (exit, error)
    """
    # Check if refiner had an error
    if state.get("workflow_status", "").startswith("error_"):
        logger.error(
            f"Refiner error encountered: {state.get('error_message')}",
            extra={
                "customer_id": state.get("customer_id"),
                "correlation_id": state.get("correlation_id"),
            },
        )
        return "escalate"

    # Success: loop back to critic for re-evaulation
    return "critic"


def route_after_final_guardrails(
    state: PipelineState,
) -> Literal["send_email", "escalate"]:
    """
    Route after final guardrail checks.

    PYTHON CONCEPT: Guard Clause
    - If guardrails fail, stop immediately
    - Only proceed to send_email if all checks pass

    Args:
        state: State after final guardrails

    Returns:
        "send_email" if safe, "escalate" if issues found
    """
    if not state.get("final_guardrail_passed", False):
        logger.warning(
            f"Final guardrail check failed: {state.get('final_guardrail_result')}",
            extra={
                "customer_id": state.get("customer_id"),
                "correlation_id": state.get("correlation_id"),
            },
        )
        return "escalate"

    return "send_email"


# === PLACEHOLDER NODES (to be implemented in Phase 5-6) ===


async def final_guardrails_node(state: PipelineState) -> dict:
    """
    Final safety checks before sending email.

    Flow:
    1. Get final email (refined or generated)
    2. Run output guards (content checks)
    3. Return pass/fail + results
    """
    final_email = get_final_email(state)

    result = await OutputGuards.validate_generated_email(
        subject=final_email.subject, body=final_email.body
    )
    return {
        "final_guardrail_result": result,
        "final_guardrail_passed": result.passed,
        "workflow_status": (
            "READY_TO_SEND" if result.passed else "FINAL_GUARDRAIL_FAILED"
        ),
    }


async def send_email_node(state: PipelineState) -> dict:
    """
    Send email via Resend API.

    Flow:
    1. Get final email content
    2. Call Resend API to send
    3. Update state with message_id + timestamp
    4. Return success or error
    """
    final_email = get_final_email(state)
    customer = state["customer_data"]
    correlation_id = state.get("correlation_id")

    try:
        result = await mcp_client.send_email(
            recipient_email=customer.email,
            recipient_name=customer.preferred_name or customer.first_name,
            subject=final_email.subject,
            html_body=final_email.body,
            correlation_id=correlation_id,
        )

        return {
            "workflow_status": "SENT",
            "sent_at": result.get("sent_at"),
            "message_id": result.get("message_id"),
        }

    except ServiceException as ex:
        logger.error(
            f"Send email failed: {ex.error_message}",
            extra={
                "customer_id": state.get("customer_id"),
                "correlation_id": correlation_id,
            },
        )
        return {"workflow_status": "FAILED", "error_message": ex.error_message}


async def escalate_node(state: PipelineState) -> dict:
    """
    Escalate to manual review queue.

    Flow:
    1. Log escalation reason
    2. Insert into manual_review queue (database)
    3. Return escalation status
    """
    correlation_id = state.get("correlation_id", "")
    reason = (
        state.get("critic_recommendation") or state.get("workflow_status") or "unknown"
    )

    try:
        await mcp_client.escalate_manual_review(
            customer_id=state.get("customer_id", ""),
            correlation_id=correlation_id,
            reason=reason,
            details={
                "critic_issues": state.get("critic_issues", []),
                "refinement_count": state.get("refinement_count", 0),
                "error_message": state.get("error_message"),
            },
        )
    except ServiceException as ex:
        logger.error(
            f"Escalation failed: {ex.error_message}",
            extra={
                "customer_id": state.get("customer_id"),
                "correlation_id": correlation_id,
            },
        )
    return {"workflow_status": "MANUAL_REVIEW"}


# === BUILD LANGGRAPH WORKFLOW ===


def build_workflow() -> StateGraph:
    """
    Construct the LangGraph StateGraph.

    PYTHON CONCEPT: Graph Building
    - StateGraph manages state flow between nodes
    - Nodes are async functions (state in, state updates out)
    - Edges define transitions (direct or conditional)
    - Returns compiled graph callable

    Structure:
    - add_node(name, async_function): Register a node
    - add_edge(from, to): Direct transition
    - add_conditional_edges(from, routing_fn, {path: to}): Conditional routing
    - compile(): Produce final callable graph

    Args:
        None

    Returns:
        Compiled StateGraph ready for execution
    """

    workflow = StateGraph(PipelineState)

    # === ADD NODES ===
    workflow.add_node("generator", generator_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("refiner", refiner_node)
    workflow.add_node("final_guardrails", final_guardrails_node)
    workflow.add_node("send_email", send_email_node)
    workflow.add_node("escalate", escalate_node)

    # === ADD EDGES ===

    # Entry point
    workflow.add_edge(START, "generator")

    # Generator always flows to critic
    workflow.add_edge("generator", "critic")

    # Critic routes to final_guardrails, refiner, or escalate based on recommendation
    workflow.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "final_guardrails": "final_guardrails",
            "refiner": "refiner",
            "escalate": "escalate",
        },
    )

    # Refiner loops back to critic or exists to escalte on error
    workflow.add_conditional_edges(
        "refiner", route_after_refiner, {"critic": "critic", "escalate": "escalate"}
    )

    # Final guardrails routes to send_email or escalate
    workflow.add_conditional_edges(
        "final_guardrails",
        route_after_final_guardrails,
        {"send_email": "send_email", "escalate": "escalate"},
    )

    # Send email ends workflow
    workflow.add_edge("send_email", END)

    # Escalate ends workflow
    workflow.add_edge("escalate", END)

    return workflow


# === SINGLETON WORKFLOW INSTANCE ===
_workflow: StateGraph | None = None


def get_workflow() -> StateGraph:
    """
    Get or create the compiled workflow (lazy singleton).

    PYTHON CONCEPT: Singleton Pattern
    - Create expensive object once, reuse thereafter
    - Avoids rebuilding StateGraph on every request
    - Thread-safe in asyncio (single-threaded)

    Returns:
        Compiled StateGraph
    """
    global _workflow

    if _workflow is None:
        _workflow = build_workflow().compile()
        logger.info("Email pipeline workflow completed")
    return _workflow
