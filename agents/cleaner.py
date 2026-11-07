"""Cleaner agent for Baton.

Deduplicates and normalises raw scraped lead data. Writes cleaned lead to DB
(upsert on dedupe_key). Transitions stage raw → cleaned.
"""
import hashlib
import re
from typing import Any

from psycopg.types.json import Jsonb

from agents.state import BatonState
from core.db import get_conn


FIELD_ALIASES = {
    # FIXED: Added "emails" and "phones" (plural) for Google Maps
    "email": ["email", "emails", "e-mail", "mail", "email_address"],
    "phone": ["phone", "phones", "telephone", "mobile", "cell", "phone_number"],
    "name": ["name", "title", "business_name", "company_name"],
    "address": ["address", "street", "location", "full_address"],
    "website": ["website", "url", "web", "site"],
    "category": ["category", "type", "business_type", "industry"],
}


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Pure function: lowercase emails, strip whitespace, map field aliases."""
    normalised: dict[str, Any] = {}

    for key, value in raw.items():
        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()

        canonical_key = None
        lower_key = key.lower()
        for canonical, aliases in FIELD_ALIASES.items():
            if lower_key in [a.lower() for a in aliases]:
                canonical_key = canonical
                break

        if canonical_key is None:
            canonical_key = lower_key

        if canonical_key == "email" and isinstance(value, str):
            value = value.lower()

        if canonical_key == "phone" and isinstance(value, str):
            value = re.sub(r"[^\d+]", "", value)

        normalised[canonical_key] = value

    return normalised


def compute_dedupe_key(normalised: dict[str, Any]) -> str:
    """Return SHA-256 hex of (email|phone|business_name+address)."""
    parts = []

    if normalised.get("email"):
        parts.append(f"email:{normalised['email']}")
    if normalised.get("phone"):
        parts.append(f"phone:{normalised['phone']}")
    if normalised.get("name") and normalised.get("address"):
        parts.append(f"name_addr:{normalised['name']}|{normalised['address']}")
    elif normalised.get("name"):
        parts.append(f"name:{normalised['name']}")

    dedupe_string = "|".join(parts) if parts else "unknown"
    return hashlib.sha256(dedupe_string.encode()).hexdigest()


async def persist_cleaned_lead(
    lead_id: str,
    dedupe_key: str,
    normalised: dict[str, Any],
    raw_data: dict[str, Any],
) -> None:
    """Update cleaned lead in the database."""
    async with get_conn() as conn:
        # FIXED: Changed from INSERT to UPDATE to avoid primary key conflicts
        await conn.execute(
            """
            UPDATE leads 
            SET 
                dedupe_key = %s,
                raw_data = %s,
                metadata = %s,
                stage = 'cleaned',
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                dedupe_key,
                Jsonb(raw_data),
                Jsonb(normalised),
                lead_id,
            ),
        )


async def cleaner_node(state: BatonState) -> BatonState:
    """Normalise raw_data, compute dedupe_key, upsert leads table."""
    raw = state.get("raw_data", {})
    lead_id = state.get("lead_id", "")

    if not raw:
        return {**state, "stage": "cleaned", "errors": state.get("errors", []) + ["No raw_data to clean"]}

    normalised = normalise(raw)
    dedupe_key = compute_dedupe_key(normalised)
    
    print(f"   🧹 [Cleaner] Normalized lead: {normalised.get('name', 'Unknown')}")
    
    await persist_cleaned_lead(lead_id, dedupe_key, normalised, raw)

    return {
        **state,
        "cleaned_data": normalised,
        "stage": "cleaned",
    }