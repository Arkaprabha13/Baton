"""Unit tests for tools.hitl_dashboard module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from tools.hitl_dashboard import app


@pytest.fixture
def mock_db():
    """Mock database connection for hitl dashboard tests."""
    with patch("tools.hitl_dashboard.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn
        yield mock_conn


@pytest.fixture
def async_client():
    """Create an async test client for the FastAPI app."""
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_list_pending_approvals_returns_list(mock_db, async_client):
    """Test GET /approvals returns pending approvals."""
    # Mock database response
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, key: [
        "approval-123",  # id
        "quote-456",     # quotation_id
        "pending",       # status
        None,            # created_at
        None,            # resolved_at
        "lead-789",      # lead_id
        5000.0,          # total_value
        '{"items": []}', # line_items
    ][key]

    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[mock_row])
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    response = await async_client.get("/approvals")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["id"] == "approval-123"
    assert data[0]["status"] == "pending"
    assert data[0]["total_value"] == 5000.0


@pytest.mark.asyncio
async def test_list_pending_approvals_empty(mock_db, async_client):
    """Test GET /approvals returns empty list when no pending approvals."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    response = await async_client.get("/approvals")

    assert response.status_code == 200
    data = response.json()
    assert data == []


@pytest.mark.asyncio
async def test_approve_approval_success(mock_db, async_client):
    """Test POST /approvals/{id}/approve updates approval to approved."""
    # Mock check for existing pending approval
    mock_check_cursor = AsyncMock()
    mock_check_cursor.fetchone = AsyncMock(return_value=["approval-123"])

    # Mock update execution
    mock_update_cursor = AsyncMock()
    mock_update_cursor.fetchone = AsyncMock(return_value=None)

    mock_db.execute = AsyncMock(side_effect=[mock_check_cursor, mock_update_cursor])

    response = await async_client.post("/approvals/approval-123/approve?approved_by=admin")

    assert response.status_code == 200
    data = response.json()
    assert data["approval_id"] == "approval-123"
    assert data["status"] == "approved"
    assert data["approved_by"] == "admin"


@pytest.mark.asyncio
async def test_approve_approval_not_found(mock_db, async_client):
    """Test POST /approvals/{id}/approve returns 404 when not found."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    response = await async_client.post("/approvals/nonexistent/approve?approved_by=admin")

    assert response.status_code == 404
    assert "Pending approval not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reject_approval_success(mock_db, async_client):
    """Test POST /approvals/{id}/reject updates approval to rejected."""
    # Mock check for existing pending approval
    mock_check_cursor = AsyncMock()
    mock_check_cursor.fetchone = AsyncMock(return_value=["approval-123"])

    # Mock update execution
    mock_update_cursor = AsyncMock()
    mock_update_cursor.fetchone = AsyncMock(return_value=None)

    mock_db.execute = AsyncMock(side_effect=[mock_check_cursor, mock_update_cursor])

    response = await async_client.post(
        "/approvals/approval-123/reject?approved_by=admin&notes=Budget too high"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["approval_id"] == "approval-123"
    assert data["status"] == "rejected"
    assert data["approved_by"] == "admin"
    assert data["notes"] == "Budget too high"


@pytest.mark.asyncio
async def test_reject_approval_not_found(mock_db, async_client):
    """Test POST /approvals/{id}/reject returns 404 when not found."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=None)
    mock_db.execute = AsyncMock(return_value=mock_cursor)

    response = await async_client.post("/approvals/nonexistent/reject?approved_by=admin")

    assert response.status_code == 404
    assert "Pending approval not found" in response.json()["detail"]