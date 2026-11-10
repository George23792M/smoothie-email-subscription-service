"""MCP-backed workflow history access."""

from app.services.postgres_workflows import PostgresWorkflows


class WorkflowRunsDAO:
    """Fetch workflow history through the PostgreSQL MCP server."""

    def __init__(self, client: PostgresWorkflows) -> None:
        """Store the injected data adapter."""
        self.client = client

    async def get_workflow_history(
        self, customer_id: str, workflow_type: str | None = None, limit: int = 10
    ) -> list[dict]:
        """Return bounded workflow history for a customer."""
        return await self.client.history(customer_id, workflow_type, limit)
