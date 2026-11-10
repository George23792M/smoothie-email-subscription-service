"""Typed application adapter for PostgreSQL MCP workflow tools."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.mcp.postgres_client import PostgresMCPClient, PostgresMCPError
from app.schemas.responses import CustomerDetailResponse


class RegistrationClaim(BaseModel):
    """A registration run owned by the requesting worker."""

    id: UUID
    customer_id: UUID
    claimed_by: str
    workflow_type: Literal["NEW_REGISTRATION"]
    status: Literal["RUNNING"]
    attempt_count: int


class ActiveEmailTemplate(BaseModel):
    """Proposed active-template fields, subject to external contract agreement."""

    model_config = ConfigDict(extra="forbid", strict=True)

    active: Literal[True]
    subject: str = Field(min_length=1, max_length=200)
    html_body: str = Field(min_length=1, max_length=65536)


class PostgresWorkflows:
    """Expose typed operations needed by API and workflow services."""

    def __init__(self, client: PostgresMCPClient) -> None:
        """Store the configured MCP client."""
        self.client = client

    async def customer(self, customer_id: str) -> CustomerDetailResponse:
        """Fetch customer data once; the external read-only contract is unverified."""
        payload = await self.client.call("get_subscription_customer", {"customer_id": customer_id})
        if not isinstance(payload, dict):
            raise PostgresMCPError("invalid_response", "Invalid customer response")
        first_name, last_name = payload.get("first_name"), payload.get("last_name")
        if not isinstance(first_name, str) or not isinstance(last_name, str):
            raise PostgresMCPError("invalid_response", "Invalid customer response")
        return CustomerDetailResponse(
            **payload, customer_name=f"{first_name} {last_name}".strip()
        )

    async def active_welcome_template(self) -> ActiveEmailTemplate | None:
        """Fetch the proposed welcome template contract once, failing closed."""
        payload = await self.client.call(
            "get_active_email_template", {"template_name": "welcome"}
        )
        if not isinstance(payload, dict):
            raise PostgresMCPError("invalid_response", "Invalid email template response")
        if payload == {"found": False} and payload["found"] is False:
            return None
        if set(payload) != {"found", "template"} or payload["found"] is not True:
            raise PostgresMCPError("invalid_response", "Invalid email template response")
        template = payload["template"]
        if not isinstance(template, dict) or template.get("active") is not True:
            raise PostgresMCPError("invalid_response", "Invalid email template response")
        try:
            return ActiveEmailTemplate.model_validate(template)
        except ValidationError:
            raise PostgresMCPError("invalid_response", "Invalid email template response") from None

    async def claim(
        self, request_id: str, worker_id: str, customer_id: str | None = None
    ) -> RegistrationClaim | None:
        """Claim a pending registration once for the supplied request."""
        payload = await self.client.call(
            "claim_registration_workflow",
            {"request_id": request_id, "worker_id": worker_id, "customer_id": customer_id},
        )
        if payload is None:
            return None
        claim = RegistrationClaim.model_validate(payload)
        if claim.claimed_by != worker_id or (customer_id and str(claim.customer_id) != customer_id):
            raise PostgresMCPError("invalid_response", "Invalid workflow claim ownership")
        return claim

    async def complete(
        self, workflow_id: str, worker_id: str, result: dict[str, Any]
    ) -> None:
        """Complete an owned workflow with a safe terminal result."""
        await self.client.call(
            "complete_registration_workflow",
            {"workflow_id": workflow_id, "worker_id": worker_id, "result": result},
        )

    async def create_batch(self, batch_id: str) -> None:
        """Create a replay-safe batch record."""
        await self.client.call("create_subscription_batch", {"batch_id": batch_id})

    async def complete_batch(self, batch_id: str, result: dict[str, Any]) -> None:
        """Persist a batch's terminal status and counters."""
        await self.client.call("complete_subscription_batch", {"batch_id": batch_id, "result": result})

    async def history(self, customer_id: str, workflow_type: str | None, limit: int) -> list[dict]:
        """Fetch a customer's bounded workflow history."""
        payload = await self.client.call(
            "get_subscription_workflow_history",
            {"customer_id": customer_id, "workflow_type": workflow_type, "limit": limit},
        )
        if not isinstance(payload, list):
            raise PostgresMCPError("invalid_response", "Invalid workflow history response")
        return payload

    async def batches(self, limit: int) -> list[dict]:
        """Fetch bounded batch history."""
        payload = await self.client.call("get_subscription_batch_history", {"limit": limit})
        if not isinstance(payload, list):
            raise PostgresMCPError("invalid_response", "Invalid batch history response")
        return payload

    async def ready(self) -> bool:
        """Check that the MCP server can execute a database query."""
        return await self.client.call("check_database_ready", {}) == {"ready": True}


def get_postgres_workflows() -> PostgresWorkflows:
    """Build the data adapter using the application settings."""
    return PostgresWorkflows(
        PostgresMCPClient(
            settings.POSTGRES_MCP_URL, settings.POSTGRES_MCP_TOKEN,
            settings.MCP_REQUEST_TIMEOUT_SECONDS,
            retry_attempts=settings.POSTGRES_READ_RETRY_ATTEMPTS,
            retry_budget=settings.POSTGRES_READ_RETRY_BUDGET_SECONDS,
            retry_initial=settings.POSTGRES_READ_RETRY_INITIAL_SECONDS,
            retry_max=settings.POSTGRES_READ_RETRY_MAX_SECONDS,
        )
    )
