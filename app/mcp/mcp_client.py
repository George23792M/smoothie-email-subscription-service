"""
MCP Client: Thin wrapper around langchain.mcp.MCPAdapter for the
separately-deployed MCP service.

PYTHON CONCEPT: Adapter Wrapper
- Isolates LangGraph nodes from MCPAdapter connection details
- One place to change if the transport or tool contract changes
- Errors from MCP are translated into this app's exception types
"""

import logging
from typing import Any

from langchain.mcp import MCPAdapter

from app.core.config import settings
from app.exceptions.service_exception import ServiceException
from app.exceptions.customer_exception import CustomerNotFoundException

logger = logging.getLogger(__name__)


async def _call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    """
    Connect to the MCP service, find a tool by name, and invoke it.

    Args:
        tool_name: Name of the tool exposed by the MCP server
        arguments: Keyword arguments to pass to the tool

    Returns:
        The tool's return value (shape depends on the tool)

    Raises:
        ServicException: If the MCP call fails unexpectedly
    """
    try:
        async with MCPAdapter(settings.MCP_SERVER_URL) as adapter:
            tools = await adapter.list_tools()
            tool = next((t for t in tools if t.name == tool_name), None)

            if tool is None:
                raise ServiceException(f"MCP tool '{tool_name}' not found on sever")

            return await tool.ainvoke(arguments)

    except Exception as ex:
        logger.error(
            "MCP tool call failed: %s(%s)", tool_name, arguments, exc_info=True
        )
        raise ServiceException(f"MCP server is unavailable") from ex


async def fetch_customer_details(customer_id: str) -> dict[str, Any]:
    """
    Fetch customer profile via the MCP service.

    Args:
        customer_id: Customer UUID

    Returns:
        Customer detail fields as returned by the MCP tool

    Raises:
        CustomerNotFoundException: If the customer does not exist
        DatabaseExecutionException: If the MCP call fails
    """
    result = await _call_tool("fetch_customer_details", {"customer_id": customer_id})

    if result is None:
        raise CustomerNotFoundException(
            customer_id=customer_id,
            error_message=f"Customer record not found for customer_id: {customer_id}",
        )
    return result


async def create_workflow_run(
    customer_id: str, workflow_type: str, correlation_id: str
) -> dict[str, Any]:
    """Create a workflow run record via the MCP service"""
    return await _call_tool(
        "create_workflow_run",
        {
            "customer_id": customer_id,
            "workflow_type": workflow_type,
            "correlation_id": correlation_id,
        },
    )


async def update_workflow_run(
    workflow_run_id: str,
    status: str,
    email_status: str | None = None,
    validation_errors: str | None = None,
) -> dict[str, Any]:
    """Update a workflow run record via the MCP service."""
    return await _call_tool(
        "update_workflow_run",
        {
            "workflow_run_id": workflow_run_id,
            "status": status,
            "email_status": email_status,
            "validation_errors": validation_errors,
        },
    )


async def send_email(
    recipient_email: str,
    recipient_name: str,
    subject: str,
    html_body: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Send an email via the MCP service."""
    return await _call_tool(
        "send_email",
        {
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "subject": subject,
            "html_body": html_body,
            "correlation_id": correlation_id,
        },
    )


async def escalate_manual_review(
    customer_id: str, correlation_id: str, reason: str, details: dict[str, Any]
) -> dict[str, Any]:
    """Escalate an email to manual review via the MCP service."""
    return await _call_tool(
        "escalate_manual_review",
        {
            "customer_id": customer_id,
            "correlation_id": correlation_id,
            "reason": reason,
            "details": details,
        },
    )
