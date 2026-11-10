"""MCP-backed batch history access."""

from app.services.postgres_workflows import PostgresWorkflows


class BatchRunsDAO:
    """Fetch batch history through the PostgreSQL MCP server."""

    def __init__(self, client: PostgresWorkflows) -> None:
        """Store the injected data adapter."""
        self.client = client

    async def get_batch_status(self, limit: int = 10) -> list[dict]:
        """Return bounded recent batch history."""
        return await self.client.batches(limit)
