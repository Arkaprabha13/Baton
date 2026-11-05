"""Enricher agent for Baton.

Augments cleaned leads with LinkedIn data or other enrichment sources.
Writes to lead_enrichment. Transitions stage cleaned → enriched.
"""

import json
from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat


ENRICHMENT_PROMPT = """You are a lead enrichment specialist. Given a business name and company, provide a JSON summary of publicly available LinkedIn signals.

Business: {name}
Company: {company}

Return a JSON object with these fields:
- employee_count_estimate: string (e.g., "11-50", "51-200")
- growth_signals: list of strings (e.g., ["hiring", "recent_funding"])
- decision_makers: list of strings (likely roles like "CEO", "CTO", "VP Sales")
- tech_stack_hints: list of strings
- recent_activity: string (brief summary)

Only return valid JSON. No markdown, no extra text."""


async def fetch_linkedin_data(name: str, company: str) -> dict[str, Any]:
    """Use Nemotron (long context) to summarise publicly available LinkedIn signals via web search context.

    Args:
        name: Business/contact name.
        company: Company name.

    Returns:
        Dictionary with enrichment data.
    """
    prompt = ENRICHMENT_PROMPT.format(name=name, company=company)
    messages = [{"role": "user", "content": prompt}]

    response = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.2)

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        # Fallback if LLM doesn't return valid JSON
        return {
            "employee_count_estimate": "unknown",
            "growth_signals": [],
            "decision_makers": [],
            "tech_stack_hints": [],
            "recent_activity": "Could not parse enrichment response",
        }


async def persist_enrichment(lead_id: str, enrichment_type: str, payload: dict[str, Any]) -> None:
    """INSERT into lead_enrichment via get_conn().

    Args:
        lead_id: The lead identifier.
        enrichment_type: Type of enrichment (e.g., 'linkedin', 'web_search').
        payload: Enrichment data to store.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO lead_enrichment (lead_id, enrichment_type, payload, created_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (lead_id, enrichment_type) DO UPDATE SET
                payload = EXCLUDED.payload,
                created_at = NOW()
            """,
            (lead_id, enrichment_type, json.dumps(payload)),
        )


async def enricher_node(state: BatonState) -> BatonState:
    """Call enrichment APIs, persist to lead_enrichment, return updated state.

    Args:
        state: Current BatonState with cleaned_data populated.

    Returns:
        Updated BatonState with enriched_data and stage set to 'enriched'.
    """
    cleaned = state.get("cleaned_data", {})
    lead_id = state.get("lead_id", "")

    name = cleaned.get("name", "")
    company = cleaned.get("name", "")  # Using name as company for now

    if not name:
        return {
            **state,
            "stage": "enriched",
            "enriched_data": {},
            "errors": state.get("errors", []) + ["No name in cleaned_data for enrichment"],
        }

    # Fetch LinkedIn enrichment
    enrichment_data = await fetch_linkedin_data(name, company)

    # Persist enrichment
    await persist_enrichment(lead_id, "linkedin", enrichment_data)

    return {
        **state,
        "enriched_data": enrichment_data,
        "stage": "enriched",
    }