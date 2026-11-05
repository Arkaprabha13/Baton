"""Maps Scraper adapter for Baton.

Wraps the Maps Scraper Docker REST API. Submits a scrape job,
polls until complete, downloads and parses the result CSV into
a list of raw lead dicts.
"""

import csv
import io
from typing import Any

import httpx

from core.config import settings


async def submit_job(query: str, location: str, max_results: int = 100) -> str:
    """POST /api/v1/jobs; return job_id.

    Args:
        query: Search query (e.g., "coffee shops").
        location: Location to search in (e.g., "NYC").
        max_results: Maximum number of results to return.

    Returns:
        The job_id string from the API response.
    """
    url = f"{settings.maps_scraper_url}/api/v1/jobs"
    payload = {
        "query": query,
        "location": location,
        "max_results": max_results,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["job_id"]


async def poll_job(
    job_id: str, timeout_s: float = 300.0, interval_s: float = 5.0
) -> str:
    """Poll GET /api/v1/jobs/{job_id} until status == 'done'; return download URL.

    Args:
        job_id: The job ID returned by submit_job.
        timeout_s: Maximum time to wait for completion in seconds.
        interval_s: Polling interval in seconds.

    Returns:
        The download URL from the completed job.

    Raises:
        TimeoutError: If the job doesn't complete within timeout_s.
        RuntimeError: If the job fails or returns an error status.
    """
    url = f"{settings.maps_scraper_url}/api/v1/jobs/{job_id}"
    elapsed = 0.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout_s:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            status = data.get("status")
            if status == "done":
                download_url = data.get("download_url")
                if not download_url:
                    raise RuntimeError("Job completed but no download_url provided")
                # Handle relative URLs
                if download_url.startswith("/"):
                    return f"{settings.maps_scraper_url}{download_url}"
                return download_url
            elif status == "failed":
                error = data.get("error", "Unknown error")
                raise RuntimeError(f"Scrape job failed: {error}")
            elif status in ("pending", "running"):
                pass  # Continue polling

            await asyncio.sleep(interval_s)
            elapsed += interval_s

    raise TimeoutError(f"Job {job_id} did not complete within {timeout_s} seconds")


async def download_results(download_url: str) -> list[dict[str, Any]]:
    """GET download_url, parse CSV rows, return list of dicts.

    Args:
        download_url: Full URL to the CSV download endpoint.

    Returns:
        List of dictionaries representing CSV rows.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(download_url)
        response.raise_for_status()
        csv_text = response.text

    # Parse CSV
    reader = csv.DictReader(io.StringIO(csv_text))
    return [row for row in reader]


async def scrape(query: str, location: str, max_results: int = 100) -> list[dict[str, Any]]:
    """Compose submit_job → poll_job → download_results pipeline.

    Args:
        query: Search query (e.g., "coffee shops").
        location: Location to search in (e.g., "NYC").
        max_results: Maximum number of results to return.

    Returns:
        List of lead dictionaries from the scraped results.
    """
    job_id = await submit_job(query, location, max_results)
    download_url = await poll_job(job_id)
    results = await download_results(download_url)
    return results


# Import asyncio at the end to avoid circular imports
import asyncio