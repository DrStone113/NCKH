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
from openai import APIConnectionError, APITimeoutError, APIError, APIStatusError

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.llm_client import (
    GarbledOutputError,
    LLMClient,
    LLMUnavailableError,
    ToolCall,
)
from config import Settings

# --------------------------------------------------------------------------- #
# Mocks
# --------------------------------------------------------------------------- #

class MockDelta:
    def __init__(
        self,
        content=None,
        tool_calls=None,
        reasoning_content=None,
        reasoning=None,
    ):
        self.content = content
        self.tool_calls = tool_calls
        self.reasoning_content = reasoning_content
        self.reasoning = reasoning

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
    # These tests drive the client with mocked streams and never reach the
    # network, so a placeholder key is enough — a real one would just leak
    # into git history.
    return LLMClient(
        model="hpx/hpx_minimax_3_free",
        base_url="https://api.vilao.ai/v1",
        api_key="sk-test-not-a-real-key"
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
async def test_chat_does_not_retry_or_fallback_on_insufficient_balance() -> None:
    client = _make_llm_client()

    mock_request = MagicMock()
    mock_response = MagicMock(status_code=402, request=mock_request)
    client.openai.chat.completions.create = AsyncMock(
        side_effect=APIStatusError(
            "insufficient balance",
            response=mock_response,
            body={"error": {"code": "INSUFFICIENT_BALANCE"}},
        )
    )

    with pytest.raises(LLMUnavailableError, match=r"\(402\)") as caught:
        await client.chat(messages=[{"role": "user", "content": "ping"}])

    assert client.openai.chat.completions.create.await_count == 1
    assert caught.value.status_code == 402
    assert caught.value.reason_code == "QUOTA_EXHAUSTED"
    assert client.provider_status == "quota_exhausted"


@pytest.mark.asyncio
async def test_restricted_client_never_falls_back_to_an_answer_model() -> None:
    client = _make_llm_client()
    client.allow_model_fallback = False
    mock_request = MagicMock()
    client.openai.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=mock_request)
    )

    with pytest.raises(LLMUnavailableError):
        await client.chat(
            messages=[{"role": "user", "content": "classify"}],
            tools=None,
            stream=False,
        )

    assert client.openai.chat.completions.create.await_count == 2
    assert {
        call.kwargs["model"]
        for call in client.openai.chat.completions.create.await_args_list
    } == {client.model}


@pytest.mark.asyncio
async def test_cost_optimized_client_does_not_retry_a_failed_paid_request() -> None:
    client = LLMClient(
        model="small-model",
        base_url="https://api.vilao.ai/v1",
        api_key="sk-test-not-a-real-key",
        allow_model_fallback=False,
        max_attempts_per_model=1,
    )
    mock_request = MagicMock()
    client.openai.chat.completions.create = AsyncMock(
        side_effect=APIConnectionError(request=mock_request)
    )

    with pytest.raises(LLMUnavailableError):
        await client.chat(messages=[{"role": "user", "content": "ping"}])

    assert client.openai.chat.completions.create.await_count == 1


@pytest.mark.asyncio
async def test_chat_rejects_empty_messages() -> None:
    client = _make_llm_client()
    with pytest.raises(ValueError):
        await client.chat(messages=[], tools=None)


# ---------------------------------------------------------------------------
# Tool calls emitted as prose instead of via the native tool_calls channel
#
# Observed in production at ~1 in 70 assistant turns: instead of using the
# native channel the model writes the call as pseudo-XML in ordinary content.
# Before this was handled, the raw markup streamed straight to the user, who
# saw "<tool_call><function=suggest_dish><parameter=meal_type>dinner..." in the
# chat bubble, and the tool never ran.
# ---------------------------------------------------------------------------

XML_TOOL_CALL = (
    "<tool_call>\n"
    "<function=suggest_dish>\n"
    "<parameter=meal_type>dinner</parameter>\n"
    "<parameter=target_kcal>750</parameter>\n"
    "</function>\n"
    "</tool_call>"
)


def test_parse_xml_mode_tool_calls_extracts_name_and_typed_args() -> None:
    from services.agent.llm_client import _parse_xml_mode_tool_calls

    calls = _parse_xml_mode_tool_calls(XML_TOOL_CALL)

    assert len(calls) == 1
    assert calls[0].name == "suggest_dish"
    # target_kcal must be numeric, not the string "750".
    assert calls[0].arguments == {"meal_type": "dinner", "target_kcal": 750}


def test_parse_xml_mode_handles_lists_and_booleans() -> None:
    from services.agent.llm_client import _parse_xml_mode_tool_calls

    calls = _parse_xml_mode_tool_calls(
        "<function=suggest_dish>"
        '<parameter=dietary_restrictions>["vegetarian"]</parameter>'
        "<parameter=strict>true</parameter>"
        "</function>"
    )

    assert calls[0].arguments == {
        "dietary_restrictions": ["vegetarian"],
        "strict": True,
    }


def test_json_mode_parser_falls_back_to_xml() -> None:
    """<tool_call> wrapping XML (not JSON) must still resolve."""
    from services.agent.llm_client import _parse_json_mode_tool_calls

    calls = _parse_json_mode_tool_calls(XML_TOOL_CALL)

    assert [c.name for c in calls] == ["suggest_dish"]


def test_strip_tool_call_markup_removes_all_variants() -> None:
    from services.agent.llm_client import _strip_tool_call_markup

    text = f"Gợi ý cho bạn một bữa tối:{XML_TOOL_CALL}"
    cleaned = _strip_tool_call_markup(text)

    assert cleaned == "Gợi ý cho bạn một bữa tối:"
    for marker in ("<tool_call>", "<function=", "<parameter=", "</function>"):
        assert marker not in cleaned


def test_strip_tool_call_markup_handles_truncated_stream() -> None:
    """A cut-off stream leaves dangling tags; none may reach the user."""
    from services.agent.llm_client import _strip_tool_call_markup

    cleaned = _strip_tool_call_markup(
        "Bữa tối nhé:<tool_call>\n<function=suggest_dish>\n<parameter=meal_type>din"
    )

    assert "<" not in cleaned
    assert cleaned.startswith("Bữa tối nhé:")


@pytest.mark.asyncio
async def test_streaming_withholds_xml_tool_markup_from_user() -> None:
    """The user must see the prose, never the markup, and the call must run.

    Chunking matters here: the model writes several tokens of ordinary prose
    first, which makes ``chat`` stop buffering and switch to live streaming.
    The markup then arrives mid-stream, which is exactly the case that used to
    put ``<tool_call><function=...>`` into the chat bubble.
    """
    client = _make_llm_client()

    stream = MockStream([
        {"content": "Gợi ý "},
        {"content": "cho bạn "},
        {"content": "một bữa tối:"},
        {"content": "<tool_call>\n<function=suggest_dish>\n"},
        {"content": "<parameter=meal_type>dinner</parameter>\n"},
        {"content": "<parameter=target_kcal>750</parameter>\n"},
        {"content": "</function>\n</tool_call>"},
    ])
    client.openai.chat.completions.create = AsyncMock(return_value=stream)

    response = await client.chat(
        messages=[{"role": "user", "content": "goi y bua toi"}],
        tools=[{"type": "function", "function": {"name": "suggest_dish"}}],
    )

    emitted = []
    if response.content_stream is not None:
        async for token in response.content_stream:
            if getattr(token, "token_type", "token") != "thought":
                emitted.append(str(token))
    shown = "".join(emitted) or response.full_text

    for marker in ("<tool_call>", "<function=", "<parameter="):
        assert marker not in shown, f"{marker} leaked to the user: {shown!r}"
    assert shown.strip() == "Gợi ý cho bạn một bữa tối:"
    assert [c.name for c in response.tool_calls] == ["suggest_dish"]
    assert response.tool_calls[0].arguments == {
        "meal_type": "dinner",
        "target_kcal": 750,
    }




@pytest.mark.asyncio
async def test_streaming_still_emits_ordinary_angle_brackets() -> None:
    """Guard against over-eager filtering of legitimate '<' in prose."""
    client = _make_llm_client()

    stream = MockStream([
        {"content": "BMI "},
        {"content": "< 18.5 "},
        {"content": "là thiếu cân"},
    ])
    client.openai.chat.completions.create = AsyncMock(return_value=stream)

    response = await client.chat(
        messages=[{"role": "user", "content": "bmi bao nhieu la thieu can"}],
        tools=[{"type": "function", "function": {"name": "suggest_dish"}}],
    )

    emitted = []
    if response.content_stream is not None:
        async for token in response.content_stream:
            if getattr(token, "token_type", "token") != "thought":
                emitted.append(str(token))

    assert "< 18.5" in "".join(emitted)


@pytest.mark.asyncio
async def test_non_first_system_messages_sanitized_to_user() -> None:
    """Non-first system messages must be converted to user role for Jinja template compatibility."""
    client = _make_llm_client()
    stream = MockStream([{"content": "ok"}])
    client.openai.chat.completions.create = AsyncMock(return_value=stream)

    messages = [
        {"role": "system", "content": "System prompt"},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "system", "content": "Secondary instruction"},
    ]

    await client.chat(messages=messages)

    call_kwargs = client.openai.chat.completions.create.call_args.kwargs
    api_messages = call_kwargs["messages"]

    assert api_messages[0]["role"] == "system"
    assert api_messages[0]["content"] == "System prompt"
    assert api_messages[1]["role"] == "user"
    assert api_messages[2]["role"] == "assistant"
    assert api_messages[3]["role"] == "user"
    assert "Secondary instruction" in api_messages[3]["content"]


@pytest.mark.asyncio
async def test_chat_forwards_configured_reasoning_effort() -> None:
    client = LLMClient(
        model="qwen3:8b",
        base_url="http://127.0.0.1:11434/v1",
        reasoning_effort="none",
    )
    stream = MockStream([{"content": "ok"}])
    client.openai.chat.completions.create = AsyncMock(return_value=stream)

    await client.chat(messages=[{"role": "user", "content": "ping"}])

    call_kwargs = client.openai.chat.completions.create.call_args.kwargs
    assert call_kwargs["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_streaming_reasoning_fields_never_enter_visible_full_text() -> None:
    client = _make_llm_client()
    stream = MockStream(
        [
            {"reasoning": "private reasoning"},
            {"reasoning_content": "more private reasoning"},
            {"content": "visible answer"},
        ]
    )
    client.openai.chat.completions.create = AsyncMock(return_value=stream)

    response = await client.chat(messages=[{"role": "user", "content": "think"}])
    tokens = [token async for token in response.content_stream]

    assert [token.token_type for token in tokens] == ["thought", "thought", "token"]
    assert "".join(str(token) for token in tokens[:-1]) == (
        "private reasoningmore private reasoning"
    )
    assert str(tokens[-1]) == "visible answer"
    assert response.full_text == "visible answer"


def test_heavy_reasoning_effort_can_override_regular_client() -> None:
    configured = Settings(
        _env_file=None,
        llm_reasoning_effort="none",
        heavy_llm_reasoning_effort="high",
    )

    assert configured.effective_heavy_llm_reasoning_effort == "high"


def test_heavy_reasoning_effort_falls_back_to_regular_client() -> None:
    configured = Settings(
        _env_file=None,
        llm_reasoning_effort="none",
        heavy_llm_reasoning_effort="",
    )

    assert configured.effective_heavy_llm_reasoning_effort == "none"

