"""Scheduler for Baton.

APScheduler-based job runner. Schedules the Maps Scraper pipeline to run on a cron.
Publishes new leads into the LangGraph pipeline.
"""

import hashlib
import uuid
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from psycopg.types.json import Jsonb

from adapters.scraper import scrape
from agents.graph import run_graph
from agents.state import BatonState
from core.db import get_conn

scheduler = AsyncIOScheduler()


def _deterministic_job_id(query: str, location: str) -> str:
    """Generate a deterministic job ID based on query and location."""
    key = f"{query}|{location}".encode()
    return hashlib.sha256(key).hexdigest()[:16]


async def run_scrape_pipeline(query: str, location: str) -> None:
    """Call adapters.scraper.scrape(), persist raw leads, enqueue into LangGraph."""
    leads = await scrape(query, location)

    print(f"💾 Saving {len(leads)} leads to database and starting LangGraph...")

    for i, lead in enumerate(leads):
        print(f"⚙️ Processing lead {i+1}/{len(leads)}: {lead.get('title', 'Unknown')}...")
        generated_id = str(uuid.uuid4())
        dedupe_key = lead.get("cid") or lead.get("link") or generated_id
        actual_lead_id = generated_id

        async with get_conn() as conn:
            # We use a cursor to get the actual ID back from the DB
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO leads (id, dedupe_key, raw_data, stage, created_at)
                    VALUES (%s, %s, %s, 'raw', NOW())
                    ON CONFLICT (dedupe_key) DO UPDATE SET
                        raw_data = EXCLUDED.raw_data,
                        stage = 'raw',
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (generated_id, dedupe_key, Jsonb(lead)),
                )
                row = await cur.fetchone()
                if row:
                    actual_lead_id = row[0]

        # Run the LangGraph pipeline using the ID the DB actually saved
        initial_state: BatonState = {
            "lead_id": actual_lead_id, 
            "raw_data": lead,
            "cleaned_data": {},
            "enriched_data": {},
            "score": 0.0,
            "stage": "raw",
            "messages": [],
            "quotation_id": None,
            "approval_status": None,
            "errors": [],
        }

        await run_graph(initial_state)


def add_scrape_job(query: str, location: str, cron_expr: str = "0 6 * * 1-5") -> str:
    """Add a cron job to the scheduler; return job_id."""
    job_id = _deterministic_job_id(query, location)
    scheduler.add_job(
        run_scrape_pipeline,
        trigger=CronTrigger.from_crontab(cron_expr),
        args=[query, location],
        id=job_id,
        name=f"scrape_{query}_{location}",
        replace_existing=True,
    )
    return job_id


async def start_scheduler() -> None:
    """Start APScheduler. Called at app startup."""
    if not scheduler.running:
        scheduler.start()


async def stop_scheduler() -> None:
    """Shutdown APScheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)