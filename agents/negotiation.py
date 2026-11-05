"""Negotiation agent for Baton.

Runs the negotiation dialogue loop. Sends outreach email (via adapters.email),
monitors replies, generates counter-proposals using Nemotron, creates quotations
in DB. Flags for HITL approval when deal value exceeds threshold.
"""

import json
from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat
from adapters.email import send_email


HITL_VALUE_THRESHOLD: float = 5000.0  # USD


INITIAL_OUTREACH_PROMPT = """Write a personalized outreach email to a potential client.

Lead Info:
- Name: {name}
- Company: {company}
- Email: {email}
- Enriched Data: {enrichment}

Write a professional, concise email introducing our services and requesting a brief call.
Return ONLY the email body. No subject line, no markdown."""


PROPOSAL_PROMPT = """Generate a sales proposal for this qualified lead.

Lead Info:
- Name: {name}
- Company: {company}
- Enriched Data: {enrichment}
- Lead Score: {score}

Create a proposal with line items for our services. Return a JSON object with:
- line_items: list of {{"description": str, "quantity": int, "unit_price": float, "total": float}}
- total_value: float (sum of all line items)
- notes: str (any additional context)

Only return valid JSON. No markdown, no extra text."""


async def send_initial_outreach(lead_id: str, contact_email: str) -> str:
    """Generate personalised email via Nemotron, send via adapters.email, return gmail message_id.

    Args:
        lead_id: The lead identifier.
        contact_email: Recipient email address.

    Returns:
        Gmail message ID from the sent email.
    """
    # We'll get the lead details from the database
    async with get_conn() as conn:
        row = await conn.execute(
            "SELECT name, email, enriched_data FROM leads WHERE id = %s", (lead_id,)
        )
        lead = await row.fetchone()

    if not lead:
        raise ValueError(f"Lead {lead_id} not found")

    name = lead[0] or "there"
    company = lead[0] or "your company"
    enrichment = lead[2] or {}

    prompt = INITIAL_OUTREACH_PROMPT.format(
        name=name, company=company, email=contact_email, enrichment=json.dumps(enrichment)
    )
    messages = [{"role": "user", "content": prompt}]

    email_body = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.4)

    result = await send_email(to=contact_email, subject="Partnership Opportunity", body=email_body)

    return result.get("message_id", "unknown")


async def generate_proposal(state: BatonState) -> dict[str, Any]:
    """Return a quotation line_items dict using Nemotron reasoning.

    Args:
        state: Current BatonState with cleaned_data and enriched_data.

    Returns:
        Dictionary with line_items, total_value, and notes.
    """
    cleaned = state.get("cleaned_data", {})
    enriched = state.get("enriched_data", {})
    score = state.get("score", 0)

    name = cleaned.get("name", "Client")
    company = cleaned.get("name", "Client Company")

    prompt = PROPOSAL_PROMPT.format(
        name=name, company=company, enrichment=json.dumps(enriched), score=score
    )
    messages = [{"role": "user", "content": prompt}]

    response = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.3)

    try:
        proposal = json.loads(response)
        # Ensure total_value is float
        proposal["total_value"] = float(proposal.get("total_value", 0))
        return proposal
    except json.JSONDecodeError:
        # Fallback proposal
        return {
            "line_items": [
                {"description": "Standard Service Package", "quantity": 1, "unit_price": 2500.0, "total": 2500.0}
            ],
            "total_value": 2500.0,
            "notes": "Default proposal - LLM response parsing failed",
        }


async def create_quotation(lead_id: str, line_items: dict[str, Any]) -> str:
    """INSERT into quotations, return quotation_id.

    Args:
        lead_id: The lead identifier.
        line_items: Proposal line items dictionary.

    Returns:
        The created quotation ID.
    """
    import uuid

    quotation_id = str(uuid.uuid4())
    total_value = line_items.get("total_value", 0.0)

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO quotations (id, lead_id, line_items, total_value, status, created_at)
            VALUES (%s, %s, %s, %s, 'draft', NOW())
            """,
            (quotation_id, lead_id, json.dumps(line_items), total_value),
        )

    return quotation_id


async def request_hitl_approval(quotation_id: str) -> None:
    """INSERT into approvals with status='pending'; the HITL dashboard picks this up.

    Args:
        quotation_id: The quotation identifier.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO approvals (quotation_id, status, created_at)
            VALUES (%s, 'pending', NOW())
            """,
            (quotation_id,),
        )


async def negotiation_node(state: BatonState) -> BatonState:
    """Drive the negotiation loop; return updated state with quotation_id.

    Args:
        state: Current BatonState with stage='qualified'.

    Returns:
        Updated BatonState with quotation_id and stage='negotiating'.
    """
    lead_id = state.get("lead_id", "")
    cleaned = state.get("cleaned_data", {})
    contact_email = cleaned.get("email")

    if not contact_email:
        return {
            **state,
            "stage": "negotiating",
            "errors": state.get("errors", []) + ["No contact email for outreach"],
        }

    # Send initial outreach
    try:
        message_id = await send_initial_outreach(lead_id, contact_email)
        # Add to conversation history
        messages = state.get("messages", [])
        messages.append({"role": "assistant", "content": f"Initial outreach sent (msg_id: {message_id})"})
    except Exception as e:
        messages = state.get("messages", [])
        messages.append({"role": "assistant", "content": f"Outreach failed: {str(e)}"})

    # Generate proposal
    proposal = await generate_proposal(state)
    quotation_id = await create_quotation(lead_id, proposal)

    # Check if HITL approval needed
    total_value = proposal.get("total_value", 0.0)
    if total_value > HITL_VALUE_THRESHOLD:
        await request_hitl_approval(quotation_id)
        approval_status = "pending"
        messages = state.get("messages", [])
        messages.append({"role": "assistant", "content": f"Quotation {quotation_id} requires HITL approval (value: ${total_value})"})
    else:
        approval_status = "approved"
        messages = state.get("messages", [])
        messages.append({"role": "assistant", "content": f"Quotation {quotation_id} auto-approved (value: ${total_value})"})

    return {
        **state,
        "quotation_id": quotation_id,
        "approval_status": approval_status,
        "stage": "negotiating",
        "messages": messages,
    }