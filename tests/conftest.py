"""Pytest configuration for Baton tests.

Sets up dummy environment variables before any module imports.
"""

import os
import sys

# Set dummy environment variables BEFORE any module imports
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("DB_DSN", "postgresql+psycopg://user:pass@localhost:5432/test")
os.environ.setdefault("NVIDIA_API_KEY", "test-nvidia-key")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

# Ensure the project root is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))