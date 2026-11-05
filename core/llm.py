"""LLM routing layer for Baton.

Exposes a single chat() coroutine that picks the right provider based on
model argument, logs token usage to rate_limit_log, and enforces per-minute
rate limits.
"""

import time
from typing import Literal

from openai import AsyncOpenAI
from groq import AsyncGroq
from google import genai
from google.genai import types

from core.config import settings
from core.db import get_conn

ModelProvider = Literal["nemotron", "groq", "gemini"]

# Rate limiting state
_rate_limits: dict[str, list[float]] = {
    "nemotron": [],
    "groq": [],
    "gemini": [],
}


def _get_provider_config(model: ModelProvider) -> dict:
    """Get provider configuration dynamically from settings."""
    configs = {
        "nemotron": {
            "base_url": "https://integrate.api.nvidia.com/v1",
            "model_id": "nvidia/nemotron-3-super-120b-a12b",
            "rpm": settings.nvidia_rpm,
            "api_key": settings.nvidia_api_key,
        },
        "groq": {
            "base_url": None,
            "model_id": "llama-3.3-70b-versatile",
            "rpm": settings.groq_rpm,
            "api_key": settings.groq_api_key,
        },
        "gemini": {
            "base_url": None,
            "model_id": "gemini-2.0-flash",
            "rpm": settings.gemini_rpm,
            "api_key": settings.gemini_api_key,
        },
    }
    return configs[model]


def _check_rate_limit(provider: ModelProvider) -> None:
    """Check and enforce per-minute rate limit for a provider."""
    now = time.time()
    config = _get_provider_config(provider)
    rpm = config["rpm"]

    # Remove timestamps older than 60 seconds
    _rate_limits[provider] = [ts for ts in _rate_limits[provider] if now - ts < 60]

    if len(_rate_limits[provider]) >= rpm:
        oldest = _rate_limits[provider][0]
        wait_time = 60 - (now - oldest)
        if wait_time > 0:
            raise RuntimeError(
                f"Rate limit exceeded for {provider}. "
                f"Wait {wait_time:.1f} seconds."
            )

    _rate_limits[provider].append(now)


async def _log_usage(
    service: str, endpoint: str, tokens_in: int, tokens_out: int
) -> None:
    """Write a row to rate_limit_log via core.db.get_conn()."""
    async with get_conn() as conn:
        await conn.execute(
            """
            INSERT INTO rate_limit_log (service, endpoint, tokens_in, tokens_out, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (service, endpoint, tokens_in, tokens_out),
        )


async def chat(
    messages: list[dict],
    model: ModelProvider = "nemotron",
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    enable_thinking: bool = False,  # Nemotron only
) -> str:
    """Route to the correct LLM, log to rate_limit_log, return content string.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        model: Which provider to use ('nemotron', 'groq', 'gemini').
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in response.
        enable_thinking: Enable Nemotron reasoning mode.

    Returns:
        The assistant's response content as a string.

    Raises:
        RuntimeError: If rate limit is exceeded or provider is unknown.
    """
    _check_rate_limit(model)
    config = _get_provider_config(model)

    if model == "nemotron":
        return await _chat_nemotron(messages, config, temperature, max_tokens, enable_thinking)
    elif model == "groq":
        return await _chat_groq(messages, config, temperature, max_tokens)
    elif model == "gemini":
        return await _chat_gemini(messages, config, temperature, max_tokens)
    else:
        raise ValueError(f"Unknown model provider: {model}")


async def _chat_nemotron(
    messages: list[dict],
    config: dict,
    temperature: float,
    max_tokens: int,
    enable_thinking: bool,
) -> str:
    """Call Nemotron via OpenAI-compatible endpoint."""
    client = AsyncOpenAI(
        base_url=config["base_url"],
        api_key=config["api_key"],
    )

    extra_body = {}
    if enable_thinking:
        extra_body = {
            "chat_template_kwargs": {
                "enable_thinking": True,
                "low_effort": True,
            }
        }

    response = await client.chat.completions.create(
        model=config["model_id"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=extra_body,
    )

    content = response.choices[0].message.content or ""
    tokens_in = response.usage.prompt_tokens if response.usage else 0
    tokens_out = response.usage.completion_tokens if response.usage else 0

    await _log_usage("nemotron", "chat", tokens_in, tokens_out)
    return content


async def _chat_groq(
    messages: list[dict],
    config: dict,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Groq API."""
    client = AsyncGroq(api_key=config["api_key"])

    response = await client.chat.completions.create(
        model=config["model_id"],
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    content = response.choices[0].message.content or ""
    tokens_in = response.usage.prompt_tokens if response.usage else 0
    tokens_out = response.usage.completion_tokens if response.usage else 0

    await _log_usage("groq", "chat", tokens_in, tokens_out)
    return content


async def _chat_gemini(
    messages: list[dict],
    config: dict,
    temperature: float,
    max_tokens: int,
) -> str:
    """Call Gemini API via google-genai SDK."""
    client = genai.Client(api_key=config["api_key"])

    # Convert messages to Gemini format
    contents = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            contents.append(types.Content(parts=[types.Part(text=content)], role="user"))
        elif role == "assistant":
            contents.append(types.Content(parts=[types.Part(text=content)], role="model"))
        else:
            contents.append(types.Content(parts=[types.Part(text=content)], role="user"))

    response = await client.aio.models.generate_content(
        model=config["model_id"],
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )

    content = response.text or ""
    tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
    tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0

    await _log_usage("gemini", "chat", tokens_in, tokens_out)
    return content


async def embed(text: str) -> list[float]:
    """Embed text using Gemini text-embedding-004; returns vector(1536).

    Args:
        text: The text to embed.

    Returns:
        A list of 1536 floats representing the embedding vector.
    """
    client = genai.Client(api_key=settings.gemini_api_key)

    response = await client.aio.models.embed_content(
        model="text-embedding-004",
        contents=[text],
    )

    # Extract embedding from response
    embeddings = response.embeddings
    if embeddings and len(embeddings) > 0:
        vector = embeddings[0].values
        if len(vector) != 1536:
            raise ValueError(f"Expected 1536-dim vector, got {len(vector)}")
        return vector

    raise RuntimeError("No embedding returned from Gemini")