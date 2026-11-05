"""Qualifier agent for Baton.

Scores the lead 0-100 using Groq (fast). Writes score back to leads.score.
Transitions enriched → qualified (score >= 60) or enriched → lost (score < 60).
"""

import json
from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat

QUALIFICATION_THRESHOLD: float = 60.0

SCORING_PROMPT = """You are a lead qualification expert. Score this lead from 0-100 based on the enrichment data.

Enrichment Data:
{enrichment_data}

Consider these factors:
- Company size (larger = higher score)
- Growth signals (hiring, funding = higher score)
- Decision maker accessibility (clear roles = higher score)
- Tech stack relevance (modern stack = higher score)
- Recent activity (active = higher score)

Return ONLY a single number (float) between 0 and 100. No extra text, no markdown."""


async def score_lead(enriched_data: dict[str, Any]) -> float:
    """Call core.llm.chat(model='groq') with scoring rubric; parse float from response.

    Args:
        enriched_data: Enriched lead data from the enricher.

    Returns:
        Score as a float between 0 and 100.
    """
    prompt = SCORING_PROMPT.format(enrichment_data=json.dumps(enriched_data, indent=2))
    messages = [{"role": "user", "content": prompt}]

    response = await chat(messages=messages, model="groq", temperature=0.1, max_tokens=10)

    # Parse float from response
    try:
        score = float(response.strip())
        return max(0.0, min(100.0, score))  # Clamp to 0-100
    except ValueError:
        # Default to 0 if parsing fails
        return 0.0


async def persist_score(lead_id: str, score: float) -> None:
    """Update lead score in the database.

    Args:
        lead_id: The lead identifier.
        score: Qualification score (0-100).
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            UPDATE leads SET score = %s, updated_at = NOW() WHERE id = %s
            """,
            (score, lead_id),
        )


async def qualifier_node(state: BatonState) -> BatonState:
    """Score lead, persist score, set stage, return updated state.

    Args:
        state: Current BatonState with enriched_data populated.

    Returns:
        Updated BatonState with score and stage set to 'qualified' or 'lost'.
    """
    enriched = state.get("enriched_data", {})
    lead_id = state.get("lead_id", "")

    if not enriched:
        return {
            **state,
            "score": 0.0,
            "stage": "lost",
            "errors": state.get("errors", []) + ["No enriched_data to score"],
        }

    score = await score_lead(enriched)
    await persist_score(lead_id, score)

    next_stage = "qualified" if score >= QUALIFICATION_THRESHOLD else "lost"

    return {
        **state,
        "score": score,
        "stage": next_stage,
    }