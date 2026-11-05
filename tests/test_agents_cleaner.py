"""Unit tests for agents.cleaner module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.cleaner import normalise, compute_dedupe_key, cleaner_node, persist_cleaned_lead


def test_normalise_lowercases_email_and_strips_whitespace():
    """Test that normalise lowercases emails and strips whitespace."""
    raw = {"Email": " Test@Example.COM ", "Name": "  Acme  "}
    result = normalise(raw)

    assert result["email"] == "test@example.com"
    assert result["name"] == "Acme"


def test_normalise_maps_field_aliases():
    """Test that normalise maps common field aliases to canonical names."""
    raw = {
        "E-mail": "user@domain.com",
        "Telephone": "555-1234",
        "Business_Name": "Test Corp",
        "Street": "123 Main St",
        "URL": "https://test.com",
        "Industry": "Tech",
    }
    result = normalise(raw)

    assert result["email"] == "user@domain.com"
    assert result["phone"] == "5551234"  # Non-digits stripped
    assert result["name"] == "Test Corp"
    assert result["address"] == "123 Main St"
    assert result["website"] == "https://test.com"
    assert result["category"] == "Tech"


def test_normalise_handles_none_values():
    """Test that normalise skips None values."""
    raw = {"email": "test@test.com", "phone": None, "name": "Test"}
    result = normalise(raw)

    assert result["email"] == "test@test.com"
    assert "phone" not in result
    assert result["name"] == "Test"


def test_compute_dedupe_key_with_email():
    """Test that compute_dedupe_key returns 64-char hex with email."""
    normalised = {"email": "test@example.com", "name": "Test Corp"}
    key = compute_dedupe_key(normalised)

    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


def test_compute_dedupe_key_with_phone():
    """Test that compute_dedupe_key works with phone."""
    normalised = {"phone": "5551234", "name": "Test Corp"}
    key = compute_dedupe_key(normalised)

    assert len(key) == 64


def test_compute_dedupe_key_with_name_and_address():
    """Test that compute_dedupe_key works with name+address."""
    normalised = {"name": "Test Corp", "address": "123 Main St"}
    key = compute_dedupe_key(normalised)

    assert len(key) == 64


def test_compute_dedupe_key_deterministic():
    """Test that compute_dedupe_key is deterministic."""
    normalised = {"email": "test@example.com", "name": "Test Corp"}
    key1 = compute_dedupe_key(normalised)
    key2 = compute_dedupe_key(normalised)

    assert key1 == key2


@pytest.mark.asyncio
async def test_persist_cleaned_lead_calls_db():
    """Test that persist_cleaned_lead executes the upsert query."""
    with patch("agents.cleaner.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await persist_cleaned_lead(
            lead_id="lead-123",
            dedupe_key="abc123",
            normalised={"email": "test@test.com", "name": "Test Corp"},
            raw_data={"Email": "test@test.com"},
        )

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO leads" in call_args[0][0]
        assert call_args[0][1][0] == "lead-123"
        assert call_args[0][1][1] == "abc123"


@pytest.mark.asyncio
async def test_cleaner_node_normalises_and_updates_stage():
    """Test that cleaner_node normalises data and sets stage to cleaned."""
    with patch("agents.cleaner.persist_cleaned_lead", new_callable=AsyncMock) as mock_persist:
        state = {
            "lead_id": "lead-123",
            "raw_data": {"Email": " Test@Example.COM ", "Name": "  Acme  "},
            "cleaned_data": {},
            "enriched_data": {},
            "score": 0.0,
            "stage": "raw",
            "messages": [],
            "quotation_id": None,
            "approval_status": None,
            "errors": [],
        }

        result = await cleaner_node(state)

        assert result["stage"] == "cleaned"
        assert result["cleaned_data"]["email"] == "test@example.com"
        assert result["cleaned_data"]["name"] == "Acme"
        mock_persist.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleaner_node_handles_empty_raw_data():
    """Test that cleaner_node handles empty raw_data gracefully."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {},
        "cleaned_data": {},
        "enriched_data": {},
        "score": 0.0,
        "stage": "raw",
        "messages": [],
        "quotation_id": None,
        "approval_status": None,
        "errors": [],
    }

    result = await cleaner_node(state)

    assert result["stage"] == "cleaned"
    assert "No raw_data to clean" in result["errors"]