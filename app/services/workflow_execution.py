"""
Phase 6 Task 1: Workflow Execution Service

Shared service for executing workflows (used by batch scheduler and API endpoints).

PYTHON CONCEPT: Single Source of Truth (DRY Principle)
- Both batch scheduler and on-demand API call the same function
- No code duplication between triggers
- Centralized logging and error handling

Architecture Note: MCP Integration (Phase 6+)
- Currently uses direct database queries for MVP speed
- Future: Replace DB queries with MCP service calls:
  - _mcp_get_recent_subscriptions() → customer_service.get_recent_subscriptions()
  - _mcp_check_workflow_exists() → workflow_service.check_workflow_exists()
  - _mcp_create_workflow_run() → workflow_service.create_workflow_run()
  - _mcp_update_workflow_run() → workflow_service.update_workflow_run()
- Placeholder functions marked with TODO: MCP

Flow:
1. Query customers from database (TODO: use MCP)
2. For each customer:
   - Check if workflow_runs record exists (TODO: use MCP)
   - Create workflow_runs record (TODO: use MCP)
   - Execute LangGraph workflow
   - Update workflow_runs with result (TODO: use MCP)
3. Track results: successful_count, failed_count, skipped_count
4. Return aggregated results
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from app.services.db_pool import DatabasePool
from app.services.db_service import fetch_customer_subscription_details_from_db
from app.graph.executor import run_email_pipeline
from app.exceptions.service_exception import ServiceException
from app.exceptions.database_exception import DatabaseExecutionException
from app.exceptions.customer_exception import CustomerNotFoundException

logger = logging.getLogger(__name__)


# ============================================================================
# MCP PLACEHOLDER FUNCTIONS (Phase 6+)
# ============================================================================
# TODO: Replace these with actual MCP service calls in Phase 7


async def _mcp_get_recent_subscriptions() -> list[str]:
    """
    MCP Placeholder: Get customers subscribed in last 10 minutes.

    Future: Call customer_service.get_recent_subscriptions()
    Current: Falls back to direct DB query

    Returns:
        List of customer UUIDs
    """
    # TODO: Replace with:
    # return await mcp_client._call_tool(
    #     "customer_service",
    #     "get_recent_subscriptions",
    #     {"minutes": 10}
    # )
    pass


async def _mcp_check_workflow_exists(
    customer_id: str, workflow_type: str
) -> Optional[str]:
    """
    MCP Placeholder: Check if workflow_runs record exists for customer.

    Future: Call workflow_service.check_workflow_exists()
    Current: Falls back to direct DB query

    Args:
        customer_id: Customer UUID
        workflow_type: Workflow type

    Returns:
        Workflow run ID if exists, None otherwise
    """
    # TODO: Replace with:
    # return await mcp_client._call_tool(
    #     "workflow_service",
    #     "check_workflow_exists",
    #     {"customer_id": customer_id, "workflow_type": workflow_type}
    # )
    pass


async def _mcp_create_workflow_run(customer_id: str, workflow_type: str) -> str:
    """
    MCP Placeholder: Create workflow_runs record.

    Future: Call workflow_service.create_workflow_run()
    Current: Falls back to direct DB query

    Args:
        customer_id: Customer UUID
        workflow_type: Workflow type

    Returns:
        Workflow run ID
    """
    # TODO: Replace with:
    # return await mcp_client._call_tool(
    #     "workflow_service",
    #     "create_workflow_run",
    #     {
    #         "customer_id": customer_id,
    #         "workflow_type": workflow_type,
    #         "status": "PENDING"
    #     }
    # )
    pass


async def _mcp_update_workflow_run(
    workflow_run_id: str,
    status: str,
    email_status: str,
    error_message: Optional[str] = None,
) -> None:
    """
    MCP Placeholder: Update workflow_runs record.

    Future: Call workflow_service.update_workflow_run()
    Current: Falls back to direct DB query

    Args:
        workflow_run_id: Workflow run ID
        status: Workflow status (SUCCESS, FAILED)
        email_status: Email status (SENT, PENDING)
        error_message: Error message if failed
    """
    # TODO: Replace with:
    # await mcp_client._call_tool(
    #     "workflow_service",
    #     "update_workflow_run",
    #     {
    #         "workflow_run_id": workflow_run_id,
    #         "status": status,
    #         "email_status": email_status,
    #         "error_message": error_message
    #     }
    # )
    pass


# ============================================================================
# TYPES & RESULTS
# ============================================================================


@dataclass
class WorkflowExecutionResult:
    """Result of executing workflow for one customer."""

    customer_id: str
    status: str  # "SUCCESS", "FAILED", "SKIPPED"
    message: str
    error_message: Optional[str] = None
    workflow_run_id: Optional[str] = None
    email_sent: bool = False


@dataclass
class BatchExecutionResult:
    """Aggregated result of executing workflows for multiple customers."""

    batch_type: str
    total_customers: int = 0
    successful_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    results: list[WorkflowExecutionResult] = field(default_factory=list)

    def add_result(self, result: WorkflowExecutionResult) -> None:
        """Add individual result and update counters."""
        self.results.append(result)
        if result.status == "SUCCESS":
            self.successful_count += 1
        elif result.status == "FAILED":
            self.failed_count += 1
        elif result.status == "SKIPPED":
            self.skipped_count += 1


# ============================================================================
# DATABASE QUERIES
# ============================================================================

QUERY_RECENT_NEW_SUBSCRIPTIONS = """
SELECT c.id AS customer_id
FROM customers c
JOIN subscriptions s ON c.id = s.customer_id
WHERE c.is_active = TRUE
AND s.status = 'ACTIVE'
AND s.start_date >= NOW() - INTERVAL '10 minutes'
GROUP BY c.id
ORDER BY MAX(s.start_date) DESC;
"""

QUERY_EXISTING_WORKFLOW_RUN = """
SELECT id FROM workflow_runs
WHERE customer_id = $1
AND workflow_type = $2
AND status IN ('PENDING', 'RUNNING', 'SUCCESS')
LIMIT 1;
"""

QUERY_CREATE_WORKFLOW_RUN = """
INSERT INTO workflow_runs 
(customer_id, workflow_type, status, attempt_count, started_at)
VALUES ($1, $2, $3, $4, $5)
RETURNING id;
"""

QUERY_UPDATE_WORKFLOW_RUN = """
UPDATE workflow_runs
SET status = $1,
    email_status = $2,
    validation_errors = $3,
    completed_at = $4,
    attempt_count = attempt_count + 1,
    updt_ts = $5
WHERE id = $6;
"""


# ============================================================================
# MAIN EXECUTION FUNCTION
# ============================================================================


async def execute_workflow_for_customers(
    customer_ids: list[str],
    workflow_type: str = "NEW_REGISTRATION",
) -> BatchExecutionResult:
    """
    Execute workflow for list of customers.

    PYTHON CONCEPT: Async Iteration + Exception Handling
    - Process multiple customers asynchronously
    - Continue on individual failures (one customer's error doesn't stop batch)
    - Collect results for caller to analyze

    Args:
        customer_ids: List of customer UUIDs to process
        workflow_type: Workflow type (default: "NEW_REGISTRATION")

    Returns:
        BatchExecutionResult with:
        - total_customers, successful_count, failed_count, skipped_count
        - List of individual results (one per customer)

    Flow for each customer:
    1. Check if workflow_runs record exists (skip if found)
    2. Create workflow_runs record (status='PENDING')
    3. Fetch customer details from database
    4. Execute LangGraph workflow
    5. Update workflow_runs with result
    6. Track success/failure
    """
    batch_result = BatchExecutionResult(
        batch_type=workflow_type,
        total_customers=len(customer_ids),
    )

    pool = await DatabasePool.get_pool()

    for customer_id in customer_ids:
        try:
            # ===== Step 1: Check for existing workflow =====
            async with pool.acquire() as connection:
                existing = await connection.fetchrow(
                    QUERY_EXISTING_WORKFLOW_RUN, customer_id, workflow_type
                )

                if existing:
                    result = WorkflowExecutionResult(
                        customer_id=customer_id,
                        status="SKIPPED",
                        message="Workflow already processed for this customer",
                        workflow_run_id=str(existing["id"]),
                    )
                    batch_result.add_result(result)
                    logger.info(
                        f"Skipped customer {customer_id}: workflow already exists",
                        extra={"workflow_type": workflow_type},
                    )
                    continue

                # ===== Step 2: Create workflow_runs record =====
                workflow_run_id = await connection.fetchval(
                    QUERY_CREATE_WORKFLOW_RUN,
                    customer_id,
                    workflow_type,
                    "PENDING",
                    0,
                    datetime.utcnow(),
                )

            # ===== Step 3: Fetch customer details =====
            try:
                customer_data = await fetch_customer_subscription_details_from_db(
                    customer_id
                )
            except CustomerNotFoundException as e:
                # TODO: MCP - Replace with _mcp_update_workflow_run()
                async with pool.acquire() as connection:
                    await connection.execute(
                        QUERY_UPDATE_WORKFLOW_RUN,
                        "FAILED",
                        "PENDING",
                        str(e),
                        datetime.utcnow(),
                        datetime.utcnow(),
                        workflow_run_id,
                    )
                result = WorkflowExecutionResult(
                    customer_id=customer_id,
                    status="FAILED",
                    message="Customer not found",
                    error_message=str(e),
                    workflow_run_id=str(workflow_run_id),
                )
                batch_result.add_result(result)
                logger.warning(
                    f"Customer {customer_id} not found",
                    extra={"workflow_type": workflow_type},
                )
                continue

            # ===== Step 4: Execute LangGraph workflow =====
            try:
                final_state = await run_email_pipeline(
                    customer_id=customer_id,
                    customer_data=customer_data,
                )

                workflow_status = final_state.get("workflow_status", "FAILED")
                email_sent = workflow_status == "sent"

                # ===== Step 5: Update workflow_runs =====
                # TODO: MCP - Replace with _mcp_update_workflow_run()
                async with pool.acquire() as connection:
                    await connection.execute(
                        QUERY_UPDATE_WORKFLOW_RUN,
                        "SUCCESS" if email_sent else "FAILED",
                        "SENT" if email_sent else "PENDING",
                        final_state.get("error_message"),
                        datetime.utcnow(),
                        datetime.utcnow(),
                        workflow_run_id,
                    )

                result = WorkflowExecutionResult(
                    customer_id=customer_id,
                    status="SUCCESS",
                    message="Workflow executed successfully",
                    workflow_run_id=str(workflow_run_id),
                    email_sent=email_sent,
                )
                batch_result.add_result(result)

                logger.info(
                    f"Customer {customer_id}: workflow completed",
                    extra={
                        "workflow_type": workflow_type,
                        "email_sent": email_sent,
                    },
                )

            except Exception as ex:
                logger.error(
                    f"Workflow execution failed for customer {customer_id}",
                    exc_info=True,
                    extra={
                        "workflow_type": workflow_type,
                        "error": str(ex),
                    },
                )

                # TODO: MCP - Replace with _mcp_update_workflow_run()
                async with pool.acquire() as connection:
                    await connection.execute(
                        QUERY_UPDATE_WORKFLOW_RUN,
                        "FAILED",
                        "PENDING",
                        str(ex),
                        datetime.utcnow(),
                        datetime.utcnow(),
                        workflow_run_id,
                    )

                result = WorkflowExecutionResult(
                    customer_id=customer_id,
                    status="FAILED",
                    message="Workflow execution error",
                    error_message=str(ex),
                    workflow_run_id=str(workflow_run_id),
                )
                batch_result.add_result(result)

        except DatabaseExecutionException as ex:
            logger.error(
                f"Database error for customer {customer_id}",
                exc_info=True,
                extra={"workflow_type": workflow_type},
            )
            result = WorkflowExecutionResult(
                customer_id=customer_id,
                status="FAILED",
                message="Database error",
                error_message=str(ex),
            )
            batch_result.add_result(result)

        except Exception as ex:
            logger.error(
                f"Unexpected error for customer {customer_id}",
                exc_info=True,
                extra={"workflow_type": workflow_type},
            )
            result = WorkflowExecutionResult(
                customer_id=customer_id,
                status="FAILED",
                message="Unexpected error",
                error_message=str(ex),
            )
            batch_result.add_result(result)

    return batch_result


async def get_recently_subscribed_customers() -> list[str]:
    """
    Query customers who subscribed in the last 10 minutes.

    TODO: MCP - Replace with _mcp_get_recent_subscriptions()

    Returns:
        List of customer UUIDs
    """
    pool = await DatabasePool.get_pool()

    try:
        async with pool.acquire() as connection:
            rows = await connection.fetch(QUERY_RECENT_NEW_SUBSCRIPTIONS)
            return [row["customer_id"] for row in rows]
    except Exception as ex:
        logger.error("Error fetching recent subscriptions", exc_info=True)
        raise DatabaseExecutionException() from ex
