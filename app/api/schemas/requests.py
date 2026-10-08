"""API Request models for workflow endpoints."""

from pydantic import BaseModel, Field


class TriggerWorkflowRequest(BaseModel):
    """Request to trigger workflow for customer(s)."""

    customer_ids: list[str] = Field(..., min_length=1, description="Customer UUIDs")
    workflow_type: str = Field(
        default="NEW_REGISTRATION", description="Type of workflow to execute"
    )


__all__ = ["TriggerWorkflowRequest"]
