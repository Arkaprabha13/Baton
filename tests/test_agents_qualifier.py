"""Unit tests for agents.qualifier module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.qualifier import QUALIFICATION_THRESHOLD, score_lead, persist_score, qualifier_node


@pytest.mark.asyncio
async def test_score_lead_calls_groq_and_parses_float():
    """Test that score_lead calls Groq and parses the float response."""
    with patch("agents.qualifier.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "72.5"

        enriched_data = {
            "employee_count_estimate": "51-200",
            "growth_signals": ["hiring"],
            "decision_makers": ["CEO", "CTO"],
            "tech_stack_hints": ["Python", "AWS"],
            "recent_activity": "Active",
        }

        score = await score_lead(enriched_data)

        assert score == 72.5
        mock_chat.assert_awaited_once()
        call_args = mock_chat.call_args
        assert call_args[1]["model"] == "groq"
        assert call_args[1]["temperature"] == 0.1
        assert call_args[1]["max_tokens"] == 10


@pytest.mark.asyncio
async def test_score_lead_clamps_to_100():
    """Test that score_lead clamps scores above 100 to 100."""
    with patch("agents.qualifier.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "150"

        score = await score_lead({})

        assert score == 100.0


@pytest.mark.asyncio
async def test_score_lead_clamps_to_0():
    """Test that score_lead clamps negative scores to 0."""
    with patch("agents.qualifier.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "-10"

        score = await score_lead({})

        assert score == 0.0


@pytest.mark.asyncio
async def test_score_lead_handles_invalid_response():
    """Test that score_lead defaults to 0 on parse failure."""
    with patch("agents.qualifier.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "not a number"

        score = await score_lead({})

        assert score == 0.0


@pytest.mark.asyncio
async def test_persist_score_calls_db():
    """Test that persist_score updates the lead score."""
    with patch("agents.qualifier.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await persist_score("lead-123", 72.5)

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "UPDATE leads SET score" in call_args[0][0]
        assert call_args[0][1] == (72.5, "lead-123")


@pytest.mark.asyncio
async def test_qualifier_node_sets_qualified_stage():
    """Test that qualifier_node sets stage to qualified when score >= threshold."""
    with patch("agents.qualifier.score_lead", new_callable=AsyncMock) as mock_score:
        with patch("agents.qualifier.persist_score", new_callable=AsyncMock) as mock_persist:
            mock_score.return_value = 72.5

            state = {
                "lead_id": "lead-123",
                "raw_data": {},
                "cleaned_data": {},
                "enriched_data": {"employee_count_estimate": "51-200"},
                "score": 0.0,
                "stage": "enriched",
                "messages": [],
                "quotation_id": None,
                "approval_status": None,
                "errors": [],
            }

            result = await qualifier_node(state)

            assert result["score"] == 72.5
            assert result["stage"] == "qualified"
            mock_score.assert_awaited_once()
            mock_persist.assert_awaited_once_with("lead-123", 72.5)


@pytest.mark.asyncio
async def test_qualifier_node_sets_lost_stage():
    """Test that qualifier_node sets stage to lost when score < threshold."""
    with patch("agents.qualifier.score_lead", new_callable=AsyncMock) as mock_score:
        with patch("agents.qualifier.persist_score", new_callable=AsyncMock) as mock_persist:
            mock_score.return_value = 45.0

            state = {
                "lead_id": "lead-123",
                "raw_data": {},
                "cleaned_data": {},
                "enriched_data": {"employee_count_estimate": "1-10"},
                "score": 0.0,
                "stage": "enriched",
                "messages": [],
                "quotation_id": None,
                "approval_status": None,
                "errors": [],
            }

            result = await qualifier_node(state)

            assert result["score"] == 45.0
            assert result["stage"] == "lost"
            mock_persist.assert_awaited_once_with("lead-123", 45.0)


@pytest.mark.asyncio
async def test_qualifier_node_handles_empty_enriched_data():
    """Test that qualifier_node handles missing enriched_data gracefully."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {},
        "cleaned_data": {},
        "enriched_data": {},
        "score": 0.0,
        "stage": "enriched",
        "messages": [],
        "quotation_id": None,
        "approval_status": None,
        "errors": [],
    }

    result = await qualifier_node(state)

    assert result["score"] == 0.0
    assert result["stage"] == "lost"
    assert "No enriched_data to score" in result["errors"]