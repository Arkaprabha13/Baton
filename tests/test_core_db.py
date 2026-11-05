"""Unit tests for core.db module."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import psycopg
from psycopg_pool import AsyncConnectionPool

import core.db as db_module
from core.db import init_pool, close_pool, get_conn


@pytest_asyncio.fixture
async def mock_pool():
    """Create a mock connection pool."""
    mock_pool = AsyncMock(spec=AsyncConnectionPool)
    mock_conn = AsyncMock(spec=psycopg.AsyncConnection)
    # connection() returns an async context manager
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.connection = MagicMock(return_value=cm)
    mock_pool.open = AsyncMock()
    mock_pool.close = AsyncMock()
    return mock_pool, mock_conn


@pytest_asyncio.fixture(autouse=True)
async def reset_pool():
    """Reset the global pool before and after each test."""
    original_pool = db_module._pool
    db_module._pool = None
    yield
    if db_module._pool is not None:
        await db_module._pool.close()
    db_module._pool = original_pool


async def test_init_pool_creates_pool(monkeypatch, mock_pool):
    """Test that init_pool creates and opens the connection pool."""
    mock_pool_instance, mock_conn = mock_pool

    with patch("core.db.AsyncConnectionPool", return_value=mock_pool_instance) as mock_pool_class:
        with patch("core.db.settings") as mock_settings:
            mock_settings.db_dsn = "postgresql+psycopg://user:pass@localhost:5432/test"

            await init_pool()

            mock_pool_class.assert_called_once_with(
                conninfo="postgresql+psycopg://user:pass@localhost:5432/test",
                min_size=1,
                max_size=10,
                open=False,
            )
            mock_pool_instance.open.assert_awaited_once()


async def test_init_pool_idempotent(monkeypatch, mock_pool):
    """Test that calling init_pool twice doesn't create two pools."""
    mock_pool_instance, mock_conn = mock_pool

    with patch("core.db.AsyncConnectionPool", return_value=mock_pool_instance):
        with patch("core.db.settings") as mock_settings:
            mock_settings.db_dsn = "postgresql+psycopg://user:pass@localhost:5432/test"

            await init_pool()
            await init_pool()

            # Should only be called once
            assert mock_pool_instance.open.await_count == 1


async def test_get_conn_yields_connection(mock_pool):
    """Test that get_conn yields a connection from the pool."""
    mock_pool_instance, mock_conn = mock_pool

    db_module._pool = mock_pool_instance

    async with get_conn() as conn:
        assert conn is mock_conn

    mock_pool_instance.connection.assert_called_once()


async def test_get_conn_raises_without_pool():
    """Test that get_conn raises RuntimeError when pool not initialized."""
    db_module._pool = None

    with pytest.raises(RuntimeError, match="Connection pool not initialized"):
        async with get_conn():
            pass


async def test_close_pool_closes_pool(mock_pool):
    """Test that close_pool closes the pool."""
    mock_pool_instance, mock_conn = mock_pool

    db_module._pool = mock_pool_instance

    await close_pool()

    mock_pool_instance.close.assert_awaited_once()
    assert db_module._pool is None


async def test_close_pool_idempotent():
    """Test that close_pool is idempotent."""
    db_module._pool = None

    # Should not raise
    await close_pool()
    await close_pool()

    assert db_module._pool is None


async def test_get_conn_after_close_raises(mock_pool):
    """Test that get_conn raises after close_pool."""
    mock_pool_instance, mock_conn = mock_pool

    db_module._pool = mock_pool_instance

    await close_pool()

    with pytest.raises(RuntimeError, match="Connection pool not initialized"):
        async with get_conn():
            pass