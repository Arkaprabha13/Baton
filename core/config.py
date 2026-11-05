"""Configuration settings for Baton.

Loads all runtime settings from environment variables via pydantic-settings.
Fails fast on missing required secrets.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Supabase
    supabase_url: str
    supabase_service_key: str
    db_dsn: str  # postgresql+psycopg://...

    # LLM API Keys
    nvidia_api_key: str
    groq_api_key: str
    gemini_api_key: str

    # Rate limits (per-minute)
    nvidia_rpm: int = 10
    groq_rpm: int = 30
    gemini_rpm: int = 15

    # Services
    maps_scraper_url: str = "http://localhost:8080"
    gmail_mcp_url: str = "http://localhost:3100"

    # HITL
    hitl_approval_timeout_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()