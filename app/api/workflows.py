"""
Phase 6 Task 3: FastAPI Endpoints for Workflow Management

REST API for:
- Triggering workflows on-demand for specific customer(s)
- Querying workflow execution history
- Checking batch job status

PYTHON CONCEPT: REST API Design Principles
- POST for actions (trigger)
- GET for queries (history, status)
- Return meaningful HTTP status codes
- Use Pydantic models for request/response validation
- Separate concerns: API layer → Service layer → DAO layer → Database
- Dependency Injection: Inject services/DAOs for better testability
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from app.services.workflow_execution import (
    execute_workflow_for_customers,
    BatchExecutionResult,
)
from app.services.workflow_service import WorkflowService
from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.dao.batch_runs_dao import BatchRunsDAO
from app.services.db_pool import DatabasePool
from app.api.schemas.requests import TriggerWorkflowRequest
from app.api.schemas.responses import (
    WorkflowResultResponse,
    BatchExecutionResultResponse,
    WorkflowHistoryItem,
    BatchRunItem,
)
from app.exceptions.database_exception import DatabaseExecutionException
from app.exceptions.service_exception import ServiceException

logger = logging.getLogger(__name__)

# Create router for workflow endpoints
router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


async def get_workflow_service() -> WorkflowService:
    """
    FastAPI dependency injection for WorkflowService.

    Creates and returns WorkflowService with injected DAOs.

    Returns:
        WorkflowService instance with dependencies
    """
    pool = await DatabasePool.get_pool()
    workflow_runs_dao = WorkflowRunsDAO(db_pool=pool)
    batch_runs_dao = BatchRunsDAO(db_pool=pool)
    return WorkflowService(
        workflow_runs_dao=workflow_runs_dao,
        batch_runs_dao=batch_runs_dao,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/trigger", response_model=BatchExecutionResultResponse)
async def trigger_workflow(request: TriggerWorkflowRequest):
    """
    Trigger workflow execution for specified customer(s).

    On-demand endpoint to execute workflows outside of scheduled batch.

    Args:
        request: TriggerWorkflowRequest with customer_ids and workflow_type

    Returns:
        BatchExecutionResultResponse with results for each customer

    Raises:
        HTTPException: If workflow execution fails
    """
    try:
        logger.info(
            f"Triggering workflow for {len(request.customer_ids)} customers",
            extra={"workflow_type": request.workflow_type},
        )

        batch_result = await execute_workflow_for_customers(
            customer_ids=request.customer_ids,
            workflow_type=request.workflow_type,
        )

        # Convert to response model
        results = [
            WorkflowResultResponse(
                customer_id=r.customer_id,
                status=r.status,
                message=r.message,
                error_message=r.error_message,
                workflow_run_id=r.workflow_run_id,
                email_sent=r.email_sent,
            )
            for r in batch_result.results
        ]

        return BatchExecutionResultResponse(
            batch_type=batch_result.batch_type,
            total_customers=batch_result.total_customers,
            successful_count=batch_result.successful_count,
            failed_count=batch_result.failed_count,
            skipped_count=batch_result.skipped_count,
            results=results,
        )

    except Exception as ex:
        logger.error("Error triggering workflow", exc_info=True)
        raise HTTPException(status_code=500, detail="Workflow execution failed") from ex


@router.get("/history/{customer_id}", response_model=list[WorkflowHistoryItem])
async def get_workflow_history(
    customer_id: str,
    workflow_type: Optional[str] = Query(None, description="Filter by workflow type"),
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Query workflow execution history for a customer.

    Uses WorkflowService injected via dependency injection.

    Args:
        customer_id: Customer UUID
        workflow_type: Optional filter by workflow type
        limit: Maximum number of records to return (default 10, max 100)
        service: Injected WorkflowService instance (via FastAPI dependency injection)

    Returns:
        List of workflow run records ordered by most recent first

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(
            f"Querying workflow history for customer {customer_id}",
            extra={"workflow_type": workflow_type, "limit": limit},
        )

        # Use injected WorkflowService
        history = await service.get_workflow_history(
            customer_id=customer_id,
            workflow_type=workflow_type,
            limit=limit,
        )

        return history

    except DatabaseExecutionException as ex:
        logger.error(
            "Database error querying workflow history",
            exc_info=True,
            extra={"customer_id": customer_id},
        )
        raise HTTPException(status_code=500, detail="Database query failed") from ex
    except Exception as ex:
        logger.error("Error querying workflow history", exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed") from ex


@router.get("/batch-status", response_model=list[BatchRunItem])
async def get_batch_status(
    limit: int = Query(10, ge=1, le=100, description="Max records to return"),
    service: WorkflowService = Depends(get_workflow_service),
):
    """
    Query recent batch execution history.

    Uses WorkflowService injected via dependency injection.

    Args:
        limit: Maximum number of batch records to return (default 10, max 100)
        service: Injected WorkflowService instance (via FastAPI dependency injection)

    Returns:
        List of batch run records ordered by most recent first

    Raises:
        HTTPException: If query fails
    """
    try:
        logger.info(f"Querying batch status with limit {limit}")

        # Use injected WorkflowService
        batch_status = await service.get_batch_status(limit=limit)

        return batch_status

    except DatabaseExecutionException as ex:
        logger.error("Database error querying batch status", exc_info=True)
        raise HTTPException(status_code=500, detail="Database query failed") from ex
    except Exception as ex:
        logger.error("Error querying batch status", exc_info=True)
        raise HTTPException(status_code=500, detail="Query failed") from ex
