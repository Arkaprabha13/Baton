import sys
import asyncio
import selectors

from core.db import init_pool, close_pool
from tools.scheduler import run_scrape_pipeline

async def main():
    print("🔌 Initializing database pool...")
    await init_pool()
    
    try:
        print("🚀 Starting pipeline...")
        await run_scrape_pipeline('plumbers ', 'Los Angeles, CA')
    finally:
        print("🔒 Closing database pool...")
        await close_pool()

if __name__ == "__main__":
    if sys.platform == "win32":
        # Force the SelectorEventLoop that psycopg needs
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    else:
        asyncio.run(main())