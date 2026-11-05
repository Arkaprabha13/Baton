"""Shared state type for Baton LangGraph agents.

Defines the BatonState TypedDict used across all LangGraph nodes.
"""

from typing import TypedDict


class BatonState(TypedDict):
    """State dictionary passed between all LangGraph agent nodes.

    Attributes:
        lead_id: Unique identifier for the lead.
        raw_data: Raw scraped data from the Maps Scraper.
        cleaned_data: Normalized and deduplicated lead data.
        enriched_data: Enriched data from LinkedIn or other sources.
        score: Qualification score (0-100).
        stage: Current pipeline stage (raw, cleaned, enriched, qualified, lost, negotiating, converted).
        messages: Conversation history for the negotiation.
        quotation_id: ID of the quotation if created.
        approval_status: HITL approval status (pending, approved, rejected).
        errors: List of error messages encountered during processing.
    """
    lead_id: str
    raw_data: dict
    cleaned_data: dict
    enriched_data: dict
    score: float
    stage: str
    messages: list[dict]
    quotation_id: str | None
    approval_status: str | None  # pending | approved | rejected
    errors: list[str]