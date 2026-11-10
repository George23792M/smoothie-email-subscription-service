"""Keep registration workflow execution unavailable until integration."""

from dataclasses import dataclass, field
from typing import NoReturn

from app.services.postgres_workflows import PostgresWorkflows, RegistrationClaim


class DeliveryUnavailableError(Exception):
    """Prevent workflow claims when the email service is unavailable."""


@dataclass
class WorkflowExecutionResult:
    """Result for one requested customer."""

    customer_id: str
    status: str
    message: str
    error_message: str | None = None
    workflow_run_id: str | None = None
    email_sent: bool = False


@dataclass
class BatchExecutionResult:
    """Aggregate counts and results for a batch of workflows."""

    batch_type: str
    total_customers: int = 0
    successful_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[WorkflowExecutionResult] = field(default_factory=list)

    def add_result(self, result: WorkflowExecutionResult) -> None:
        """Append one result and increment its matching count."""
        self.results.append(result)
        if result.status == "SUCCESS":
            self.successful_count += 1
        elif result.status == "FAILED":
            self.failed_count += 1
        elif result.status == "SKIPPED":
            self.skipped_count += 1


def require_delivery_ready() -> NoReturn:
    """Reject processing unconditionally until execution is integrated."""
    raise DeliveryUnavailableError("Email delivery is unavailable")


async def execute_workflow_for_customers(
    customer_ids: list[str], workflow_type: str = "NEW_REGISTRATION"
) -> BatchExecutionResult:
    """Reject targeted execution before acquiring an adapter or claim."""
    require_delivery_ready()


async def execute_claim(adapter: PostgresWorkflows, claim: RegistrationClaim) -> WorkflowExecutionResult:
    """Reject direct claim execution without inspecting the claim or adapter."""
    require_delivery_ready()
