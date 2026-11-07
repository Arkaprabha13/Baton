"""Qualifier agent for Baton.

Scores the lead 0-100 using Groq (fast) with a structured multi-parameter prompt.
Writes score back to leads.score.
Transitions enriched → qualified (score >= 50) or enriched → lost (score < 50).
"""

import json
import re
from typing import Any

from agents.state import BatonState
from core.db import get_conn
from core.llm import chat

QUALIFICATION_THRESHOLD: float = 50.0

SCORING_PROMPT = """
You are an expert agency sales qualifier. Your job is to evaluate a lead and provide a structured JSON response.

Return ONLY a valid JSON object with these exact keys:
{
    "traction_score": <int 0-30. Give 30 if they have >20 Google reviews. 15 if they have 5-20. 0 if 0 reviews.>,
    "gap_score": <int 0-40. Give 40 if they have obvious digital gaps (no website, no booking, terrible SEO). 0 if they are flawless.>,
    "fit_score": <int 0-30. Give 30 if they are a local B2C (dentist, cafe) or growing B2B. 0 if they are an enterprise or a hobby.>,
    "total_score": <int 0-100. MUST equal traction_score + gap_score + fit_score.>,
    "reasoning": "<string: a short sentence explaining the score>"
}
"""


async def score_lead(cleaned_data: dict, enriched_data: dict, raw_data: dict) -> float:
    """Score the lead using a structured JSON prompt with Groq."""
    # Robustly get the Google Maps review data
    reviews = raw_data.get('reviews') or raw_data.get('review_count') or raw_data.get('user_ratings_total') or 0
    rating = raw_data.get('rating') or raw_data.get('review_rating') or 'N/A'
    
    review_info = f"Google Maps Reviews: {reviews}, Rating: {rating}"
    prompt_text = f"Business Info: {cleaned_data}\n{review_info}\nAI Research: {enriched_data}"
    
    messages = [
        {"role": "system", "content": SCORING_PROMPT},
        {"role": "user", "content": prompt_text},
    ]
    
    try:
        # Increased max_tokens to allow for the JSON output
        response = await chat(messages=messages, model="groq", temperature=0.1, max_tokens=150)
        
        # Clean up potential markdown formatting from the LLM
        clean_json = response.strip().removeprefix("```json").removesuffix("```").strip()
        
        try:
            # Try to parse as JSON first (preferred)
            data = json.loads(clean_json)
            score = float(data.get("total_score", 0.0))
            
            print(f"   📊 [Qualifier] Traction: {data.get('traction_score')}/30 | Gaps: {data.get('gap_score')}/40 | Fit: {data.get('fit_score')}/30")
            print(f"   💡 [Qualifier] Reasoning: {data.get('reasoning')}")
            
        except json.JSONDecodeError:
            # Fallback: If JSON fails, use regex to extract the first 1-3 digit number
            print(f"   ⚠️ [Qualifier] JSON parsing failed. Falling back to regex.")
            match = re.search(r'\b(\d{1,3})\b', response)
            score = float(match.group(1)) if match else 0.0
            
        return min(100.0, max(0.0, score))
        
    except Exception as e:
        print(f"   ❌ [Qualifier] Groq API Error: {e}")
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
    cleaned = state.get("cleaned_data", {})
    enriched = state.get("enriched_data", {})
    raw = state.get("raw_data", {})
    lead_id = state.get("lead_id", "")
    
    print(f"   🧠 [Qualifier] Scoring lead: {cleaned.get('name', 'Unknown')}...")
    score = await score_lead(cleaned, enriched, raw)
    
    # Save the score to Supabase immediately
    await persist_score(lead_id, score)
    
    stage = "qualified" if score >= QUALIFICATION_THRESHOLD else "lost"
    print(f"   🎯 [Qualifier] Score: {score}/100 -> Stage: {stage}")

    return {**state, "score": score, "stage": stage}