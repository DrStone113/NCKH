"""LLM client wrapping OpenAI API with function-calling support.

Implements §4.4 / §9.1 of ``backend/.kiro/specs/chatbot-redesign/design.md``.
Validates Requirements 1.5, 1.6, 7.6, 7.7.

Contract (see design §9.1):

- ``chat(messages, tools, stream=True)`` returns an :class:`LLMResponse`.
- When the model emits native ``tool_calls`` the response carries a
  non-empty ``tool_calls`` list and ``content_stream`` is ``None``.
- Otherwise ``tool_calls`` is empty and ``content_stream`` is an async
  iterator that yields the buffered text tokens; ``full_text`` holds the
  concatenated text.
- A JSON-mode fallback parses ``<tool_call>{...}</tool_call>`` blocks from
  the assistant text when ``tools`` were offered but the model produced no
  native ``tool_calls``.
- Garbled output (≥ 30% characters outside the printable ASCII / Vietnamese
  Unicode ranges within the first 8 token chunks) raises
  :class:`GarbledOutputError`.
- Connection failures raise :class:`LLMUnavailableError`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, APIError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------- #
# Constants
# ---------------------------------------------------------------------------- #

GARBLED_CHECK_TOKENS = 8
GARBLED_INVALID_RATIO = 0.30
DEFAULT_REQUEST_TIMEOUT_S = 180.0
DEFAULT_HEALTH_TIMEOUT_S = 5.0

_TOOL_CALL_BLOCK_RE = re.compile(
    r"<tool_call>\s*(.*?)\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)

# ---------------------------------------------------------------------------- #
# Errors
# ---------------------------------------------------------------------------- #

class LLMError(Exception):
    """Base class for errors raised by :class:`LLMClient`."""

class GarbledOutputError(LLMError):
    """Raised when the early token buffer contains too many invalid chars."""

class LLMUnavailableError(LLMError):
    """Raised when the underlying LLM service is not reachable."""

# ---------------------------------------------------------------------------- #
# Data classes
# ---------------------------------------------------------------------------- #

@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

@dataclass(slots=True)
class LLMResponse:
    tool_calls: list[ToolCall] = field(default_factory=list)
    content_stream: AsyncIterator[str] | None = None
    full_text: str = ""

# ---------------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------------- #

def _is_valid_char(ch: str) -> bool:
    if ch in "\n\t\r":
        return True
    code = ord(ch)
    if 0x0020 <= code <= 0x007E:
        return True
    if 0x00A0 <= code <= 0x024F:
        return True
    if 0x0300 <= code <= 0x036F:
        return True
    if 0x1E00 <= code <= 0x1EFF:
        return True
    return False

def _check_garbled(buffer_text: str) -> None:
    stripped = buffer_text.strip()
    if not stripped:
        return
    invalid = sum(1 for c in stripped if not _is_valid_char(c))
    ratio = invalid / len(stripped)
    if ratio >= GARBLED_INVALID_RATIO:
        logger.warning("Garbled LLM output detected: invalid_ratio=%.2f sample=%r", ratio, buffer_text[:60])
        raise GarbledOutputError(f"LLM output garbled (invalid chars {ratio:.0%} >= {GARBLED_INVALID_RATIO:.0%}); sample={buffer_text[:40]!r}")

def _coerce_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

def _new_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"

def _parse_native_tool_calls(raw_calls: Iterable[Any]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = fn.get("name") if isinstance(fn, dict) else None
        if not isinstance(name, str) or not name:
            continue
        args = _coerce_arguments(fn.get("arguments") if isinstance(fn, dict) else None)
        raw_id = raw.get("id")
        call_id = raw_id if isinstance(raw_id, str) and raw_id else _new_call_id()
        result.append(ToolCall(id=call_id, name=name, arguments=args))
    return result

def _parse_json_mode_tool_calls(full_text: str) -> list[ToolCall]:
    matches = _TOOL_CALL_BLOCK_RE.findall(full_text)
    if not matches:
        return []
    payload = matches[-1].strip()
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        logger.debug("JSON-mode fallback: failed to parse tool_call payload: %r", payload[:120])
        return []
    if isinstance(parsed, list):
        items: list[Any] = parsed
    elif isinstance(parsed, dict):
        items = [parsed]
    else:
        return []
    return _parse_native_tool_calls(items)

# ---------------------------------------------------------------------------- #
# Streaming Content Iterator
# ---------------------------------------------------------------------------- #

class StreamingContent(AsyncIterator[str]):
    def __init__(self, buffer: list[str], response_stream: Any, response_obj: LLMResponse) -> None:
        self.buffer = buffer
        self.response_stream = response_stream
        self.response_obj = response_obj
        self.buffer_idx = 0
        self.garbled_buffer: list[str] = []
        self.garbled_checked = False

    def __aiter__(self) -> StreamingContent:
        return self

    async def __anext__(self) -> str:
        if self.buffer_idx < len(self.buffer):
            token = self.buffer[self.buffer_idx]
            self.buffer_idx += 1
            self.response_obj.full_text += token
            if not self.garbled_checked:
                self.garbled_buffer.append(token)
                if len(self.garbled_buffer) >= GARBLED_CHECK_TOKENS:
                    _check_garbled("".join(self.garbled_buffer))
                    self.garbled_checked = True
            return token

        try:
            while True:
                chunk = await self.response_stream.__anext__()
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                if delta.tool_calls:
                    if not hasattr(self, '_tool_calls_map'):
                        self._tool_calls_map = {}
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in self._tool_calls_map:
                            self._tool_calls_map[idx] = {
                                "id": tc_chunk.id or _new_call_id(),
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                self._tool_calls_map[idx]["function"]["name"] += tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                self._tool_calls_map[idx]["function"]["arguments"] += tc_chunk.function.arguments

                content = delta.content
                if content:
                    self.response_obj.full_text += content
                    if not self.garbled_checked:
                        self.garbled_buffer.append(content)
                        if len(self.garbled_buffer) >= GARBLED_CHECK_TOKENS:
                            _check_garbled("".join(self.garbled_buffer))
                            self.garbled_checked = True
                    return content
        except StopAsyncIteration:
            if hasattr(self, '_tool_calls_map') and self._tool_calls_map:
                self.response_obj.tool_calls = _parse_native_tool_calls(self._tool_calls_map.values())
            elif not self.response_obj.tool_calls and "<tool_call>" in self.response_obj.full_text:
                fallback = _parse_json_mode_tool_calls(self.response_obj.full_text)
                if fallback:
                    self.response_obj.tool_calls = fallback

            if not self.garbled_checked and self.garbled_buffer:
                _check_garbled("".join(self.garbled_buffer))
                self.garbled_checked = True
            raise StopAsyncIteration


# ---------------------------------------------------------------------------- #
# Client
# ---------------------------------------------------------------------------- #

class LLMClient:
    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "",
        *,
        request_timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
        health_timeout_s: float = DEFAULT_HEALTH_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key if api_key else "dummy-key"
        self.request_timeout_s = request_timeout_s
        self.health_timeout_s = health_timeout_s
        self._external_client = client
        self.openai = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=self._external_client,
            timeout=self.request_timeout_s,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        stream: bool = True,
    ) -> LLMResponse:
        if not messages:
            raise ValueError("messages must be non-empty (precondition §9.1)")

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": bool(stream),
        }
        if tools:
            kwargs["tools"] = tools

        try:
            if not stream:
                # Non-streaming fallback
                response = await self.openai.chat.completions.create(**kwargs)
                choice = response.choices[0].message
                content = choice.content or ""
                _check_garbled(content)
                native_tool_calls = []
                if choice.tool_calls:
                    raw_calls = []
                    for tc in choice.tool_calls:
                        raw_calls.append({
                            "id": tc.id,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        })
                    native_tool_calls = _parse_native_tool_calls(raw_calls)
                
                if native_tool_calls:
                    return LLMResponse(tool_calls=native_tool_calls, content_stream=None, full_text="")
                if tools:
                    fallback = _parse_json_mode_tool_calls(content)
                    if fallback:
                        return LLMResponse(tool_calls=fallback, content_stream=None, full_text="")
                return LLMResponse(tool_calls=[], content_stream=None, full_text=content)

            # Streaming mode (stream=True)
            raw_stream = await self.openai.chat.completions.create(**kwargs)
            response_stream = raw_stream.__aiter__()
            
            # Read first few chunks to determine if it is a tool call
            buffered_chunks = []
            buffered_tokens = []
            buffered_text = ""
            native_tool_calls_detected = False
            tool_calls_map = {}
            
            # Iterate through response_stream to fill the buffer
            async for chunk in response_stream:
                buffered_chunks.append(chunk)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                
                # Check for native tool calls
                if delta.tool_calls:
                    native_tool_calls_detected = True
                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc_chunk.id or _new_call_id(),
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_map[idx]["function"]["name"] += tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                tool_calls_map[idx]["function"]["arguments"] += tc_chunk.function.arguments
                
                content = delta.content
                if content:
                    buffered_tokens.append(content)
                    buffered_text += content
                
                # Stop buffering if native tool call detected, non-tool text started (≥2 tokens, ≥5 chars), or buffer full
                if native_tool_calls_detected:
                    break
                if len(buffered_tokens) >= 2 and len(buffered_text) >= 5 and not buffered_text.strip().startswith("<"):
                    break
                if len(buffered_tokens) >= 8 and len(buffered_text) >= 20:
                    break
            
            # Run early garbled check on the buffer
            _check_garbled("".join(buffered_tokens))

            # Determine if this is a tool call response
            is_tool_call = native_tool_calls_detected
            if tools and "<tool_call>" in buffered_text:
                is_tool_call = True

            if is_tool_call:
                # Consume all remaining chunks
                async for chunk in response_stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            if idx not in tool_calls_map:
                                tool_calls_map[idx] = {
                                    "id": tc_chunk.id or _new_call_id(),
                                    "function": {"name": "", "arguments": ""}
                                }
                            if tc_chunk.function:
                                if tc_chunk.function.name:
                                    tool_calls_map[idx]["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tool_calls_map[idx]["function"]["arguments"] += tc_chunk.function.arguments
                    content = delta.content
                    if content:
                        buffered_tokens.append(content)
                
                full_text = "".join(buffered_tokens)
                if tool_calls_map:
                    native_tool_calls = _parse_native_tool_calls(tool_calls_map.values())
                    return LLMResponse(tool_calls=native_tool_calls, content_stream=None, full_text="")
                if tools:
                    fallback = _parse_json_mode_tool_calls(full_text)
                    if fallback:
                        return LLMResponse(tool_calls=fallback, content_stream=None, full_text="")
                
                # Fallback if somehow it didn't match tool calls
                return LLMResponse(tool_calls=[], content_stream=None, full_text=full_text)

            # Normal text response - return real-time stream
            llm_response = LLMResponse(tool_calls=[], content_stream=None, full_text="")
            llm_response.content_stream = StreamingContent(buffered_tokens, response_stream, llm_response)
            return llm_response

        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("LLM API unavailable: %s", exc)
            raise LLMUnavailableError(f"LLM API not reachable: {exc!s}") from exc
        except APIError as exc:
            status_code = getattr(exc, "status_code", None)
            if status_code and status_code >= 500:
                raise LLMUnavailableError(f"LLM API returned {status_code}") from exc
            raise LLMUnavailableError(f"LLM API error: {exc!s}") from exc
        except Exception as exc:
            if isinstance(exc, GarbledOutputError):
                raise
            logger.warning("Unexpected error: %s", exc)
            raise LLMUnavailableError(f"LLM API unexpected error: {exc!s}") from exc

    async def health_check(self) -> bool:
        try:
            custom_openai = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                http_client=self._external_client,
                timeout=self.health_timeout_s,
                max_retries=0
            )
            await custom_openai.models.list()
            return True
        except Exception:
            return False

__all__ = [
    "DEFAULT_HEALTH_TIMEOUT_S",
    "DEFAULT_REQUEST_TIMEOUT_S",
    "GARBLED_CHECK_TOKENS",
    "GARBLED_INVALID_RATIO",
    "GarbledOutputError",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMUnavailableError",
    "ToolCall",
]
