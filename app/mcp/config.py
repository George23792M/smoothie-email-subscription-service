"""
MCP service configuration from environment variables.

ENVIRONMENT VARIABLES (set these):
  EMAIL_SERVICE_REPLICAS="http://localhost:9001,http://localhost:9002"
  CUSTOMER_SERVICE_REPLICAS="http://localhost:8001"

UPGRADE PATH (GCP/Kubernetes):
  Just replace get_service_replicas() to use K8s DNS - no other changes needed!
"""

import os
import logging
from typing import List

logger = logging.getLogger(__name__)


def _env_var_name(service_name: str) -> str:
    """Convert service name to environment variable name."""
    return f"{service_name.upper()}_REPLICAS"


def _parse_replicas(replicas_str: str) -> List[str]:
    """Parse comma-separated replica URLs."""
    replicas = [url.strip() for url in replicas_str.split(",") if url.strip()]

    if not replicas:
        raise ValueError("Parsed replicas list is empty")

    return replicas


def get_service_replicas(
    service_name: str, fallback: List[str] | None = None
) -> List[str]:
    """
    Get service replicas from environment variable.

    Args:
        service_name: Service name (e.g., "email_service")
        fallback: Fallback replicas if env var not set (for local dev)

    Returns:
        List of replica URLs
    """
    env_key = _env_var_name(service_name)
    replicas_str = os.getenv(env_key)

    if not replicas_str:
        if fallback:
            logger.warning(
                f"Environment variable {env_key} not set, using fallback",
                extra={"service": service_name, "fallback_count": len(fallback)},
            )
            return fallback

        raise ValueError(
            f"Environment variable {env_key} not set and no fallback provided"
        )

    replicas = _parse_replicas(replicas_str)
    logger.info(
        f"Loaded {len(replicas)} replicas for '{service_name}'",
        extra={"service": service_name},
    )
    return replicas


# Service-specific getter functions with fallbacks for local development
def get_email_service_replicas() -> List[str]:
    """Get email service replicas."""
    return get_service_replicas("email_service", fallback=["http://localhost:9001"])


def get_customer_service_replicas() -> List[str]:
    """Get customer service replicas."""
    return get_service_replicas("customer_service", fallback=["http://localhost:8001"])


def get_workflow_service_replicas() -> List[str]:
    """Get workflow service replicas."""
    return get_service_replicas("workflow_service", fallback=["http://localhost:7001"])


def get_escalation_service_replicas() -> List[str]:
    """Get escalation service replicas."""
    return get_service_replicas(
        "escalation_service", fallback=["http://localhost:6001"]
    )


def get_metrics_service_replicas() -> List[str]:
    """Get metrics service replicas."""
    return get_service_replicas("metrics_service", fallback=["http://localhost:5001"])
