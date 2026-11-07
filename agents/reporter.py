"""Reporter agent for Baton.

Generates a final conversion summary (Gemini Flash, long context).
Writes to conversion_events. Ends the graph.
"""

from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat


SUMMARY_PROMPT = """Generate a markdown summary of this completed deal.

Lead Information:
- Lead ID: {lead_id}
- Company: {company}
- Contact Email: {email}
- Final Score: {score}

Conversation History:
{conversation}

Quotation:
{quotation}

Write a professional summary covering:
1. Lead background and qualification
2. Negotiation highlights
3. Final deal terms
4. Outcome

Return markdown format. No extra text."""


async def generate_summary(state: BatonState) -> str:
    """Call core.llm.chat(model='gemini') with full message history; return markdown summary.

    Args:
        state: Current BatonState with full conversation history.

    Returns:
        Markdown summary string.
    """
    cleaned = state.get("cleaned_data", {})
    messages = state.get("messages", [])
    quotation_id = state.get("quotation_id", "")

    # Get quotation details
    quotation_details = "Not available"
    if quotation_id:
        async with get_conn() as conn:
            row = await conn.execute(
                "SELECT line_items, total_amount FROM quotations WHERE id = %s", (quotation_id,)
            )
            q = await row.fetchone()
            if q:
                quotation_details = f"Line Items: {q[0]}\nTotal Amount: ${q[1]}"

    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in messages])

    prompt = SUMMARY_PROMPT.format(
        lead_id=state.get("lead_id", ""),
        company=cleaned.get("name", "Unknown"),
        email=cleaned.get("email", "Unknown"),
        score=state.get("score", 0),
        conversation=conversation_text,
        quotation=quotation_details,
    )

    messages_for_llm = [{"role": "user", "content": prompt}]

    summary = await chat(messages=messages_for_llm, model="nemotron", temperature=0.3, max_tokens=4096, enable_thinking=True)
    return summary


async def persist_conversion(lead_id: str, quotation_id: str, value: float) -> None:
    """INSERT into conversion_events via get_conn().

    Args:
        lead_id: The lead identifier.
        quotation_id: The quotation identifier.
        value: Deal value in USD.
    """
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO conversion_events (lead_id, quotation_id, value, converted_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (lead_id, quotation_id, value),
        )


async def reporter_node(state: BatonState) -> BatonState:
    """Summarise the full conversation, persist conversion_event, return final state.

    Args:
        state: Current BatonState with stage='converted'.

    Returns:
        Updated BatonState with stage='converted'.
    """
    lead_id = state.get("lead_id", "")
    quotation_id = state.get("quotation_id", "")

    # Get deal value from quotation
    deal_value = 0.0
    if quotation_id:
        async with get_conn() as conn:
            row = await conn.execute(
                "SELECT total_amount FROM quotations WHERE id = %s", (quotation_id,)
            )
            q = await row.fetchone()
            if q:
                deal_value = float(q[0])

    # Generate summary using Gemini
    summary = await generate_summary(state)

    # Persist conversion event
    await persist_conversion(lead_id, quotation_id, deal_value)

    # Add summary to messages
    messages = state.get("messages", [])
    messages.append({"role": "system", "content": f"Deal Summary:\n{summary}"})

    state["stage"] = "done"
    state["messages"] = messages
    return state