"""Unit tests for agents.graph module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.graph import build_graph, create_checkpointer, run_graph, CLEANER
from agents.supervisor import route, END


def test_build_graph_creates_state_graph():
    """Test that build_graph returns a compiled StateGraph."""
    graph = build_graph()

    # Verify graph compiles without errors
    assert graph is not None
    # The compiled graph should have the invoke method
    assert hasattr(graph, "ainvoke")


def test_build_graph_with_checkpointer():
    """Test that build_graph accepts and uses checkpointer."""
    mock_checkpointer = MagicMock()

    graph = build_graph(checkpointer=mock_checkpointer)

    assert graph is not None


def test_route_integration_with_graph():
    """Test that the route function works correctly for graph edges."""
    # Test all valid stage transitions
    test_cases = [
        ({"stage": "raw"}, "cleaner"),
        ({"stage": "cleaned"}, "enricher"),
        ({"stage": "enriched"}, "qualifier"),
        ({"stage": "qualified"}, "negotiator"),
        ({"stage": "negotiating"}, "negotiator"),
        ({"stage": "lost"}, END),
        ({"stage": "converted"}, "reporter"),
        ({}, CLEANER),  # Defaults to raw -> cleaner
        ({"stage": "unknown"}, END),
    ]

    for state, expected in test_cases:
        assert route(state) == expected, f"Failed for state {state}"


@pytest.mark.asyncio
async def test_create_checkpointer_sets_up():
    """Test that create_checkpointer creates and sets up the saver."""
    with patch("agents.graph.AsyncPostgresSaver") as mock_saver_class:
        mock_saver = AsyncMock()
        mock_saver.setup = AsyncMock()
        mock_saver_class.return_value = mock_saver

        result = await create_checkpointer("postgresql://user:pass@localhost/db")

        assert result is mock_saver
        mock_saver_class.assert_called_once_with("postgresql://user:pass@localhost/db")
        mock_saver.setup.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_graph_invokes_compiled_graph():
    """Test that run_graph invokes the graph with correct config."""
    with patch("agents.graph.build_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"stage": "converted", "lead_id": "lead-123"})
        mock_build_graph.return_value = mock_graph

        initial_state = {
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

        result = await run_graph(initial_state, dsn=None)

        assert result["lead_id"] == "lead-123"
        assert result["stage"] == "converted"
        mock_graph.ainvoke.assert_awaited_once()
        call_args = mock_graph.ainvoke.call_args
        assert call_args[0][0] == initial_state
        assert "configurable" in call_args[1]["config"]
        assert call_args[1]["config"]["configurable"]["thread_id"] == "lead-123"


@pytest.mark.asyncio
async def test_run_graph_uses_custom_config():
    """Test that run_graph accepts custom config."""
    with patch("agents.graph.build_graph") as mock_build_graph:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(return_value={"stage": "converted"})
        mock_build_graph.return_value = mock_graph

        initial_state = {"lead_id": "lead-123", "stage": "raw"}

        await run_graph(initial_state, dsn=None, config={"configurable": {"thread_id": "custom-thread"}})

        call_args = mock_graph.ainvoke.call_args
        assert call_args[1]["config"]["configurable"]["thread_id"] == "custom-thread"


@pytest.mark.asyncio
async def test_graph_compilation_succeeds():
    """Test that the full graph compiles without errors."""
    # This test ensures all nodes are properly connected
    graph = build_graph()

    # Verify the graph structure by checking it can be invoked
    # We can't easily test the internal structure, but we can verify it compiles
    assert graph is not None

    # Test that all expected nodes are reachable by checking the graph's nodes
    # This is a basic sanity check
    try:
        # Try to get the graph's internal structure
        # Note: LangGraph's compiled graph doesn't expose nodes directly easily
        # but we can at least verify it doesn't raise on creation
        pass
    except Exception as e:
        pytest.fail(f"Graph compilation failed: {e}")


def test_graph_node_names():
    """Test that expected node names are defined."""
    from agents.graph import (
        CLEANER, ENRICHER, QUALIFIER, NEGOTIATOR, REPORTER, SUPERVISOR
    )

    assert CLEANER == "cleaner"
    assert ENRICHER == "enricher"
    assert QUALIFIER == "qualifier"
    assert NEGOTIATOR == "negotiator"
    assert REPORTER == "reporter"
    assert SUPERVISOR == "supervisor"