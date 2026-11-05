"""Scheduler for Baton.

APScheduler-based job runner. Schedules the Maps Scraper pipeline to run on a cron.
Publishes new leads into the LangGraph pipeline.
"""

import hashlib
import uuid
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

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
    """Call adapters.scraper.scrape(), persist raw leads, enqueue into LangGraph.

    Args:
        query: Search query (e.g., "coffee shops").
        location: Location to search in (e.g., "NYC").
    """
    # Scrape leads from Maps Scraper
    leads = await scrape(query, location)

    # Persist raw leads and enqueue into LangGraph
    for lead in leads:
        lead_id = str(uuid.uuid4())

        # Insert raw lead into database
        async with get_conn() as conn:
            await conn.execute(
                """
                INSERT INTO leads (id, raw_data, stage, created_at)
                VALUES (%s, %s, 'raw', NOW())
                ON CONFLICT (id) DO UPDATE SET
                    raw_data = EXCLUDED.raw_data,
                    stage = 'raw',
                    updated_at = NOW()
                """,
                (lead_id, lead),
            )

        # Run the LangGraph pipeline for this lead
        initial_state: BatonState = {
            "lead_id": lead_id,
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


def add_scrape_job(
    query: str,
    location: str,
    cron_expr: str = "0 6 * * 1-5",
) -> str:
    """Add a cron job to the scheduler; return job_id.

    Args:
        query: Search query for the scraper.
        location: Location for the scraper.
        cron_expr: Cron expression (default: weekdays at 6 AM).

    Returns:
        The job ID.
    """
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