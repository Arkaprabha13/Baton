---
name: nemotron-config
description: Configures OpenCode to use NVIDIA Nemotron models via the OpenAI-compatible endpoint. Use this skill when setting up the LLM provider in core/llm.py.
---
# Nemotron Configuration
- Provider: Use the `openai` Python SDK.
- Base URL: `https://integrate.api.nvidia.com/v1`
- Model ID: `nvidia/nemotron-3-super-120b-a12b`
- Context Limit: 1,000,000 tokens.
- Reasoning Toggle: To enable reasoning and bypass the OpenCode UI bug, pass `extra_body={"chat_template_kwargs": {"enable_thinking": True, "low_effort": True}}` in the API call.
