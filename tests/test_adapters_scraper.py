"""Unit tests for adapters.scraper module."""

import asyncio
import pytest
import respx
import httpx

from adapters.scraper import submit_job, poll_job, download_results, scrape


@pytest.fixture
def mock_maps_scraper_url(monkeypatch):
    """Mock the maps_scraper_url setting."""
    monkeypatch.setattr("adapters.scraper.settings.maps_scraper_url", "http://test-scraper:8080")


async def test_submit_job_returns_job_id(mock_maps_scraper_url):
    """Test that submit_job returns job_id from API response."""
    with respx.mock:
        respx.post("http://test-scraper:8080/api/v1/jobs").mock(
            return_value=httpx.Response(200, json={"job_id": "abc123"})
        )

        job_id = await submit_job("coffee shops", "NYC", 100)
        assert job_id == "abc123"


async def test_submit_job_raises_on_error(mock_maps_scraper_url):
    """Test that submit_job raises on HTTP error."""
    with respx.mock:
        respx.post("http://test-scraper:8080/api/v1/jobs").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(httpx.HTTPStatusError):
            await submit_job("coffee shops", "NYC", 100)


async def test_poll_job_returns_download_url(mock_maps_scraper_url):
    """Test that poll_job returns download_url when job is done."""
    with respx.mock:
        # First poll returns pending
        respx.get("http://test-scraper:8080/api/v1/jobs/abc123").mock(
            side_effect=[
                httpx.Response(200, json={"status": "pending"}),
                httpx.Response(200, json={"status": "running"}),
                httpx.Response(200, json={"status": "done", "download_url": "/dl/abc123.csv"}),
            ]
        )

        download_url = await poll_job("abc123", timeout_s=10.0, interval_s=0.01)
        assert download_url == "http://test-scraper:8080/dl/abc123.csv"


async def test_poll_job_raises_on_failed(mock_maps_scraper_url):
    """Test that poll_job raises when job fails."""
    with respx.mock:
        respx.get("http://test-scraper:8080/api/v1/jobs/abc123").mock(
            return_value=httpx.Response(200, json={"status": "failed", "error": "Scraping failed"})
        )

        with pytest.raises(RuntimeError, match="Scrape job failed"):
            await poll_job("abc123", timeout_s=10.0, interval_s=0.01)


async def test_poll_job_raises_on_timeout(mock_maps_scraper_url):
    """Test that poll_job raises TimeoutError when job doesn't complete."""
    with respx.mock:
        respx.get("http://test-scraper:8080/api/v1/jobs/abc123").mock(
            return_value=httpx.Response(200, json={"status": "pending"})
        )

        with pytest.raises(TimeoutError):
            await poll_job("abc123", timeout_s=0.1, interval_s=0.01)


async def test_download_results_parses_csv(mock_maps_scraper_url):
    """Test that download_results parses CSV into list of dicts."""
    csv_content = "name,email,phone\nAcme Corp,test@acme.com,555-1234\nBeta Inc,info@beta.com,555-5678"

    with respx.mock:
        respx.get("http://test-scraper:8080/dl/abc123.csv").mock(
            return_value=httpx.Response(200, text=csv_content)
        )

        results = await download_results("http://test-scraper:8080/dl/abc123.csv")
        assert len(results) == 2
        assert results[0]["name"] == "Acme Corp"
        assert results[0]["email"] == "test@acme.com"
        assert results[1]["name"] == "Beta Inc"
        assert results[1]["email"] == "info@beta.com"


async def test_scrape_pipeline_composes_all_steps(mock_maps_scraper_url):
    """Test that scrape() composes submit_job → poll_job → download_results."""
    csv_content = "name,email,phone\nAcme Corp,test@acme.com,555-1234\nBeta Inc,info@beta.com,555-5678"

    with respx.mock:
        # submit_job
        respx.post("http://test-scraper:8080/api/v1/jobs").mock(
            return_value=httpx.Response(200, json={"job_id": "abc123"})
        )
        # poll_job - two pending then done
        respx.get("http://test-scraper:8080/api/v1/jobs/abc123").mock(
            side_effect=[
                httpx.Response(200, json={"status": "pending"}),
                httpx.Response(200, json={"status": "running"}),
                httpx.Response(200, json={"status": "done", "download_url": "/dl/abc123.csv"}),
            ]
        )
        # download_results
        respx.get("http://test-scraper:8080/dl/abc123.csv").mock(
            return_value=httpx.Response(200, text=csv_content)
        )

        results = await scrape("coffee shops", "NYC", 100)
        assert len(results) == 2
        assert results[0]["name"] == "Acme Corp"
        assert results[1]["name"] == "Beta Inc"