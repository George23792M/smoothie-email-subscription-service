"""Service layer for workflow-related operations.

Service layer provides high-level business logic and orchestration,
using DAO layer for data access operations.
"""

import logging
from typing import Optional

from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.dao.batch_runs_dao import BatchRunsDAO
from app.api.schemas.responses import WorkflowHistoryItem, BatchRunItem
from app.exceptions.database_exception import DatabaseExecutionException

logger = logging.getLogger(__name__)


class WorkflowService:
    """Service for workflow management operations."""

    def __init__(
        self,
        workflow_runs_dao: WorkflowRunsDAO,
        batch_runs_dao: BatchRunsDAO,
    ):
        """
        Initialize service with DAO dependencies.

        Args:
            workflow_runs_dao: DAO for workflow_runs table
            batch_runs_dao: DAO for batch_runs table
        """
        self.workflow_runs_dao = workflow_runs_dao
        self.batch_runs_dao = batch_runs_dao

    async def get_workflow_history(
        self,
        customer_id: str,
        workflow_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[WorkflowHistoryItem]:
        """
        Fetch workflow execution history for a customer.

        Args:
            customer_id: Customer UUID
            workflow_type: Optional filter by workflow type
            limit: Maximum number of records to return

        Returns:
            List of WorkflowHistoryItem objects ordered by most recent first

        Raises:
            DatabaseExecutionException: If database query fails
        """
        try:
            logger.info(
                f"Fetching workflow history for customer {customer_id}",
                extra={"workflow_type": workflow_type, "limit": limit},
            )

            # Use DAO to fetch raw data
            rows = await self.workflow_runs_dao.get_workflow_history(
                customer_id=customer_id,
                workflow_type=workflow_type,
                limit=limit,
            )

            if not rows:
                logger.info(
                    f"No workflow history found for customer {customer_id}",
                    extra={"workflow_type": workflow_type},
                )
                return []

            # Transform to response models
            history_items = [
                WorkflowHistoryItem(
                    id=str(row["id"]),
                    customer_id=str(row["customer_id"]),
                    workflow_type=row["workflow_type"],
                    status=row["status"],
                    email_status=row["email_status"],
                    attempt_count=row["attempt_count"],
                    started_at=row["started_at"].isoformat(),
                    completed_at=(
                        row["completed_at"].isoformat() if row["completed_at"] else None
                    ),
                    error_message=row["validation_errors"],
                )
                for row in rows
            ]

            logger.info(
                f"Found {len(history_items)} workflow history items",
                extra={"customer_id": customer_id},
            )
            return history_items

        except DatabaseExecutionException:
            raise
        except Exception as ex:
            logger.error(
                "Unexpected error fetching workflow history",
                exc_info=True,
                extra={"customer_id": customer_id},
            )
            raise DatabaseExecutionException(
                f"Failed to fetch workflow history: {str(ex)}"
            ) from ex

    async def get_batch_status(self, limit: int = 10) -> list[BatchRunItem]:
        """
        Fetch recent batch execution history.

        Args:
            limit: Maximum number of batch records to return

        Returns:
            List of BatchRunItem objects ordered by most recent first

        Raises:
            DatabaseExecutionException: If database query fails
        """
        try:
            logger.info(f"Fetching batch status with limit {limit}")

            # Use DAO to fetch raw data
            rows = await self.batch_runs_dao.get_batch_status(limit=limit)

            if not rows:
                logger.info("No batch runs found")
                return []

            # Transform to response models
            batch_items = [
                BatchRunItem(
                    id=str(row["id"]),
                    batch_type=row["batch_type"],
                    status=row["status"],
                    total_customers=row["total_customers"],
                    successful_count=row["successful_count"],
                    failed_count=row["failed_count"],
                    skipped_count=row["skipped_count"],
                    started_at=row["started_at"].isoformat(),
                    completed_at=(
                        row["completed_at"].isoformat() if row["completed_at"] else None
                    ),
                    error_message=row["error_message"],
                )
                for row in rows
            ]

            logger.info(f"Found {len(batch_items)} batch run items")
            return batch_items

        except DatabaseExecutionException:
            raise
        except Exception as ex:
            logger.error(
                "Unexpected error fetching batch status",
                exc_info=True,
                extra={"limit": limit},
            )
            raise DatabaseExecutionException(
                f"Failed to fetch batch status: {str(ex)}"
            ) from ex


__all__ = ["WorkflowService"]
