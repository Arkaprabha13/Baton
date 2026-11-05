"""Unit tests for agents.supervisor module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.supervisor import route, supervisor_node, CLEANER, ENRICHER, QUALIFIER, NEGOTIATOR, REPORTER
from langgraph.graph import END


def test_route_raw_stage_returns_cleaner():
    """Test that route returns 'cleaner' for raw stage."""
    state = {"stage": "raw"}
    assert route(state) == CLEANER


def test_route_cleaned_stage_returns_enricher():
    """Test that route returns 'enricher' for cleaned stage."""
    state = {"stage": "cleaned"}
    assert route(state) == ENRICHER


def test_route_enriched_stage_returns_qualifier():
    """Test that route returns 'qualifier' for enriched stage."""
    state = {"stage": "enriched"}
    assert route(state) == QUALIFIER


def test_route_qualified_stage_returns_negotiator():
    """Test that route returns 'negotiator' for qualified stage."""
    state = {"stage": "qualified"}
    assert route(state) == NEGOTIATOR


def test_route_negotiating_stage_returns_negotiator():
    """Test that route returns 'negotiator' for negotiating stage."""
    state = {"stage": "negotiating"}
    assert route(state) == NEGOTIATOR


def test_route_lost_stage_returns_end():
    """Test that route returns END for lost stage."""
    state = {"stage": "lost"}
    assert route(state) == END


def test_route_converted_stage_returns_reporter():
    """Test that route returns 'reporter' for converted stage."""
    state = {"stage": "converted"}
    assert route(state) == REPORTER


def test_route_unknown_stage_returns_end():
    """Test that route returns END for unknown stage."""
    state = {"stage": "unknown"}
    assert route(state) == END


def test_route_missing_stage_defaults_to_cleaner():
    """Test that route defaults to cleaner when stage is missing (starts from beginning)."""
    state = {}
    assert route(state) == CLEANER


@pytest.mark.asyncio
async def test_supervisor_node_logs_routing_decision():
    """Test that supervisor_node adds routing log to messages."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {},
        "cleaned_data": {},
        "enriched_data": {},
        "score": 0.0,
        "stage": "raw",
        "messages": [],
        "quotation_id": None,
        "approval_status": None,
        "errors": [],
    }

    result = await supervisor_node(state)

    assert len(result["messages"]) == 1
    assert "Supervisor routing: raw -> cleaner" in result["messages"][0]["content"]
    assert result["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_supervisor_node_preserves_state():
    """Test that supervisor_node preserves all state fields."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {"name": "Test"},
        "cleaned_data": {"name": "Test"},
        "enriched_data": {"score": 80},
        "score": 80.0,
        "stage": "qualified",
        "messages": [{"role": "user", "content": "Hello"}],
        "quotation_id": "quote-123",
        "approval_status": "pending",
        "errors": [],
    }

    result = await supervisor_node(state)

    assert result["lead_id"] == "lead-123"
    assert result["raw_data"] == {"name": "Test"}
    assert result["cleaned_data"] == {"name": "Test"}
    assert result["enriched_data"] == {"score": 80}
    assert result["score"] == 80.0
    assert result["stage"] == "qualified"
    assert result["quotation_id"] == "quote-123"
    assert result["approval_status"] == "pending"
    assert result["errors"] == []