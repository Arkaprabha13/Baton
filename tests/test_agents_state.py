"""Unit tests for agents.state module."""

from agents.state import BatonState


def test_baton_state_instantiation():
    """Test that BatonState can be instantiated with all required keys."""
    state: BatonState = {
        "lead_id": "test-lead-123",
        "raw_data": {"name": "Acme Corp", "email": "test@acme.com"},
        "cleaned_data": {"name": "Acme Corp", "email": "test@acme.com"},
        "enriched_data": {"employee_count_estimate": "11-50"},
        "score": 75.0,
        "stage": "qualified",
        "messages": [{"role": "user", "content": "Hello"}],
        "quotation_id": "quote-456",
        "approval_status": "pending",
        "errors": [],
    }

    assert isinstance(state, dict)
    assert state["lead_id"] == "test-lead-123"
    assert state["raw_data"]["name"] == "Acme Corp"
    assert state["cleaned_data"]["email"] == "test@acme.com"
    assert state["enriched_data"]["employee_count_estimate"] == "11-50"
    assert state["score"] == 75.0
    assert state["stage"] == "qualified"
    assert len(state["messages"]) == 1
    assert state["quotation_id"] == "quote-456"
    assert state["approval_status"] == "pending"
    assert state["errors"] == []


def test_baton_state_empty_values():
    """Test that BatonState works with empty/default values."""
    state: BatonState = {
        "lead_id": "",
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

    assert isinstance(state, dict)
    assert state["lead_id"] == ""
    assert state["stage"] == "raw"
    assert state["quotation_id"] is None
    assert state["approval_status"] is None