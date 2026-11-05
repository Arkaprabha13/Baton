"""Unit tests for agents.negotiation module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.negotiation import (
    HITL_VALUE_THRESHOLD,
    send_initial_outreach,
    generate_proposal,
    create_quotation,
    request_hitl_approval,
    negotiation_node,
)


@pytest.mark.asyncio
async def test_send_initial_outreach_calls_llm_and_email():
    """Test that send_initial_outreach generates email and sends it."""
    with patch("agents.negotiation.get_conn") as mock_get_conn:
        with patch("agents.negotiation.chat", new_callable=AsyncMock) as mock_chat:
            with patch("agents.negotiation.send_email", new_callable=AsyncMock) as mock_send_email:
                # Mock database response
                mock_conn = AsyncMock()
                mock_cursor = AsyncMock()
                mock_cursor.fetchone = AsyncMock(return_value=["Acme Corp", "test@acme.com", {}])
                mock_conn.execute = AsyncMock(return_value=mock_cursor)
                mock_get_conn.return_value.__aenter__.return_value = mock_conn

                # Mock LLM response
                mock_chat.return_value = "Dear Acme Corp, we'd love to work with you."

                # Mock email response
                mock_send_email.return_value = {"message_id": "msg-123"}

                message_id = await send_initial_outreach("lead-123", "test@acme.com")

                assert message_id == "msg-123"
                mock_chat.assert_awaited_once()
                mock_send_email.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_proposal_returns_valid_structure():
    """Test that generate_proposal returns proper line_items dict."""
    with patch("agents.negotiation.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = json.dumps({
            "line_items": [
                {"description": "Service A", "quantity": 2, "unit_price": 1000.0, "total": 2000.0},
                {"description": "Service B", "quantity": 1, "unit_price": 3000.0, "total": 3000.0},
            ],
            "total_value": 5000.0,
            "notes": "Custom proposal",
        })

        state = {
            "cleaned_data": {"name": "Acme Corp"},
            "enriched_data": {"employee_count_estimate": "51-200"},
            "score": 75.0,
        }

        proposal = await generate_proposal(state)

        assert "line_items" in proposal
        assert "total_value" in proposal
        assert proposal["total_value"] == 5000.0
        assert len(proposal["line_items"]) == 2


@pytest.mark.asyncio
async def test_generate_proposal_handles_invalid_json():
    """Test that generate_proposal falls back on JSON parse error."""
    with patch("agents.negotiation.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = "not valid json"

        state = {
            "cleaned_data": {"name": "Acme Corp"},
            "enriched_data": {},
            "score": 75.0,
        }

        proposal = await generate_proposal(state)

        assert proposal["total_value"] == 2500.0
        assert len(proposal["line_items"]) == 1
        assert "Default proposal" in proposal["notes"]


@pytest.mark.asyncio
async def test_create_quotation_inserts_and_returns_id():
    """Test that create_quotation inserts into DB and returns ID."""
    with patch("agents.negotiation.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        line_items = {
            "line_items": [{"description": "Test", "quantity": 1, "unit_price": 1000.0, "total": 1000.0}],
            "total_value": 1000.0,
            "notes": "Test",
        }

        quotation_id = await create_quotation("lead-123", line_items)

        assert quotation_id is not None
        assert len(quotation_id) > 0
        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO quotations" in call_args[0][0]
        assert call_args[0][1][1] == "lead-123"


@pytest.mark.asyncio
async def test_request_hitl_approval_inserts_pending():
    """Test that request_hitl_approval inserts into approvals table."""
    with patch("agents.negotiation.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await request_hitl_approval("quote-123")

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO approvals" in call_args[0][0]
        assert call_args[0][1] == ("quote-123",)


@pytest.mark.asyncio
async def test_negotiation_node_creates_quotation_and_sets_stage():
    """Test that negotiation_node creates quotation and updates state."""
    with patch("agents.negotiation.send_initial_outreach", new_callable=AsyncMock) as mock_outreach:
        with patch("agents.negotiation.generate_proposal", new_callable=AsyncMock) as mock_proposal:
            with patch("agents.negotiation.create_quotation", new_callable=AsyncMock) as mock_create:
                with patch("agents.negotiation.request_hitl_approval", new_callable=AsyncMock) as mock_hitl:
                    mock_outreach.return_value = "msg-123"
                    mock_proposal.return_value = {
                        "line_items": [{"description": "Test", "quantity": 1, "unit_price": 1000.0, "total": 1000.0}],
                        "total_value": 1000.0,
                        "notes": "Test",
                    }
                    mock_create.return_value = "quote-456"

                    state = {
                        "lead_id": "lead-123",
                        "raw_data": {},
                        "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
                        "enriched_data": {},
                        "score": 75.0,
                        "stage": "qualified",
                        "messages": [],
                        "quotation_id": None,
                        "approval_status": None,
                        "errors": [],
                    }

                    result = await negotiation_node(state)

                    assert result["stage"] == "negotiating"
                    assert result["quotation_id"] == "quote-456"
                    assert result["approval_status"] == "approved"  # Below threshold
                    mock_outreach.assert_awaited_once()
                    mock_proposal.assert_awaited_once()
                    mock_create.assert_awaited_once()
                    mock_hitl.assert_not_awaited()


@pytest.mark.asyncio
async def test_negotiation_node_triggers_hitl_above_threshold():
    """Test that negotiation_node requests HITL when value exceeds threshold."""
    with patch("agents.negotiation.send_initial_outreach", new_callable=AsyncMock) as mock_outreach:
        with patch("agents.negotiation.generate_proposal", new_callable=AsyncMock) as mock_proposal:
            with patch("agents.negotiation.create_quotation", new_callable=AsyncMock) as mock_create:
                with patch("agents.negotiation.request_hitl_approval", new_callable=AsyncMock) as mock_hitl:
                    mock_outreach.return_value = "msg-123"
                    mock_proposal.return_value = {
                        "line_items": [{"description": "Premium", "quantity": 1, "unit_price": 10000.0, "total": 10000.0}],
                        "total_value": 10000.0,
                        "notes": "Premium",
                    }
                    mock_create.return_value = "quote-789"

                    state = {
                        "lead_id": "lead-123",
                        "raw_data": {},
                        "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
                        "enriched_data": {},
                        "score": 85.0,
                        "stage": "qualified",
                        "messages": [],
                        "quotation_id": None,
                        "approval_status": None,
                        "errors": [],
                    }

                    result = await negotiation_node(state)

                    assert result["stage"] == "negotiating"
                    assert result["approval_status"] == "pending"
                    mock_hitl.assert_awaited_once_with("quote-789")


@pytest.mark.asyncio
async def test_negotiation_node_handles_missing_email():
    """Test that negotiation_node handles missing contact email."""
    state = {
        "lead_id": "lead-123",
        "raw_data": {},
        "cleaned_data": {"name": "Acme Corp"},
        "enriched_data": {},
        "score": 75.0,
        "stage": "qualified",
        "messages": [],
        "quotation_id": None,
        "approval_status": None,
        "errors": [],
    }

    result = await negotiation_node(state)

    assert result["stage"] == "negotiating"
    assert "No contact email for outreach" in result["errors"]


# Import json for test
import json