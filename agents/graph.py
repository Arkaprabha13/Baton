"""LangGraph assembly for Baton.

Assembles the LangGraph StateGraph, adds all nodes, connects edges
based on the Supervisor routing, and compiles it using AsyncPostgresSaver.
"""

from typing import Literal

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from agents.state import BatonState
from agents.cleaner import cleaner_node
from agents.enricher import enricher_node
from agents.qualifier import qualifier_node
from agents.negotiation import negotiation_node
from agents.reporter import reporter_node
from agents.supervisor import route, supervisor_node

# Node names
CLEANER = "cleaner"
ENRICHER = "enricher"
QUALIFIER = "qualifier"
NEGOTIATOR = "negotiator"
REPORTER = "reporter"
SUPERVISOR = "supervisor"


def build_graph(checkpointer: AsyncPostgresSaver | None = None) -> StateGraph:
    """Build and compile the LangGraph StateGraph.

    Args:
        checkpointer: Optional AsyncPostgresSaver for persistence.

    Returns:
        Compiled StateGraph ready for invocation.
    """
    graph = StateGraph(BatonState)

    # Add all agent nodes
    graph.add_node(CLEANER, cleaner_node)
    graph.add_node(ENRICHER, enricher_node)
    graph.add_node(QUALIFIER, qualifier_node)
    graph.add_node(NEGOTIATOR, negotiation_node)
    graph.add_node(REPORTER, reporter_node)
    graph.add_node(SUPERVISOR, supervisor_node)

    # Set entry point to supervisor
    graph.set_entry_point(SUPERVISOR)

    # Supervisor routes to the appropriate agent
    graph.add_conditional_edges(
        SUPERVISOR,
        route,
        {
            CLEANER: CLEANER,
            ENRICHER: ENRICHER,
            QUALIFIER: QUALIFIER,
            NEGOTIATOR: NEGOTIATOR,
            REPORTER: REPORTER,
            "__end__": END,
        },
    )

    # After each agent, return to supervisor for next routing decision
    graph.add_edge(CLEANER, SUPERVISOR)
    graph.add_edge(ENRICHER, SUPERVISOR)
    graph.add_edge(QUALIFIER, SUPERVISOR)
    graph.add_edge(NEGOTIATOR, SUPERVISOR)
    graph.add_edge(REPORTER, END)

    # Compile with checkpointer if provided
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


async def create_checkpointer(dsn: str) -> AsyncPostgresSaver:
    """Create an AsyncPostgresSaver connected to the database.

    Args:
        dsn: PostgreSQL connection string.

    Returns:
        Connected AsyncPostgresSaver instance.
    """
    checkpointer = AsyncPostgresSaver(dsn)
    await checkpointer.setup()
    return checkpointer


async def run_graph(
    initial_state: BatonState,
    dsn: str | None = None,
    config: dict | None = None,
) -> BatonState:
    """Run the compiled graph with the given initial state.

    Args:
        initial_state: Starting BatonState.
        dsn: Optional database DSN for checkpointer.
        config: Optional LangGraph config.

    Returns:
        Final BatonState after graph execution.
    """
    checkpointer = None
    if dsn:
        checkpointer = await create_checkpointer(dsn)

    graph = build_graph(checkpointer)

    if config is None:
        config = {"configurable": {"thread_id": initial_state.get("lead_id", "default")}}

    result = await graph.ainvoke(initial_state, config=config)
    return result