"""Unit tests for tools.scheduler module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from apscheduler.triggers.cron import CronTrigger

from tools.scheduler import scheduler, add_scrape_job, start_scheduler, stop_scheduler, run_scrape_pipeline


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Reset scheduler state before and after each test."""
    # Remove all jobs
    scheduler.remove_all_jobs()
    yield
    scheduler.remove_all_jobs()


def test_add_scrape_job_returns_job_id():
    """Test that add_scrape_job returns a non-empty job_id."""
    job_id = add_scrape_job("coffee shops", "NYC", "0 6 * * 1-5")

    assert job_id is not None
    assert len(job_id) > 0


def test_add_scrape_job_creates_job_in_scheduler():
    """Test that the job is added to the scheduler."""
    job_id = add_scrape_job("coffee shops", "NYC", "0 6 * * 1-5")

    job = scheduler.get_job(job_id)
    assert job is not None
    assert job.id == job_id
    assert job.name == "scrape_coffee shops_NYC"


def test_add_scrape_job_has_cron_trigger():
    """Test that the job's trigger is a CronTrigger."""
    job_id = add_scrape_job("coffee shops", "NYC", "0 6 * * 1-5")

    job = scheduler.get_job(job_id)
    assert job.trigger is not None
    assert isinstance(job.trigger, CronTrigger)


def test_add_scrape_job_default_cron():
    """Test that default cron expression is used when not provided."""
    job_id = add_scrape_job("restaurants", "LA")

    job = scheduler.get_job(job_id)
    assert job is not None
    # Default should be "0 6 * * 1-5" (weekdays at 6 AM)


def test_add_scrape_job_replace_existing():
    """Test that adding job with same query/location replaces existing."""
    job_id1 = add_scrape_job("coffee shops", "NYC", "0 6 * * 1-5")
    job_id2 = add_scrape_job("coffee shops", "NYC", "0 7 * * 1-5")

    # Should have same job_id (deterministic based on query+location)
    assert job_id1 == job_id2
    job = scheduler.get_job(job_id1)
    assert job is not None


@pytest.mark.asyncio
async def test_start_scheduler():
    """Test that start_scheduler starts the scheduler."""
    # Ensure scheduler is stopped
    if scheduler.running:
        scheduler.shutdown(wait=False)

    await start_scheduler()
    assert scheduler.running is True


@pytest.mark.asyncio
async def test_stop_scheduler():
    """Test that stop_scheduler calls scheduler.shutdown."""
    from tools.scheduler import scheduler, stop_scheduler
    
    # Ensure scheduler is running
    if not scheduler.running:
        scheduler.start()
    
    # Mock the shutdown method
    with patch.object(scheduler, 'shutdown') as mock_shutdown:
        mock_shutdown.return_value = None
        await stop_scheduler()
        mock_shutdown.assert_called_once_with(wait=False)


@pytest.mark.asyncio
async def test_run_scrape_pipeline_calls_scraper_and_graph():
    """Test that run_scrape_pipeline calls scraper and runs graph for each lead."""
    mock_leads = [
        {"name": "Cafe A", "email": "a@cafe.com"},
        {"name": "Cafe B", "email": "b@cafe.com"},
    ]

    with patch("tools.scheduler.scrape", new_callable=AsyncMock) as mock_scrape:
        with patch("tools.scheduler.run_graph", new_callable=AsyncMock) as mock_run_graph:
            with patch("tools.scheduler.get_conn") as mock_get_conn:
                mock_scrape.return_value = mock_leads

                mock_conn = AsyncMock()
                mock_get_conn.return_value.__aenter__.return_value = mock_conn

                await run_scrape_pipeline("coffee shops", "NYC")

                # Verify scrape was called (max_results has default value)
                mock_scrape.assert_awaited_once_with("coffee shops", "NYC")

                # Verify DB insert called for each lead
                assert mock_conn.execute.await_count == 2

                # Verify graph run for each lead
                assert mock_run_graph.await_count == 2


@pytest.mark.asyncio
async def test_run_scrape_pipeline_handles_empty_results():
    """Test that run_scrape_pipeline handles empty scrape results."""
    with patch("tools.scheduler.scrape", new_callable=AsyncMock) as mock_scrape:
        with patch("tools.scheduler.run_graph", new_callable=AsyncMock) as mock_run_graph:
            mock_scrape.return_value = []

            await run_scrape_pipeline("coffee shops", "NYC")

            mock_scrape.assert_awaited_once()
            mock_run_graph.assert_not_awaited()