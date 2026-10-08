"""DAO for batch_runs table operations."""

import logging

from app.services.db_pool import DatabasePool
from app.exceptions.database_exception import DatabaseExecutionException

logger = logging.getLogger(__name__)


class BatchRunsDAO:
    """Data Access Object for batch_runs table."""

    # SQL Queries
    QUERY_GET_BATCH_STATUS = """
        SELECT id, batch_type, status, total_customers, successful_count, 
               failed_count, skipped_count, started_at, completed_at, error_message
        FROM batch_runs
        ORDER BY started_at DESC
        LIMIT $1
    """

    def __init__(self, db_pool: DatabasePool):
        """
        Initialize DAO with database pool dependency.

        Args:
            db_pool: Database connection pool instance
        """
        self.db_pool = db_pool

    async def get_batch_status(self, limit: int = 10) -> list[dict]:
        """
        Fetch recent batch execution history.

        Args:
            limit: Maximum number of batch records to return

        Returns:
            List of batch run records ordered by most recent first

        Raises:
            DatabaseExecutionException: If database query fails
        """
        try:
            async with self.db_pool.acquire() as connection:
                rows = await connection.fetch(self.QUERY_GET_BATCH_STATUS, limit)

            return [dict(row) for row in rows] if rows else []

        except Exception as ex:
            logger.error(
                "Error fetching batch status history",
                exc_info=True,
                extra={"limit": limit},
            )
            raise DatabaseExecutionException(
                f"Failed to fetch batch status: {str(ex)}"
            ) from ex


__all__ = ["BatchRunsDAO"]
