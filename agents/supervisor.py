"""Supervisor agent for Baton.

Orchestrates routing between agent nodes based on state["stage"].
Decides next node or ends the graph.
"""

from typing import Literal

from agents.state import BatonState
from langgraph.graph import END

# Node names
CLEANER = "cleaner"
ENRICHER = "enricher"
QUALIFIER = "qualifier"
NEGOTIATOR = "negotiator"
REPORTER = "reporter"


def route(state: BatonState) -> Literal["cleaner", "enricher", "qualifier", "negotiator", "reporter", "__end__"]:
    """Return the name of the next node based on current stage.

    Args:
        state: Current BatonState.

    Returns:
        Next node name or END.
    """
    stage = state.get("stage", "")

    if stage == "raw":
        return "cleaner"
    elif stage == "cleaned":
        return "enricher"
    elif stage == "enriched":
        return "qualifier"
    elif stage == "qualified":
        return "negotiator"
    elif stage in ["quoted", "converted"]:
        return "reporter"
    elif stage == "lost":
        return "__end__"

    return "__end__"


async def supervisor_node(state: BatonState) -> BatonState:
    """LangGraph node: logs the routing decision, may call core.llm.chat() for edge-case reasoning.

    Args:
        state: Current BatonState.

    Returns:
        Updated BatonState (unchanged, just passes through).
    """
    next_node = route(state)
    # Log routing decision to messages
    messages = state.get("messages", [])
    messages.append({"role": "system", "content": f"Supervisor routing: {state.get('stage', 'raw')} -> {next_node}"})

    return {
        **state,
        "messages": messages,
    }