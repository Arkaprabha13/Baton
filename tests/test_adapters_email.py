"""Unit tests for adapters.email module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.email import send_email, search_emails, _get_mcp_client


@pytest.fixture(autouse=True)
def reset_mcp_client():
    """Reset the global MCP client before each test."""
    import adapters.email as email_module
    email_module._mcp_client = None


async def test_get_mcp_client_creates_and_caches():
    """Test that _get_mcp_client creates and caches the client."""
    with patch("adapters.email.MultiServerMCPClient") as mock_client_class:
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_client_class.return_value = mock_client

        # First call creates client
        client1 = await _get_mcp_client()
        assert client1 is mock_client
        mock_client_class.assert_called_once()

        # Second call returns cached client
        client2 = await _get_mcp_client()
        assert client2 is mock_client
        assert mock_client_class.call_count == 1


async def test_send_email_calls_ainvoke_with_correct_tool():
    """Test that send_email calls the send_email tool via ainvoke."""
    with patch("adapters.email._get_mcp_client", new_callable=AsyncMock) as mock_get_client:
        mock_client = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "send_email"
        mock_tool.ainvoke = AsyncMock(return_value={"status": "sent", "message_id": "msg123"})
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])
        mock_get_client.return_value = mock_client

        result = await send_email("a@b.com", "Hi", "Body")

        mock_tool.ainvoke.assert_awaited_once_with(
            {"to": "a@b.com", "subject": "Hi", "body": "Body"}
        )
        assert result == {"status": "sent", "message_id": "msg123"}


async def test_send_email_raises_when_tool_not_found():
    """Test that send_email raises when send_email tool is not found."""
    with patch("adapters.email._get_mcp_client", new_callable=AsyncMock) as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[])  # No tools
        mock_get_client.return_value = mock_client

        with pytest.raises(RuntimeError, match="send_email tool not found"):
            await send_email("a@b.com", "Hi", "Body")


async def test_search_emails_calls_ainvoke_with_correct_tool():
    """Test that search_emails calls the search_emails tool via ainvoke."""
    with patch("adapters.email._get_mcp_client", new_callable=AsyncMock) as mock_get_client:
        mock_client = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_emails"
        mock_tool.ainvoke = AsyncMock(
            return_value=[
                {"id": "1", "from": "boss@corp.com", "subject": "Meeting"},
                {"id": "2", "from": "boss@corp.com", "subject": "Follow up"},
            ]
        )
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])
        mock_get_client.return_value = mock_client

        result = await search_emails("from:boss@corp.com", max_results=20)

        mock_tool.ainvoke.assert_awaited_once_with(
            {"query": "from:boss@corp.com", "max_results": 20}
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["from"] == "boss@corp.com"


async def test_search_emails_raises_when_tool_not_found():
    """Test that search_emails raises when search_emails tool is not found."""
    with patch("adapters.email._get_mcp_client", new_callable=AsyncMock) as mock_get_client:
        mock_client = MagicMock()
        mock_client.get_tools = AsyncMock(return_value=[])  # No tools
        mock_get_client.return_value = mock_client

        with pytest.raises(RuntimeError, match="search_emails tool not found"):
            await search_emails("from:boss@corp.com")


async def test_search_emails_returns_list_even_for_single_result():
    """Test that search_emails always returns a list."""
    with patch("adapters.email._get_mcp_client", new_callable=AsyncMock) as mock_get_client:
        mock_client = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "search_emails"
        # Tool returns a single dict, not a list
        mock_tool.ainvoke = AsyncMock(return_value={"id": "1", "subject": "Single"})
        mock_client.get_tools = AsyncMock(return_value=[mock_tool])
        mock_get_client.return_value = mock_client

        result = await search_emails("test")

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["subject"] == "Single"