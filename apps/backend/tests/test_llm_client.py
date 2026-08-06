"""Unit tests for `services/agent/llm_client.py`.

Validates Requirements 1.5, 1.6, 7.7 by mocking AsyncOpenAI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from openai import APIConnectionError, APITimeoutError, APIError

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.llm_client import (
    GarbledOutputError,
    LLMClient,
    LLMUnavailableError,
    ToolCall,
)

# --------------------------------------------------------------------------- #
# Mocks
# --------------------------------------------------------------------------- #

class MockDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

class MockChoice:
    def __init__(self, delta):
        self.delta = delta

class MockChunk:
    def __init__(self, choices):
        self.choices = choices

class MockToolCallFunction:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments

class MockToolCallChunk:
    def __init__(self, index, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function

class MockStream:
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for c in self.chunks:
            yield MockChunk([MockChoice(MockDelta(**c))])

def _make_llm_client() -> LLMClient:
    return LLMClient(
        model="hpx/hpx_minimax_3_free",
        base_url="https://api.vilao.ai/v1",
        api_key="sk-63fa6e22f6cbd26d2ec0209fed6af4c6d49eab748908bca235c539e5f2e81be6"
    )

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_chat_parses_native_tool_calls() -> None:
    client = _make_llm_client()
    
    # Simulate OpenAI SSE tool call streaming
    stream = MockStream([
        {"tool_calls": [MockToolCallChunk(index=0, id="call_42", function=MockToolCallFunction(name="get_user_profile", arguments=""))]},
        {"tool_calls": [MockToolCallChunk(index=0, function=MockToolCallFunction(arguments='{"user_id":'))]},
        {"tool_calls": [MockToolCallChunk(index=0, function=MockToolCallFunction(arguments='"u1"}'))]},
    ])
    
    client.openai.chat.completions.create = AsyncMock(return_value=stream)
    
    response = await client.chat(
        messages=[{"role": "user", "content": "ping"}],
        tools=[{"type": "function", "function": {"name": "get_user_profile", "parameters": {"type": "object"}}}],
    )

    assert response.tool_calls == [
        ToolCall(id="call_42", name="get_user_profile", arguments={"user_id": "u1"})
    ]
    assert response.content_stream is None
    assert response.full_text == ""


@pytest.mark.asyncio
async def test_chat_streams_plain_text_chunks() -> None:
    client = _make_llm_client()
    
    chunks = ["Xin", " chào", " bạn", "!"]
    stream = MockStream([{"content": c} for c in chunks])
    
    client.openai.chat.completions.create = AsyncMock(return_value=stream)
    
    response = await client.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
    )

    assert response.tool_calls == []
    assert response.content_stream is not None

    streamed = [token async for token in response.content_stream]
    assert streamed == chunks
    assert response.full_text == "Xin chào bạn!"


@pytest.mark.asyncio
async def test_chat_raises_garbled_output_error_on_noise() -> None:
    client = _make_llm_client()
    
    noise_chunks = [
        "\x00\x01\x02\x03",
        "\x04\x05\x06\x07",
        "\x08\x0b\x0c\x0e",
        "\x0f\x10\x11\x12",
        "\x13\x14\x15\x16",
        "\x17\x18\x19\x1a",
        "\x1b\x1c\x1d\x1e",
        "\x1f\x7f\x80\x81",
    ]
    
    stream = MockStream([{"content": c} for c in noise_chunks])
    client.openai.chat.completions.create = AsyncMock(return_value=stream)
    
    with pytest.raises(GarbledOutputError):
        await client.chat(messages=[{"role": "user", "content": "ping"}])


@pytest.mark.asyncio
async def test_chat_json_mode_fallback_parses_tool_call_block() -> None:
    client = _make_llm_client()
    
    block = '<tool_call>{"name":"suggest_dish","arguments":{"meal_type":"lunch","target_kcal":600}}</tool_call>'
    stream = MockStream([
        {"content": "Đang chọn món... "},
        {"content": block},
    ])
    
    client.openai.chat.completions.create = AsyncMock(return_value=stream)
    
    response = await client.chat(
        messages=[{"role": "user", "content": "gợi ý món trưa"}],
        tools=[{"type": "function", "function": {"name": "suggest_dish", "parameters": {"type": "object"}}}],
    )

    assert len(response.tool_calls) == 1
    call = response.tool_calls[0]
    assert call.name == "suggest_dish"
    assert call.arguments == {"meal_type": "lunch", "target_kcal": 600}
    assert response.content_stream is None
    assert response.full_text == ""


@pytest.mark.asyncio
async def test_chat_raises_llm_unavailable_on_connect_error() -> None:
    client = _make_llm_client()
    
    mock_request = MagicMock()
    client.openai.chat.completions.create = AsyncMock(side_effect=APIConnectionError(request=mock_request))
    
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "ping"}])


@pytest.mark.asyncio
async def test_chat_raises_llm_unavailable_on_5xx() -> None:
    client = _make_llm_client()
    
    mock_request = MagicMock()
    mock_response = MagicMock(status_code=503)
    client.openai.chat.completions.create = AsyncMock(side_effect=APIError("error", request=mock_request, body=None))
    
    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "ping"}])


@pytest.mark.asyncio
async def test_chat_rejects_empty_messages() -> None:
    client = _make_llm_client()
    with pytest.raises(ValueError):
        await client.chat(messages=[], tools=None)
