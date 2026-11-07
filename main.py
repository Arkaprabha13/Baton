"""Baton - Main entry point.

Initializes the DB pool, starts the scheduler, and runs the FastAPI app using uvicorn.
"""

import asyncio
import signal
import sys

import uvicorn

from core.config import settings
from core.db import close_pool, init_pool
from tools.hitl_dashboard import app
from tools.scheduler import start_scheduler, stop_scheduler

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())



async def startup() -> None:
    """Application startup: initialize DB pool and start scheduler."""
    print("Starting Baton...")
    await init_pool()
    print("Database pool initialized.")

    await start_scheduler()
    print("Scheduler started.")


async def shutdown() -> None:
    """Application shutdown: stop scheduler and close DB pool."""
    print("Shutting down Baton...")
    await stop_scheduler()
    print("Scheduler stopped.")

    await close_pool()
    print("Database pool closed.")


async def main() -> None:
    """Main entry point."""
    await startup()

    # Run FastAPI app
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)

    # Handle shutdown signals
    loop = asyncio.get_running_loop()

    def handle_signal() -> None:
        asyncio.create_task(shutdown())
        server.should_exit = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    try:
        await server.serve()
    finally:
        await shutdown()


if __name__ == "__main__":
    asyncio.run(main())