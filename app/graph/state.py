from typing import Annotated, Optional, List, Literal
from typing_extensions import TypedDict
from pydantic import BaseModel

from app.schemas.responses import CustomerDetailResponse
from app.guardrails.input_guards import GuardRailResult

# === PYTHON CONCEPT: TypedDict ===
# TypedDict = Dictionary with typed keys
# vs Dict[str, Any] which has no key validation
# vs Pydantic BaseModel (more strict validation)


class EmailContent(BaseModel):
    """Generated email content from Generator agent."""

    subject: str
    body: str
    personalized_elements: List[str]  # Which fields were personalized


class CriticEvaluation(BaseModel):
    """Structured output from Critic agent."""

    is_valid: bool
    severity: Literal["CRITICAL", "MODERATE", "MINOR", "PASS"]
    issues: List[str]  # What issues were found
    recommendation: Literal["SEND", "REFINE", "MANUAL_REVIEW"]
    reasoning: str  # Why the recommendation


class PipelineState(TypedDict, total=False):
    """
    Shared state object that flows through LangGraph.

    PYTHON CONCEPT: TypedDict
    - total=False: All fields are optional
    - Type-checked at development time (if using mypy)
    - Runtime: Still a regular dict (no validation)

    Workflow:
    1. Input: customer_id
    2. Database: Fetch customer_data
    3. Input Guardrails: Check customer_data validity
    4. Generator: Create email content
    5. Output Guardrails: Validate generated email
    6. Critic: Deep evaluation
    7. [Conditional] Refiner: Fix if MODERATE issues
    8. Final Guardrails: Pre-send checks
    9. Output: Send email or queue for review
    """

    # === Input Data ===
    customer_id: str
    correlation_id: str
    customer_data: CustomerDetailResponse

    # === Input Guardrails Results ===
    input_guardrail_result: GuardRailResult
    input_guardrail_passed: bool

    # === Generator Agent Output ===
    generated_email: EmailContent
    generation_time_seconds: float

    # === Output Guardrails Results ===
    output_guardrail_result: GuardRailResult
    output_guardrail_passed: bool

    # === Critic Agent Output ===
    critic_evaluation: CriticEvaluation
    critic_issues: List[str]
    critic_recommendation: Literal["SEND", "REFINE", "MANUAL_REVIEW"]

    # === Refiner Agent (Optional) ===
    refinement_count: int  # Number of times refiner was invoked
    refined_email: Optional[EmailContent]
    refiner_last_feedback: str

    # === Final Guardrails ===
    final_guardrail_result: GuardRailResult
    final_guardrail_passed: bool

    # === Final Status ===
    workflow_status: Literal[
        "PENDING",
        "PROCESSING",
        "SENT",
        "MANUAL_REVIEW",
        "FAILED",
        "FINAL_GUARDRAIL_FAILED",
        "READY_TO_SEND",
    ]

    error_message: Optional[str]
    sent_at: Optional[str]  # ISO timestamp
    message_id: Optional[str]  # Resend API message ID


# === STATE HELPERS ===


def get_final_email(state: PipelineState) -> EmailContent:
    """
    Get the final email to send (refined or generated).

    PYTHON CONCEPT: Function Logic
    - Conditional return based on state
    - If Refiner ran and succeeded, use refined
    - Otherwise use original generated
    """
    if state.get("refined_email") and state["refinement_count"] > 0:
        return state["refined_email"]
    return state["generated_email"]


def is_critical_failure(state: PipelineState) -> bool:
    """
    Determine if workflow has critical failures.

    PYTHON CONCEPT: Boolean Logic
    - Use 'any()' to check if any condition is True
    - Short-circuits (stops early when first True found)
    """
    return any(
        [
            not state.get("input_guardrail_passed", False),
            not state.get("output_guardrail_passed", False),
            state.get("critic_recommendation") == "MANUAL_REVIEW",
        ]
    )


def get_all_violations(state: PipelineState) -> List[str]:
    """
    Aggregate all violations from all guardrail checks.

    PYTHON CONCEPT: List Comprehension (Alternative)
    - Functional style to collect violations
    - vs traditional: for loop + append pattern
    """
    violations = []

    # Add violations from each layer
    for layer_key in [
        "input_guardrail_result",
        "output_guardrail_result",
        "final_guardrail_result",
    ]:
        if layer_key in state:
            violations.extend(state[layer_key].violations)

    # Add Critic issues
    violations.extend(state.get("critic_issues", []))

    return violations
