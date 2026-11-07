"""Enricher agent for Baton."""
import json
from typing import Any
from psycopg.types.json import Jsonb
from agents.state import BatonState
from core.db import get_conn
from core.llm import chat

async def fetch_linkedin_data(name: str, company: str) -> dict[str, Any]:
    if not name and not company:
        return {}

    target = f"{name} ({company})" if name and company else (name or company)

    messages = [
        {
            "role": "system",
            "content": (
                "You are an expert agency sales researcher. Analyze this B2B or B2C business. "
                "Find digital marketing gaps (e.g., poor SEO, outdated website, lack of online booking, "
                "missing B2B lead gen funnels, weak social media). "
                "Return a JSON object with keys: 'tech_stack' (list), "
                "'pain_points' (list), and 'summary' (string). "
                "Do not include markdown formatting, just raw JSON."
            ),
        },
        {"role": "user", "content": f"Analyze this business: {target}"},
    ]

    try:
        response = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.2)
        clean_json = response.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"   ⚠️ [Enricher] Failed for {target}: {e}")
        return {"error": str(e)}

async def persist_enrichment(lead_id: str, enrichment_type: str, payload: dict[str, Any]) -> None:
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO lead_enrichment (lead_id, enrichment_type, provider, payload, fetched_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (lead_id, enrichment_type, "nemotron", Jsonb(payload)),
        )

async def enricher_node(state: BatonState) -> BatonState:
    cleaned = state.get("cleaned_data", {})
    lead_id = state.get("lead_id", "")

    if not cleaned:
        return {**state, "stage": "enriched", "errors": state.get("errors", []) + ["No cleaned_data"]}

    name = cleaned.get("name", "Unknown")
    company = cleaned.get("category", "")
    
    print(f"   🔍 [Enricher] Researching {name} using NVIDIA...")
    enrichment_data = await fetch_linkedin_data(name, company)

    if enrichment_data:
        await persist_enrichment(lead_id, "ai_research", enrichment_data)

    return {**state, "enriched_data": enrichment_data, "stage": "enriched"}