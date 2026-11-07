"""Negotiation agent for Baton.

Runs the negotiation dialogue loop. Sends outreach email (via adapters.email),
monitors replies, generates counter-proposals using Nemotron, creates quotations
in DB. Flags for HITL approval when deal value exceeds threshold.
"""

import json
import uuid
import os
from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat
# FIXED: Imported save_draft alongside send_email
from adapters.email import send_email, save_draft


HITL_VALUE_THRESHOLD: float = 5000.0  # USD

INITIAL_OUTREACH_PROMPT = """Write a personalized outreach email from a solo freelance web developer and AI automation specialist.

Business Info:
- Business Name: {business_name}
- Industry: {category}
- Research/Gaps: {enrichment}

Strict Rules:
1. Start with "Hi {business_name} team,".
2. Call out 1 or 2 specific digital gaps found in the research (e.g., no online booking, slow website, missing AI automations).
3. Pitch directly: Explain how a modern website or AI automation can solve their exact problem.
4. Use "I" instead of "we" (you are a solo freelancer, not an agency).
5. Keep it under 100 words. Be conversational and helpful, not pushy.
6. YOU MUST END THE EMAIL EXACTLY WITH THIS SIGNATURE. DO NOT USE ANY PLACEHOLDERS OR BRACKETS.

Best regards,
Arkaprabha Banerjee
Freelance Web Developer & AI Automation Specialist
https://www.arkaprabhabanerjee.tech/

Return ONLY the email body starting from "Hi". Do not include the subject line in the body."""

PROPOSAL_PROMPT = """Generate a sales proposal for this qualified lead.

Business Info:
- Business Name: {business_name}
- Research/Gaps: {enrichment}
- Lead Score: {score}

Create a proposal with line items for freelance web development and AI automation services.
IMPORTANT: As a freelancer, keep the pricing realistic for small-to-medium businesses. The total amount should NOT exceed $4,500.

Return a JSON object with:
- line_items: list of {{"description": str, "quantity": int, "unit_price": float, "total": float}}
- total_amount: float (sum of all line items)
- notes: str (any additional context)

Only return valid JSON. No markdown, no extra text."""


async def send_initial_outreach(lead_id: str, contact_email: str | None) -> str:
    """Generate personalised email via Nemotron, send via SMTP or save to Gmail Drafts."""
    # Get lead details from the database
    async with get_conn() as conn:
        row = await conn.execute(
            """
            SELECT 
                COALESCE(metadata->>'name', 'Business Owner') as business_name,
                COALESCE(metadata->>'category', 'Local Business') as category,
                (SELECT payload FROM lead_enrichment WHERE lead_id = %s LIMIT 1) as enrichment
            FROM leads 
            WHERE id = %s
            """, 
            (lead_id, lead_id)
        )
        lead = await row.fetchone()

    if not lead:
        raise ValueError(f"Lead {lead_id} not found")

    business_name = lead[0]
    category = lead[1]
    enrichment = lead[2] or {}

    prompt = INITIAL_OUTREACH_PROMPT.format(
        business_name=business_name, 
        category=category, 
        enrichment=json.dumps(enrichment)
    )
    messages = [{"role": "user", "content": prompt}]

    # 1. Generate Email
    print(f"   📝 [Negotiation] Drafting email for {business_name}...")
    email_body = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.4)

    # 2. Save to local Outbox as a physical backup
    os.makedirs("outbox", exist_ok=True)
    filepath = f"outbox/email_{lead_id}.txt"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"To: {contact_email if contact_email else 'NO EMAIL FOUND (Saved to Gmail Drafts)'}\n")
        f.write(f"Subject: Quick question about {business_name}'s digital presence\n\n")
        f.write(email_body)

    subject_line = f"Quick question about {business_name}'s digital presence"

    # 3. Sending / Drafting Logic
    if not contact_email:
        print(f"   📑 [Negotiation] No email found for {business_name}. Saving to Gmail Drafts via IMAP.")
        try:
            await save_draft(to="", subject=subject_line, body=email_body)
        except Exception as e:
            print(f"   ⚠️ [Negotiation] Failed to save to Gmail Drafts: {e}")
        return "draft_only"
    
    try:
        result = await send_email(
            to=contact_email, 
            subject=subject_line, 
            body=email_body
        )
        print(f"   ✅ [Negotiation] Email SENT successfully to {contact_email}!")
        return result.get("message_id", "unknown")
    except Exception as e:
        print(f"   ❌ [Negotiation] Failed to send via Gmail: {e}. Draft saved locally.")
        return "draft_only"


async def generate_proposal(state: BatonState) -> dict[str, Any]:
    """Return a quotation line_items dict using Nemotron reasoning."""
    cleaned = state.get("cleaned_data", {})
    enriched = state.get("enriched_data", {})
    score = state.get("score", 0)

    business_name = cleaned.get("name", "Client")

    prompt = PROPOSAL_PROMPT.format(
        business_name=business_name, 
        enrichment=json.dumps(enriched), 
        score=score
    )
    messages = [{"role": "user", "content": prompt}]

    response = await chat(messages=messages, model="nemotron", enable_thinking=True, temperature=0.3)

    try:
        # Clean up potential markdown formatting
        clean_json = response.strip().removeprefix("```json").removesuffix("```").strip()
        proposal = json.loads(clean_json)
        proposal["total_amount"] = float(proposal.get("total_amount", 0))
        return proposal
    except json.JSONDecodeError:
        # Fallback proposal
        return {
            "line_items": [
                {"description": "Modern Website + Booking Setup", "quantity": 1, "unit_price": 1500.0, "total": 1500.0},
                {"description": "AI Lead Nurturing Automation", "quantity": 1, "unit_price": 1000.0, "total": 1000.0}
            ],
            "total_amount": 2500.0,
            "notes": "Default proposal - LLM response parsing failed",
        }


async def create_quotation(lead_id: str, line_items: dict[str, Any]) -> str:
    """INSERT into quotations, return quotation_id."""
    quotation_id = str(uuid.uuid4())
    total_amount = line_items.get("total_amount", 0.0)

    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO quotations (id, lead_id, line_items, total_amount, status)
            VALUES (%s, %s, %s, %s, 'draft')
            """,
            (quotation_id, lead_id, json.dumps(line_items), total_amount),
        )

    return quotation_id


async def request_hitl_approval(quotation_id: str) -> None:
    """INSERT into approvals with status='pending'; the HITL dashboard picks this up."""
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO approvals (quotation_id, requested_by, status, requested_at)
            VALUES (%s, 'negotiator_agent', 'pending', NOW())
            """,
            (quotation_id,),
        )


async def negotiation_node(state: BatonState) -> BatonState:
    """Drive the negotiation loop; return updated state with quotation_id."""
    lead_id = state.get("lead_id", "")
    print(f"   🤝 [Negotiation] Starting negotiation for lead: {lead_id}")

    cleaned = state.get("cleaned_data", {})
    
    # If it's empty, it stays None. No fake emails.
    contact_email = cleaned.get("email")

    # Send initial outreach (or save to Gmail Drafts)
    try:
        await send_initial_outreach(lead_id, contact_email)
    except Exception as e:
        print(f"   ⚠️ [Negotiation] Outreach error: {str(e)}")

    # Generate proposal
    proposal = await generate_proposal(state)
    quotation_id = await create_quotation(lead_id, proposal)

    # Request HITL approval
    await request_hitl_approval(quotation_id)

    # Explicitly set stage to "quoted" so the Supervisor routes to the Reporter
    return {
        **state,
        "quotation_id": quotation_id,
        "approval_status": "pending",
        "stage": "quoted",
    }