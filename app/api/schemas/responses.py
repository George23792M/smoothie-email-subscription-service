"""API Response models for workflow endpoints."""

from typing import Optional
from pydantic import BaseModel


class WorkflowResultResponse(BaseModel):
    """Response for single workflow execution result."""

    customer_id: str
    status: str
    message: str
    error_message: Optional[str] = None
    workflow_run_id: Optional[str] = None
    email_sent: bool = False


class BatchExecutionResultResponse(BaseModel):
    """Response for batch workflow execution."""

    batch_type: str
    total_customers: int
    successful_count: int
    failed_count: int
    skipped_count: int
    results: list[WorkflowResultResponse]


class WorkflowHistoryItem(BaseModel):
    """Single workflow run record from database."""

    id: str
    customer_id: str
    workflow_type: str
    status: str
    email_status: str
    attempt_count: int
    started_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class BatchRunItem(BaseModel):
    """Single batch run record from database."""

    id: str
    batch_type: str
    status: str
    total_customers: int
    successful_count: int
    failed_count: int
    skipped_count: int
    started_at: str
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


__all__ = [
    "WorkflowResultResponse",
    "BatchExecutionResultResponse",
    "WorkflowHistoryItem",
    "BatchRunItem",
]
