"""DAO for workflow_runs table operations."""

import logging
from typing import Optional

from app.services.db_pool import DatabasePool
from app.exceptions.database_exception import DatabaseExecutionException

logger = logging.getLogger(__name__)


class WorkflowRunsDAO:
    """Data Access Object for workflow_runs table."""

    # SQL Queries
    QUERY_GET_WORKFLOW_HISTORY = """
        SELECT id, customer_id, workflow_type, status, email_status, 
               attempt_count, started_at, completed_at, validation_errors
        FROM workflow_runs
        WHERE customer_id = $1
        {workflow_type_filter}
        ORDER BY started_at DESC
        LIMIT $2
    """

    QUERY_GET_WORKFLOW_HISTORY_WITH_TYPE = """
        SELECT id, customer_id, workflow_type, status, email_status, 
               attempt_count, started_at, completed_at, validation_errors
        FROM workflow_runs
        WHERE customer_id = $1 AND workflow_type = $2
        ORDER BY started_at DESC
        LIMIT $3
    """

    def __init__(self, db_pool: DatabasePool):
        """
        Initialize DAO with database pool dependency.

        Args:
            db_pool: Database connection pool instance
        """
        self.db_pool = db_pool

    async def get_workflow_history(
        self,
        customer_id: str,
        workflow_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict]:
        """
        Fetch workflow execution history for a customer.

        Args:
            customer_id: Customer UUID
            workflow_type: Optional filter by workflow type
            limit: Maximum number of records to return

        Returns:
            List of workflow run records ordered by most recent first

        Raises:
            DatabaseExecutionException: If database query fails
        """
        try:
            async with self.db_pool.acquire() as connection:
                if workflow_type:
                    rows = await connection.fetch(
                        self.QUERY_GET_WORKFLOW_HISTORY_WITH_TYPE,
                        customer_id,
                        workflow_type,
                        limit,
                    )
                else:
                    rows = await connection.fetch(
                        self.QUERY_GET_WORKFLOW_HISTORY.format(workflow_type_filter=""),
                        customer_id,
                        limit,
                    )

            return [dict(row) for row in rows] if rows else []

        except Exception as ex:
            logger.error(
                f"Error fetching workflow history for customer {customer_id}",
                exc_info=True,
                extra={"workflow_type": workflow_type},
            )
            raise DatabaseExecutionException(
                f"Failed to fetch workflow history: {str(ex)}"
            ) from ex


__all__ = ["WorkflowRunsDAO"]
