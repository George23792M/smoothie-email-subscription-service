"""
Agent utility functions - functional, idiomatic Python.

PHILOSOPHY:
- Use standard library + Python idioms
- Let Pydantic handle validation
- Let LangGraph handle state
- Functions, not classes (when possible)
- No wrapper classes for existing functionality

This is production-grade precisely because it's SIMPLE.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import ValidationError

from app.graph.state import EmailContent
from app.schemas.responses import CustomerDetailResponse

logger = logging.getLogger(__name__)


# ============================================================================
# CORRELATION ID (Single function, not a class)
# ============================================================================


def generate_correlation_id() -> str:
    """
    Generate unique ID for workflow tracing.

    That's it. No class wrapper needed.
    """
    return uuid.uuid4().hex


# ============================================================================
# JSON PARSING (Pure function)
# ============================================================================


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract JSON from markdown or raw text.

    Handles:
    - Direct JSON: {"key": "value"}
    - Markdown JSON: ```json\n{...}\n```
    - Generic markdown: ```\n{...}\n```

    Args:
        text: LLM response (may contain markdown)

    Returns:
        Parsed dictionary

    Raises:
        ValueError: If JSON invalid or not found
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Input must be non-empty string")

    # Try to extract markdown JSON blocks
    extracted = text
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end != -1:
            extracted = text[start:end]
    elif "```" in text:
        start = text.find("```") + len("```")
        end = text.find("```", start)
        if end != -1:
            extracted = text[start:end]

    extracted = extracted.strip()

    try:
        return json.loads(extracted)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}", extra={"text_preview": extracted[:100]})
        raise ValueError(f"Invalid JSON: {e}")


def parse_llm_response(text: str) -> EmailContent:
    """
    Extract JSON from text and validate as EmailContent.

    Lets Pydantic do all validation (no custom validator class).

    Args:
        text: LLM response

    Returns:
        EmailContent object (typed, validated)

    Raises:
        ValueError: If parsing or validation fails
    """
    try:
        parsed_dict = extract_json_from_text(text)
        email = EmailContent(**parsed_dict)  # Pydantic validates

        logger.info(
            "Parsed LLM response",
            extra={
                "subject_len": len(email.subject),
                "body_len": len(email.body),
                "personalized_count": len(email.personalized_elements),
            },
        )
        return email
    except ValidationError as e:
        logger.error(
            f"Validation error: {e}", extra={"input_keys": list(parsed_dict.keys())}
        )
        raise ValueError(f"Invalid email content: {e}")
    except ValueError as e:
        # Already logged by extract_json_from_text
        raise


# ============================================================================
# CONTEXT BUILDING (Simple functions)
# ============================================================================


def build_generation_context(customer_data: CustomerDetailResponse) -> Dict[str, Any]:
    """
    Transform customer data to prompt context.

    Simple dict - no dataclass wrapper needed.

    Args:
        customer_data: Database record

    Returns:
        Dict ready for Jinja2 template rendering
    """
    # Determine best name (defensive order)
    customer_name = (
        customer_data.preferred_name
        or customer_data.customer_name
        or f"{customer_data.first_name} {customer_data.last_name}"
    ).strip()

    if not customer_name:
        raise ValueError("Cannot determine customer name")

    # Build context dict - only include non-None values
    return {
        "customer_id": customer_data.customer_id,
        "customer_name": customer_name,
        "first_name": customer_data.first_name,
        "last_name": customer_data.last_name,
        "plan_name": customer_data.plan_name or "Standard",
        "email": customer_data.email,
        "timestamp": datetime.utcnow().isoformat(),
    }


def build_critic_context(
    customer_name: str,
    plan_name: Optional[str],
    subject: str,
    body: str,
) -> Dict[str, str]:
    """Build context for Critic evaluation."""
    return {
        "customer_name": customer_name,
        "plan_name": plan_name or "Standard",
        "email_subject": subject,
        "email_body_preview": body[:500],
    }


# ============================================================================
# HELPER FUNCTIONS (No classes needed)
# ============================================================================


def log_node_entry(node_name: str, correlation_id: str, state_keys: list[str]) -> None:
    """Log when agent node starts."""
    logger.info(
        f"{node_name} START",
        extra={
            "node": node_name,
            "correlation_id": correlation_id,
            "state_keys": state_keys,
        },
    )


def log_node_exit(
    node_name: str, correlation_id: str, duration_ms: float, status: str = "success"
) -> None:
    """Log when agent node completes."""
    logger.info(
        f"{node_name} END",
        extra={
            "node": node_name,
            "correlation_id": correlation_id,
            "duration_ms": duration_ms,
            "status": status,
        },
    )


def log_metric(
    metric_name: str, value: float, tags: Optional[Dict[str, str]] = None
) -> None:
    """Record a performance metric."""
    logger.info(
        f"metric: {metric_name}={value}",
        extra={"metric_name": metric_name, "metric_value": value, "tags": tags or {}},
    )
