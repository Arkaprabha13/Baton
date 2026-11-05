"""Unit tests for core.llm module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm import chat, embed, _log_usage, _rate_limits, ModelProvider


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limits before each test."""
    for key in _rate_limits:
        _rate_limits[key].clear()


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_groq_client():
    """Create a mock Groq client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello from Groq!"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_genai_client():
    """Create a mock Gemini client."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini!"
    mock_response.usage_metadata = MagicMock(
        prompt_token_count=10,
        candidates_token_count=5,
    )
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
    return mock_client


@pytest.fixture
def mock_genai_embed_client():
    """Create a mock Gemini client for embeddings."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.1] * 1536
    mock_response.embeddings = [mock_embedding]
    mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)
    return mock_client


async def test_chat_nemotron_calls_openai_with_correct_base_url(
    monkeypatch, mock_openai_client
):
    """Test that chat with model='nemotron' calls OpenAI with correct base_url."""
    with patch("core.llm.AsyncOpenAI", return_value=mock_openai_client) as mock_openai_class:
        with patch("core.llm._log_usage", new_callable=AsyncMock) as mock_log:
            with patch("core.llm.settings") as mock_settings:
                mock_settings.nvidia_api_key = "test-key"
                mock_settings.nvidia_rpm = 10
                mock_settings.groq_api_key = "test-key"
                mock_settings.groq_rpm = 30
                mock_settings.gemini_api_key = "test-key"
                mock_settings.gemini_rpm = 15

                result = await chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="nemotron",
                )

                assert result == "Hello!"
                mock_openai_class.assert_called_once_with(
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key="test-key",
                )
                mock_openai_client.chat.completions.create.assert_awaited_once()
                mock_log.assert_awaited_once_with("nemotron", "chat", 10, 5)


async def test_chat_groq_calls_groq_client(monkeypatch, mock_groq_client):
    """Test that chat with model='groq' calls Groq client."""
    with patch("core.llm.AsyncGroq", return_value=mock_groq_client) as mock_groq_class:
        with patch("core.llm._log_usage", new_callable=AsyncMock) as mock_log:
            with patch("core.llm.settings") as mock_settings:
                mock_settings.nvidia_api_key = "test-key"
                mock_settings.nvidia_rpm = 10
                mock_settings.groq_api_key = "test-groq-key"
                mock_settings.groq_rpm = 30
                mock_settings.gemini_api_key = "test-key"
                mock_settings.gemini_rpm = 15

                result = await chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="groq",
                )

                assert result == "Hello from Groq!"
                mock_groq_class.assert_called_once_with(api_key="test-groq-key")
                mock_groq_client.chat.completions.create.assert_awaited_once()
                mock_log.assert_awaited_once_with("groq", "chat", 10, 5)


async def test_chat_gemini_calls_genai_client(monkeypatch, mock_genai_client):
    """Test that chat with model='gemini' calls Gemini client."""
    with patch("core.llm.genai.Client", return_value=mock_genai_client) as mock_genai_class:
        with patch("core.llm._log_usage", new_callable=AsyncMock) as mock_log:
            with patch("core.llm.settings") as mock_settings:
                mock_settings.nvidia_api_key = "test-key"
                mock_settings.nvidia_rpm = 10
                mock_settings.groq_api_key = "test-key"
                mock_settings.groq_rpm = 30
                mock_settings.gemini_api_key = "test-gemini-key"
                mock_settings.gemini_rpm = 15

                result = await chat(
                    messages=[{"role": "user", "content": "hi"}],
                    model="gemini",
                )

                assert result == "Hello from Gemini!"
                mock_genai_class.assert_called_once_with(api_key="test-gemini-key")
                mock_genai_client.aio.models.generate_content.assert_awaited_once()
                mock_log.assert_awaited_once_with("gemini", "chat", 10, 5)


async def test_chat_logs_usage_per_call(monkeypatch, mock_openai_client):
    """Test that _log_usage is called once per chat() call."""
    with patch("core.llm.AsyncOpenAI", return_value=mock_openai_client):
        with patch("core.llm._log_usage", new_callable=AsyncMock) as mock_log:
            with patch("core.llm.settings") as mock_settings:
                mock_settings.nvidia_api_key = "test-key"
                mock_settings.nvidia_rpm = 10
                mock_settings.groq_api_key = "test-key"
                mock_settings.groq_rpm = 30
                mock_settings.gemini_api_key = "test-key"
                mock_settings.gemini_rpm = 15

                await chat(messages=[{"role": "user", "content": "hi"}], model="nemotron")
                await chat(messages=[{"role": "user", "content": "hi"}], model="nemotron")

                assert mock_log.await_count == 2


async def test_embed_returns_1536_dim_vector(monkeypatch, mock_genai_embed_client):
    """Test that embed() returns a 1536-dimension vector."""
    with patch("core.llm.genai.Client", return_value=mock_genai_embed_client):
        with patch("core.llm.settings") as mock_settings:
            mock_settings.gemini_api_key = "test-gemini-key"

            result = await embed("hello")

            assert isinstance(result, list)
            assert len(result) == 1536
            assert all(isinstance(x, float) for x in result)


async def test_embed_raises_on_wrong_dimension(monkeypatch):
    """Test that embed() raises if vector dimension is not 1536."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_embedding = MagicMock()
    mock_embedding.values = [0.1] * 100  # Wrong dimension
    mock_response.embeddings = [mock_embedding]
    mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)

    with patch("core.llm.genai.Client", return_value=mock_client):
        with patch("core.llm.settings") as mock_settings:
            mock_settings.gemini_api_key = "test-gemini-key"

            with pytest.raises(ValueError, match="Expected 1536-dim vector"):
                await embed("hello")


async def test_log_usage_inserts_row(monkeypatch):
    """Test that _log_usage inserts a row into rate_limit_log."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()

    with patch("core.llm.get_conn") as mock_get_conn:
        mock_get_conn.return_value.__aenter__.return_value = mock_conn

        await _log_usage("nemotron", "chat", 100, 50)

        mock_conn.execute.assert_awaited_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][0].strip().startswith("INSERT INTO rate_limit_log")
        assert call_args[0][1] == ("nemotron", "chat", 100, 50)