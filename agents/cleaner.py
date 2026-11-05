"""Cleaner agent for Baton.

Deduplicates and normalises raw scraped lead data. Writes cleaned lead to DB
(upsert on dedupe_key). Transitions stage raw → cleaned.
"""

import hashlib
import re
from typing import Any

from agents.state import BatonState
from core.db import get_conn


FIELD_ALIASES = {
    "email": ["email", "e-mail", "mail", "email_address"],
    "phone": ["phone", "telephone", "mobile", "cell", "phone_number"],
    "name": ["name", "business_name", "company_name", "title"],
    "address": ["address", "street", "location", "full_address"],
    "website": ["website", "url", "web", "site"],
    "category": ["category", "type", "business_type", "industry"],
}


def normalise(raw: dict[str, Any]) -> dict[str, Any]:
    """Pure function: lowercase emails, strip whitespace, map field aliases.

    Args:
        raw: Raw lead data with potentially inconsistent field names and formatting.

    Returns:
        Normalized dictionary with standardized keys and cleaned values.
    """
    normalised: dict[str, Any] = {}

    for key, value in raw.items():
        if value is None:
            continue

        # Strip whitespace from strings
        if isinstance(value, str):
            value = value.strip()

        # Find canonical field name
        canonical_key = None
        lower_key = key.lower()
        for canonical, aliases in FIELD_ALIASES.items():
            if lower_key in [a.lower() for a in aliases]:
                canonical_key = canonical
                break

        if canonical_key is None:
            canonical_key = lower_key

        # Special handling for email - lowercase it
        if canonical_key == "email" and isinstance(value, str):
            value = value.lower()

        # Special handling for phone - strip non-digits except +
        if canonical_key == "phone" and isinstance(value, str):
            value = re.sub(r"[^\d+]", "", value)

        normalised[canonical_key] = value

    return normalised


def compute_dedupe_key(normalised: dict[str, Any]) -> str:
    """Return SHA-256 hex of (email|phone|business_name+address).

    Args:
        normalised: Normalized lead data.

    Returns:
        64-character hexadecimal SHA-256 hash string.
    """
    # Build dedupe string from available identifiers
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
    """Upsert cleaned lead into the database.

    Args:
        lead_id: Unique lead identifier.
        dedupe_key: SHA-256 deduplication key.
        normalised: Normalized lead data.
        raw_data: Original raw data.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO leads (id, dedupe_key, email, phone, name, address, website, category, raw_data, stage, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'cleaned', NOW())
            ON CONFLICT (id) DO UPDATE SET
                dedupe_key = EXCLUDED.dedupe_key,
                email = EXCLUDED.email,
                phone = EXCLUDED.phone,
                name = EXCLUDED.name,
                address = EXCLUDED.address,
                website = EXCLUDED.website,
                category = EXCLUDED.category,
                raw_data = EXCLUDED.raw_data,
                stage = 'cleaned',
                updated_at = NOW()
            """,
            (
                lead_id,
                dedupe_key,
                normalised.get("email"),
                normalised.get("phone"),
                normalised.get("name"),
                normalised.get("address"),
                normalised.get("website"),
                normalised.get("category"),
                raw_data,
            ),
        )


async def cleaner_node(state: BatonState) -> BatonState:
    """Normalise raw_data, compute dedupe_key, upsert leads table, return updated state.

    Args:
        state: Current BatonState with raw_data populated.

    Returns:
        Updated BatonState with cleaned_data, dedupe_key in stage, and stage set to 'cleaned'.
    """
    raw = state.get("raw_data", {})
    lead_id = state.get("lead_id", "")

    if not raw:
        return {**state, "stage": "cleaned", "errors": state.get("errors", []) + ["No raw_data to clean"]}

    normalised = normalise(raw)
    dedupe_key = compute_dedupe_key(normalised)

    await persist_cleaned_lead(lead_id, dedupe_key, normalised, raw)

    return {
        **state,
        "cleaned_data": normalised,
        "stage": "cleaned",
    }