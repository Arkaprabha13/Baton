"""Unit tests for agents.reporter module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.reporter import generate_summary, persist_conversion, reporter_node


@pytest.mark.asyncio
async def test_generate_summary_calls_gemini():
    """Test that generate_summary calls Gemini with correct parameters."""
    with patch("agents.reporter.chat", new_callable=AsyncMock) as mock_chat:
        with patch("agents.reporter.get_conn") as mock_get_conn:
            mock_chat.return_value = "# Summary\nDeal closed successfully."

            # Mock quotation lookup
            mock_conn = AsyncMock()
            mock_cursor = AsyncMock()
            mock_cursor.fetchone = AsyncMock(return_value=["line_items_json", 5000.0])
            mock_conn.execute = AsyncMock(return_value=mock_cursor)
            mock_get_conn.return_value.__aenter__.return_value = mock_conn

            state = {
                "lead_id": "lead-123",
                "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there"},
                ],
                "quotation_id": "quote-123",
            }

            summary = await generate_summary(state)

            assert summary == "# Summary\nDeal closed successfully."
            mock_chat.assert_awaited_once()
            call_args = mock_chat.call_args
            assert call_args[1]["model"] == "gemini"
            assert call_args[1]["temperature"] == 0.3
            assert call_args[1]["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_persist_conversion_inserts_event():
    """Test that persist_conversion inserts into conversion_events."""
    with patch("agents.reporter.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await persist_conversion("lead-123", "quote-456", 5000.0)

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO conversion_events" in call_args[0][0]
        assert call_args[0][1] == ("lead-123", "quote-456", 5000.0)


@pytest.mark.asyncio
async def test_reporter_node_generates_summary_and_persists():
    """Test that reporter_node generates summary and updates stage to converted."""
    with patch("agents.reporter.generate_summary", new_callable=AsyncMock) as mock_summary:
        with patch("agents.reporter.persist_conversion", new_callable=AsyncMock) as mock_persist:
            with patch("agents.reporter.get_conn") as mock_get_conn:
                mock_summary.return_value = "# Summary\nDeal closed with Acme Corp."

                # Mock quotation value lookup
                mock_conn = AsyncMock()
                mock_cursor = AsyncMock()
                mock_cursor.fetchone = AsyncMock(return_value=[5000.0])
                mock_conn.execute = AsyncMock(return_value=mock_cursor)
                mock_get_conn.return_value.__aenter__.return_value = mock_conn

                state = {
                    "lead_id": "lead-123",
                    "raw_data": {},
                    "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
                    "enriched_data": {},
                    "score": 75.0,
                    "stage": "converted",
                    "messages": [
                        {"role": "user", "content": "Initial message"},
                    ],
                    "quotation_id": "quote-456",
                    "approval_status": "approved",
                    "errors": [],
                }

                result = await reporter_node(state)

                assert result["stage"] == "converted"
                assert len(result["messages"]) == 2  # Original + summary
                assert "Deal Summary" in result["messages"][1]["content"]
                mock_summary.assert_awaited_once()
                mock_persist.assert_awaited_once_with("lead-123", "quote-456", 5000.0)


@pytest.mark.asyncio
async def test_reporter_node_handles_missing_quotation():
    """Test that reporter_node handles missing quotation gracefully."""
    with patch("agents.reporter.generate_summary", new_callable=AsyncMock) as mock_summary:
        with patch("agents.reporter.persist_conversion", new_callable=AsyncMock) as mock_persist:
            with patch("agents.reporter.get_conn") as mock_get_conn:
                mock_summary.return_value = "# Summary\nDeal completed."
                mock_conn = AsyncMock()
                mock_cursor = AsyncMock()
                mock_cursor.fetchone = AsyncMock(return_value=None)
                mock_conn.execute = AsyncMock(return_value=mock_cursor)
                mock_get_conn.return_value.__aenter__.return_value = mock_conn

                state = {
                    "lead_id": "lead-123",
                    "raw_data": {},
                    "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
                    "enriched_data": {},
                    "score": 75.0,
                    "stage": "converted",
                    "messages": [],
                    "quotation_id": None,
                    "approval_status": "approved",
                    "errors": [],
                }

                result = await reporter_node(state)

                assert result["stage"] == "converted"
                mock_persist.assert_awaited_once_with("lead-123", None, 0.0)