"""Tests for MCP-backed workflow and batch history DAOs."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.dao.batch_runs_dao import BatchRunsDAO
from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.mcp.postgres_client import PostgresMCPError


@pytest.mark.asyncio
async def test_get_workflow_history_without_filter():
    """Return rows and forward the customer and limit."""
    client = AsyncMock()
    customer_id = str(uuid4())
    rows = [{"customer_id": customer_id}]
    client.history.return_value = rows

    result = await WorkflowRunsDAO(client).get_workflow_history(customer_id, limit=10)

    assert result == rows
    client.history.assert_awaited_once_with(customer_id, None, 10)


@pytest.mark.asyncio
async def test_get_workflow_history_with_filter():
    """Forward an explicit workflow type filter."""
    client = AsyncMock()
    client.history.return_value = []
    customer_id = str(uuid4())

    assert await WorkflowRunsDAO(client).get_workflow_history(customer_id, "NEW_REGISTRATION", 10) == []
    client.history.assert_awaited_once_with(customer_id, "NEW_REGISTRATION", 10)


@pytest.mark.asyncio
async def test_get_workflow_history_handles_exception():
    """Do not convert transport failure into empty history."""
    client = AsyncMock()
    client.history.side_effect = PostgresMCPError("unavailable", "Unavailable")

    with pytest.raises(PostgresMCPError):
        await WorkflowRunsDAO(client).get_workflow_history(str(uuid4()))


@pytest.mark.asyncio
async def test_get_batch_status_returns_records():
    """Return the batches supplied by the data adapter."""
    client = AsyncMock()
    client.batches.return_value = [{"batch_type": "NEW_REGISTRATION"}]

    result = await BatchRunsDAO(client).get_batch_status()

    assert result == [{"batch_type": "NEW_REGISTRATION"}]
    client.batches.assert_awaited_once_with(10)


@pytest.mark.asyncio
async def test_get_batch_status_respects_limit():
    """Forward the requested history limit."""
    client = AsyncMock()
    client.batches.return_value = []

    assert await BatchRunsDAO(client).get_batch_status(5) == []
    client.batches.assert_awaited_once_with(5)


@pytest.mark.asyncio
async def test_get_batch_status_handles_exception():
    """Surface data-service failures."""
    client = AsyncMock()
    client.batches.side_effect = PostgresMCPError("unavailable", "Unavailable")

    with pytest.raises(PostgresMCPError):
        await BatchRunsDAO(client).get_batch_status()
