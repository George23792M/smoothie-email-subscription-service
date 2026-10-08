"""
Tests for FastAPI workflow endpoints with dependency injection.

Tests the REST API layer for workflow management including:
- On-demand workflow triggering
- Workflow execution history queries
- Batch job status queries

Tests use FastAPI dependency overrides to mock WorkflowService.
"""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.workflows import router, get_workflow_service
from app.services.workflow_service import WorkflowService
from app.dao.workflow_runs_dao import WorkflowRunsDAO
from app.dao.batch_runs_dao import BatchRunsDAO
from app.api.schemas.responses import WorkflowHistoryItem, BatchRunItem


# ============================================================================
# FIXTURES FOR DEPENDENCY OVERRIDES
# ============================================================================


def create_test_app():
    """Create a test FastAPI app with router."""
    app = FastAPI()
    app.include_router(router)
    return app


def get_mock_workflow_service() -> WorkflowService:
    """Create a mock WorkflowService for testing."""
    mock_workflow_dao = MagicMock(spec=WorkflowRunsDAO)
    mock_batch_dao = MagicMock(spec=BatchRunsDAO)
    mock_service = WorkflowService(
        workflow_runs_dao=mock_workflow_dao,
        batch_runs_dao=mock_batch_dao,
    )
    return mock_service


# ============================================================================
# TESTS: POST /api/workflows/trigger
# ============================================================================


class TestTriggerWorkflowEndpoint:
    """Test POST /api/workflows/trigger endpoint."""

    @pytest.mark.asyncio
    async def test_trigger_workflow_returns_batch_result(self):
        """Should return aggregated batch result."""
        from app.services.workflow_execution import (
            BatchExecutionResult,
            WorkflowExecutionResult,
        )

        customer_id = str(uuid4())
        request_data = {
            "customer_ids": [customer_id],
            "workflow_type": "NEW_REGISTRATION",
        }

        batch_result = BatchExecutionResult(
            batch_type="NEW_REGISTRATION",
            total_customers=1,
        )
        batch_result.add_result(
            WorkflowExecutionResult(
                customer_id=customer_id,
                status="SUCCESS",
                message="Workflow executed successfully",
                workflow_run_id=str(uuid4()),
                email_sent=True,
            )
        )

        with patch(
            "app.api.workflows.execute_workflow_for_customers",
            new_callable=AsyncMock,
            return_value=batch_result,
        ):
            app = create_test_app()
            client = TestClient(app)

            response = client.post("/api/workflows/trigger", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["total_customers"] == 1
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_trigger_workflow_with_multiple_customers(self):
        """Should handle multiple customers in a single trigger."""
        from app.services.workflow_execution import (
            BatchExecutionResult,
            WorkflowExecutionResult,
        )

        customer_ids = [str(uuid4()), str(uuid4())]
        request_data = {
            "customer_ids": customer_ids,
            "workflow_type": "NEW_REGISTRATION",
        }

        batch_result = BatchExecutionResult(
            batch_type="NEW_REGISTRATION",
            total_customers=2,
        )
        for cid in customer_ids:
            batch_result.add_result(
                WorkflowExecutionResult(
                    customer_id=cid,
                    status="SUCCESS",
                    message="OK",
                    workflow_run_id=str(uuid4()),
                    email_sent=True,
                )
            )

        with patch(
            "app.api.workflows.execute_workflow_for_customers",
            new_callable=AsyncMock,
            return_value=batch_result,
        ):
            app = create_test_app()
            client = TestClient(app)

            response = client.post("/api/workflows/trigger", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["total_customers"] == 2
        assert len(data["results"]) == 2


# ============================================================================
# TESTS: GET /api/workflows/history/{customer_id}
# ============================================================================


class TestWorkflowHistoryEndpoint:
    """Test GET /api/workflows/history/{customer_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_workflow_history_returns_records(self):
        """Should return workflow history for customer."""
        customer_id = str(uuid4())
        workflow_run_id = str(uuid4())

        mock_history = [
            WorkflowHistoryItem(
                id=workflow_run_id,
                customer_id=customer_id,
                workflow_type="NEW_REGISTRATION",
                status="SUCCESS",
                email_status="SENT",
                attempt_count=1,
                started_at=datetime.utcnow().isoformat(),
                completed_at=datetime.utcnow().isoformat(),
                error_message=None,
            )
        ]

        app = create_test_app()

        # Override the dependency with a mock service
        mock_service = get_mock_workflow_service()
        mock_service.get_workflow_history = AsyncMock(return_value=mock_history)

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get(f"/api/workflows/history/{customer_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["customer_id"] == customer_id

    @pytest.mark.asyncio
    async def test_get_workflow_history_with_workflow_type_filter(self):
        """Should filter by workflow_type if provided."""
        customer_id = str(uuid4())

        app = create_test_app()

        mock_service = get_mock_workflow_service()
        mock_service.get_workflow_history = AsyncMock(return_value=[])

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get(
            f"/api/workflows/history/{customer_id}?workflow_type=NEW_REGISTRATION"
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_workflow_history_returns_empty_for_unknown_customer(self):
        """Should return empty list if no history found."""
        customer_id = str(uuid4())

        app = create_test_app()

        mock_service = get_mock_workflow_service()
        mock_service.get_workflow_history = AsyncMock(return_value=[])

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get(f"/api/workflows/history/{customer_id}")

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ============================================================================
# TESTS: GET /api/workflows/batch-status
# ============================================================================


class TestBatchStatusEndpoint:
    """Test GET /api/workflows/batch-status endpoint."""

    @pytest.mark.asyncio
    async def test_get_batch_status_returns_records(self):
        """Should return batch run history."""
        batch_id = str(uuid4())

        mock_batch_status = [
            BatchRunItem(
                id=batch_id,
                batch_type="NEW_REGISTRATION",
                status="SUCCESS",
                total_customers=10,
                successful_count=10,
                failed_count=0,
                skipped_count=0,
                started_at=datetime.utcnow().isoformat(),
                completed_at=datetime.utcnow().isoformat(),
                error_message=None,
            )
        ]

        app = create_test_app()

        mock_service = get_mock_workflow_service()
        mock_service.get_batch_status = AsyncMock(return_value=mock_batch_status)

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get("/api/workflows/batch-status")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["batch_type"] == "NEW_REGISTRATION"

    @pytest.mark.asyncio
    async def test_get_batch_status_respects_limit(self):
        """Should respect limit parameter."""
        app = create_test_app()

        mock_service = get_mock_workflow_service()
        mock_service.get_batch_status = AsyncMock(return_value=[])

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get("/api/workflows/batch-status?limit=5")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_batch_status_returns_empty_if_no_runs(self):
        """Should return empty list if no batch runs exist."""
        app = create_test_app()

        mock_service = get_mock_workflow_service()
        mock_service.get_batch_status = AsyncMock(return_value=[])

        async def override_get_workflow_service():
            return mock_service

        app.dependency_overrides[get_workflow_service] = override_get_workflow_service

        client = TestClient(app)
        response = client.get("/api/workflows/batch-status")

        assert response.status_code == 200
        data = response.json()
        assert data == []
