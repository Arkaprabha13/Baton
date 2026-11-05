"""Unit tests for core.config module."""

import os
import pytest
from pydantic import ValidationError

from core.config import Settings


def test_settings_loads_from_env(monkeypatch):
    """Test that settings loads correctly from environment variables."""
    # Monkeypatch all required env vars
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("DB_DSN", "postgresql+psycopg://user:pass@localhost:5432/test")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    # Create new Settings instance to pick up monkeypatched env
    settings = Settings()

    assert settings.supabase_url == "https://test.supabase.co"
    assert settings.supabase_service_key == "test-service-key"
    assert settings.db_dsn == "postgresql+psycopg://user:pass@localhost:5432/test"
    assert settings.nvidia_api_key == "test-nvidia-key"
    assert settings.groq_api_key == "test-groq-key"
    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.nvidia_rpm == 10
    assert settings.groq_rpm == 30
    assert settings.gemini_rpm == 15
    assert settings.maps_scraper_url == "http://localhost:8080"
    assert settings.gmail_mcp_url == "http://localhost:3100"
    assert settings.hitl_approval_timeout_seconds == 3600


def test_settings_raises_on_missing_supabase_url(monkeypatch):
    """Test that Settings raises ValidationError when supabase_url is missing."""
    # Provide all except supabase_url
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("DB_DSN", "postgresql+psycopg://user:pass@localhost:5432/test")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-nvidia-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    # Remove supabase_url if it was set
    monkeypatch.delenv("SUPABASE_URL", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings()

    errors = exc_info.value.errors()
    assert any(e["loc"] == ("supabase_url",) for e in errors)