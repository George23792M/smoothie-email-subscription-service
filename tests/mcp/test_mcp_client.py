"""
Tests for MCPClient with MCPRegistry integration.

Coverage:
- Service URL retrieval from registry
- Success/error tracking
- Tool invocation
- Error handling and fallback
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.mcp.mcp_client import _call_tool, _get_registry_url
from app.exceptions.service_exception import ServiceException

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_registry():
    """Mock MCPRegistry for testing."""
    registry = MagicMock()
    registry.get_healthiest = MagicMock(return_value="http://workflow:8000")
    registry.record_success = MagicMock()
    registry.record_error = MagicMock()
    return registry


@pytest.fixture
def mock_tool():
    """Mock MCP tool."""
    tool = AsyncMock()
    tool.ainvoke = AsyncMock(return_value={"status": "success", "id": "123"})
    tool.name = "test_tool"
    return tool


# ============================================================================
# TEST: URL RETRIEVAL
# ============================================================================


class TestURLRetrieval:
    """Service URL retrieval from registry."""

    def test_get_registry_url_returns_healthy_url(self, mock_registry):
        """get_registry_url() should return healthiest URL."""
        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            url = _get_registry_url()
            assert url == "http://workflow:8000"
            mock_registry.get_healthiest.assert_called_once_with("workflow_service")

    def test_get_registry_url_raises_when_no_healthy_replicas(self, mock_registry):
        """Should raise if no healthy replicas available."""
        mock_registry.get_healthiest.return_value = None

        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with pytest.raises(ServiceException, match="No healthy"):
                _get_registry_url()


# ============================================================================
# TEST: TOOL INVOCATION
# ============================================================================


class TestToolInvocation:
    """Tool invocation with registry routing."""

    @pytest.mark.asyncio
    async def test_call_tool_invokes_and_tracks_success(self, mock_registry, mock_tool):
        """_call_tool() should invoke tool and record success."""
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.list_tools = AsyncMock(return_value=[mock_tool])

        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with patch("app.mcp.mcp_client.MCPAdapter", return_value=mock_adapter):
                result = await _call_tool("test_tool", {"id": "123"})

                assert result == {"status": "success", "id": "123"}
                mock_registry.record_success.assert_called_once_with(
                    "workflow_service", "http://workflow:8000"
                )

    @pytest.mark.asyncio
    async def test_call_tool_tracks_error_on_failure(self, mock_registry, mock_tool):
        """_call_tool() should record error on failure."""
        mock_tool.ainvoke = AsyncMock(side_effect=Exception("Tool error"))
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.list_tools = AsyncMock(return_value=[mock_tool])

        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with patch("app.mcp.mcp_client.MCPAdapter", return_value=mock_adapter):
                with pytest.raises(ServiceException):
                    await _call_tool("test_tool", {"id": "123"})

                mock_registry.record_error.assert_called_once_with(
                    "workflow_service", "http://workflow:8000"
                )

    @pytest.mark.asyncio
    async def test_call_tool_raises_if_tool_not_found(self, mock_registry):
        """Should raise ServiceException if tool not found."""
        mock_adapter = AsyncMock()
        mock_adapter.__aenter__ = AsyncMock(return_value=mock_adapter)
        mock_adapter.__aexit__ = AsyncMock(return_value=None)
        mock_adapter.list_tools = AsyncMock(return_value=[])

        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with patch("app.mcp.mcp_client.MCPAdapter", return_value=mock_adapter):
                with pytest.raises(ServiceException, match="not found"):
                    await _call_tool("nonexistent_tool", {})

                mock_registry.record_error.assert_called_once_with(
                    "workflow_service", "http://workflow:8000"
                )


# ============================================================================
# TEST: ERROR HANDLING
# ============================================================================


class TestErrorHandling:
    """Error handling and fallback behavior."""

    @pytest.mark.asyncio
    async def test_connection_error_tracks_and_raises(self, mock_registry):
        """Connection errors should be tracked and wrapped."""
        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with patch(
                "app.mcp.mcp_client.MCPAdapter",
                side_effect=Exception("Connection failed"),
            ):
                with pytest.raises(ServiceException, match="unavailable"):
                    await _call_tool("any_tool", {})

                mock_registry.record_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_healthy_replicas_raises_immediately(self, mock_registry):
        """Should fail immediately if no healthy replicas."""
        mock_registry.get_healthiest.return_value = None

        with patch("app.mcp.mcp_client.get_registry", return_value=mock_registry):
            with pytest.raises(ServiceException, match="No healthy"):
                await _call_tool("any_tool", {})

            mock_registry.record_error.assert_not_called()
