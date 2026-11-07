"""Database connection pool management for Baton.

Provides a managed psycopg_pool.AsyncConnectionPool singleton,
plus a get_conn() async context manager used by all DB-writing modules.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import psycopg
from psycopg_pool import AsyncConnectionPool

from core.config import settings

_pool: AsyncConnectionPool | None = None


async def init_pool() -> None:
    """Initialise the global connection pool. Call once at startup."""
    global _pool
    if _pool is not None:
        return
    _pool = AsyncConnectionPool(
        conninfo=settings.db_dsn,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"prepare_threshold": None},
    )
    await _pool.open()


async def close_pool() -> None:
    """Drain and close the connection pool. Call at shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn() -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """Async context manager yielding a connection from the pool.

    Yields:
        An AsyncConnection from the pool.

    Raises:
        RuntimeError: If the pool has not been initialized.
    """
    if _pool is None:
        raise RuntimeError("Connection pool not initialized. Call init_pool() first.")
    async with _pool.connection() as conn:
        yield conn