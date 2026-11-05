"""Gmail MCP adapter for Baton.

Thin async wrapper around the Gmail MCP server SSE endpoint.
Uses langchain-mcp-adapters to call send_email and search_emails tools.
"""

from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from core.config import settings


_mcp_client: MultiServerMCPClient | None = None


async def _get_mcp_client() -> MultiServerMCPClient:
    """Return a cached MultiServerMCPClient connected to gmail_mcp_url/sse.

    Returns:
        A MultiServerMCPClient instance connected to the Gmail MCP server.
    """
    global _mcp_client
    if _mcp_client is not None:
        return _mcp_client

    _mcp_client = MultiServerMCPClient(
        {
            "gmail": {
                "transport": "sse",
                "url": f"{settings.gmail_mcp_url}/sse",
            }
        }
    )
    return _mcp_client


async def send_email(to: str, subject: str, body: str) -> dict[str, Any]:
    """Call the MCP send_email tool; return the tool response dict.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body: Email body content.

    Returns:
        The tool response dictionary from the MCP server.
    """
    client = await _get_mcp_client()
    tools = await client.get_tools()

    send_email_tool = next((t for t in tools if t.name == "send_email"), None)
    if send_email_tool is None:
        raise RuntimeError("send_email tool not found on MCP server")

    result = await send_email_tool.ainvoke(
        {"to": to, "subject": subject, "body": body}
    )
    return result if isinstance(result, dict) else {"result": result}


async def search_emails(query: str, max_results: int = 20) -> list[dict[str, Any]]:
    """Call the MCP search_emails tool; return list of email dicts.

    Args:
        query: Gmail search query (e.g., "from:boss@corp.com").
        max_results: Maximum number of emails to return.

    Returns:
        List of email dictionaries from the search results.
    """
    client = await _get_mcp_client()
    tools = await client.get_tools()

    search_tool = next((t for t in tools if t.name == "search_emails"), None)
    if search_tool is None:
        raise RuntimeError("search_emails tool not found on MCP server")

    result = await search_tool.ainvoke(
        {"query": query, "max_results": max_results}
    )
    return result if isinstance(result, list) else [result]