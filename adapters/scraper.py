"""Maps Scraper adapter for Baton.

Wraps the Maps Scraper Docker REST API. Submits a scrape job,
polls until complete, downloads and parses the result CSV into
a list of raw lead dicts.
"""

import asyncio
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
    
    combined_keyword = f"{query} in {location}"
    
    # Hardcoded coordinates for Austin, TX for testing
    payload = {
        "name": "baton_job",
        "keywords": [combined_keyword],
        "lat": "30.2672",
        "lon": "-97.7431",
        "max_time": 300,
        "depth": 10,
        "email": True,
        "lang": "en",
        "zoom": 15
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        
        # We expect a 201 Created status code, which raise_for_status allows.
        response.raise_for_status()
        data = response.json()
        
        # The API actually returns {"id": "..."} on success
        job_id = data.get("id") or data.get("job_id")
        if not job_id:
            raise RuntimeError(f"API did not return a job ID. Response: {data}")
            
        return job_id


async def poll_job(
    job_id: str, timeout_s: float = 300.0, interval_s: float = 5.0
) -> str:
    """Poll GET /api/v1/jobs/{job_id} until the job is done; return download URL.

    Args:
        job_id: The job ID returned by submit_job.
        timeout_s: Maximum time to wait for completion in seconds.
        interval_s: Polling interval in seconds.

    Returns:
        The constructed download URL for the completed job.
    """
    url = f"{settings.maps_scraper_url}/api/v1/jobs/{job_id}"
    elapsed = 0.0

    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed < timeout_s:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # FIX 1 & 2: Parse the exact API schema
            status = data.get("Status")
            progress = data.get("Progress", {})
            stage = progress.get("stage")
            
            # If Status is "ok" and stage is "done" (or 100% complete)
            if status == "ok" and (stage == "done" or progress.get("percent") == 100):
                # FIX 3: Construct the download URL manually
                return f"{settings.maps_scraper_url}/api/v1/jobs/{job_id}/download"
                
            # Check for errors
            elif status == "failed" or data.get("Error"):
                error = data.get("Error", "Unknown error")
                raise RuntimeError(f"Scrape job failed: {error}")

            # Keep waiting
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
    # Added follow_redirects=True in case the Docker container redirects to an S3 bucket
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
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
    print(f"🚀 Submitting job for: {query} in {location}...")
    job_id = await submit_job(query, location, max_results)
    
    print(f"⏳ Job {job_id} submitted. Polling for completion...")
    download_url = await poll_job(job_id)
    
    print(f"📥 Job done! Downloading results from {download_url}...")
    results = await download_results(download_url)
    
    print(f"✅ Successfully scraped {len(results)} leads!")
    return results