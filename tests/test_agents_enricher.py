"""Unit tests for agents.enricher module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.enricher import fetch_linkedin_data, persist_enrichment, enricher_node


@pytest.mark.asyncio
async def test_fetch_linkedin_data_calls_llm_and_parses_json():
    """Test that fetch_linkedin_data calls LLM and parses JSON response."""
    mock_enrichment = {
        "employee_count_estimate": "51-200",
        "growth_signals": ["hiring", "recent_funding"],
        "decision_makers": ["CEO", "CTO", "VP Sales"],
        "tech_stack_hints": ["Python", "React", "AWS"],
        "recent_activity": "Posted about new product launch",
    }

    with patch("agents.enricher.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = str(mock_enrichment).replace("'", '"')

        result = await fetch_linkedin_data("John Doe", "Acme Corp")

        assert result == mock_enrichment
        mock_chat.assert_awaited_once()
        call_args = mock_chat.call_args
        assert call_args[1]["model"] == "nemotron"
        assert call_args[1]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_fetch_linkedin_data_handles_invalid_json():
    """Test that fetch_linkedin_data handles invalid JSON gracefully."""
    with patch("agents.enricher.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "This is not valid JSON"

        result = await fetch_linkedin_data("John Doe", "Acme Corp")

        assert result["employee_count_estimate"] == "unknown"
        assert result["growth_signals"] == []
        assert result["recent_activity"] == "Could not parse enrichment response"


@pytest.mark.asyncio
async def test_persist_enrichment_calls_db():
    """Test that persist_enrichment inserts into lead_enrichment."""
    with patch("agents.enricher.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await persist_enrichment("lead-123", "linkedin", {"key": "value"})

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO lead_enrichment" in call_args[0][0]
        assert call_args[0][1][0] == "lead-123"
        assert call_args[0][1][1] == "linkedin"
        assert '"key": "value"' in call_args[0][1][2]


@pytest.mark.asyncio
async def test_enricher_node_fetches_and_persists_enrichment():
    """Test that enricher_node fetches enrichment and updates stage."""
    with patch("agents.enricher.fetch_linkedin_data", new_callable=AsyncMock) as mock_fetch:
        with patch("agents.enricher.persist_enrichment", new_callable=AsyncMock) as mock_persist:
            mock_fetch.return_value = {
                "employee_count_estimate": "11-50",
                "growth_signals": ["hiring"],
                "decision_makers": ["CEO"],
                "tech_stack_hints": ["Python"],
                "recent_activity": "Active",
            }

            state = {
                "lead_id": "lead-123",
                "raw_data": {},
                "cleaned_data": {"name": "Acme Corp"},
                "enriched_data": {},
                "score": 0.0,
                "stage": "cleaned",
                "messages": [],
                "quotation_id": None,
                "approval_status": None,
                "errors": [],
            }

            result = await enricher_node(state)

            assert result["stage"] == "enriched"
            assert result["enriched_data"]["employee_count_estimate"] == "11-50"
            assert result["enriched_data"]["growth_signals"] == ["hiring"]
            mock_fetch.assert_awaited_once_with("Acme Corp", "Acme Corp")
            mock_persist.assert_awaited_once_with("lead-123", "linkedin", mock_fetch.return_value)


@pytest.mark.asyncio
async def test_enricher_node_handles_empty_cleaned_data():
    """Test that enricher_node handles missing name gracefully."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {},
        "cleaned_data": {},
        "enriched_data": {},
        "score": 0.0,
        "stage": "cleaned",
        "messages": [],
        "quotation_id": None,
        "approval_status": None,
        "errors": [],
    }

    result = await enricher_node(state)

    assert result["stage"] == "enriched"
    assert result["enriched_data"] == {}
    assert "No name in cleaned_data for enrichment" in result["errors"]