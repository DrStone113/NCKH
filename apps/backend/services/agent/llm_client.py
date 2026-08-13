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

import asyncio
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

def _split_concatenated_tool_calls(name: str, arguments_str: str) -> list[tuple[str, str]]:
    known_tools = [
        "suggest_dish",
        "suggest_workout",
        "calculate_tdee",
        "search_food_nutrition",
        "create_plan",
        "append_plan_items",
        "query_rag",
        "search_medical_knowledge",
        "get_user_profile",
        "get_today_meals",
        "get_meal_log_range",
        "log_meal",
        "get_today_exercises",
        "get_exercise_log_range",
        "get_weight_history",
        "log_exercise",
        "log_weight",
        "get_lifestyle_logs",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "get_active_plan",
        "mark_plan_item_complete",
        "navigate_to_screen",
    ]
    
    # Try to find sequences of known tools in the concatenated name
    detected_tools = []
    temp_name = name
    while temp_name:
        matched = False
        for tool in known_tools:
            if temp_name.startswith(tool):
                detected_tools.append(tool)
                temp_name = temp_name[len(tool):]
                matched = True
                break
        if not matched:
            return []
            
    if not detected_tools or len(detected_tools) <= 1:
        return []
        
    # Split concatenated JSON objects like {"user_id": "..."}{"user_id": "..."}
    json_strs = []
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(arguments_str):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx != -1:
                json_strs.append(arguments_str[start_idx:i+1])
                start_idx = -1
                
    if len(json_strs) == len(detected_tools):
        return list(zip(detected_tools, json_strs))
        
    return []

def _parse_native_tool_calls(raw_calls: Iterable[Any]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for raw in raw_calls:
        if not isinstance(raw, dict):
            continue
        fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
        name = fn.get("name") if isinstance(fn, dict) else None
        if not isinstance(name, str) or not name:
            continue
            
        args_raw = fn.get("arguments") if isinstance(fn, dict) else None
        args_str = args_raw if isinstance(args_raw, str) else json.dumps(args_raw) if args_raw else ""
        
        split_calls = _split_concatenated_tool_calls(name, args_str)
        if split_calls:
            for s_name, s_args_str in split_calls:
                call_id = _new_call_id()
                args = _coerce_arguments(s_args_str)
                result.append(ToolCall(id=call_id, name=s_name, arguments=args))
            continue
            
        args = _coerce_arguments(args_raw)
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
        return _parse_xml_mode_tool_calls(full_text)
    if isinstance(parsed, list):
        items: list[Any] = parsed
    elif isinstance(parsed, dict):
        items = [parsed]
    else:
        return []
    return _parse_native_tool_calls(items)


#: Some models occasionally emit a tool call as *prose* instead of using the
#: native tool_calls channel, in a pseudo-XML dialect:
#:
#:     <tool_call>
#:     <function=suggest_dish>
#:     <parameter=meal_type>dinner</parameter>
#:     <parameter=target_kcal>750</parameter>
#:     </function>
#:     </tool_call>
#:
#: Observed at roughly 1-in-70 assistant turns. Without a parser the raw markup
#: is streamed straight to the user as chat text, which is what they see.
_XML_FUNCTION_RE = re.compile(
    r"<function\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*>(.*?)</function\s*>",
    re.DOTALL | re.IGNORECASE,
)
_XML_PARAMETER_RE = re.compile(
    r"<parameter\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*>(.*?)</parameter\s*>",
    re.DOTALL | re.IGNORECASE,
)


def _coerce_scalar(raw: str) -> Any:
    """Best-effort typing for XML parameter values, which are all strings."""
    text = raw.strip()
    if not text:
        return ""
    lowered = text.casefold()
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in ("null", "none"):
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    # JSON arrays/objects written inline, e.g. ["vegetarian"].
    if text[0] in "[{":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return text


def _parse_xml_mode_tool_calls(full_text: str) -> list[ToolCall]:
    """Recover tool calls a model wrote as pseudo-XML prose."""
    calls: list[ToolCall] = []
    for name, body in _XML_FUNCTION_RE.findall(full_text):
        arguments = {
            param: _coerce_scalar(value)
            for param, value in _XML_PARAMETER_RE.findall(body)
        }
        calls.append(ToolCall(id=_new_call_id(), name=name, arguments=arguments))
    if calls:
        logger.info(
            "Recovered %d tool call(s) emitted as XML prose instead of native "
            "tool_calls: %s",
            len(calls),
            [c.name for c in calls],
        )
    return calls


def _strip_tool_call_markup(text: str) -> str:
    """Remove tool-call markup so it never reaches the user as chat text."""
    cleaned = _TOOL_CALL_BLOCK_RE.sub("", text)
    cleaned = _XML_FUNCTION_RE.sub("", cleaned)
    # Drop stray opening/closing markers left behind by a truncated stream.
    cleaned = re.sub(r"</?tool_call\s*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?function[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</?parameter[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

# ---------------------------------------------------------------------------- #
# Streaming Content Iterator
# ---------------------------------------------------------------------------- #

class StreamingToken(str):
    """A string subclass that carries a token type (e.g. 'token' or 'thought')."""
    
    def __new__(cls, value: str, token_type: str = "token") -> StreamingToken:
        obj = str.__new__(cls, value)
        obj.token_type = token_type
        return obj


class StreamingContent(AsyncIterator[str]):
    def __init__(self, buffer: list[str], response_stream: Any, response_obj: LLMResponse) -> None:
        self.response_stream = response_stream
        self.response_obj = response_obj
        self.garbled_buffer: list[str] = []
        self.garbled_checked = False
        self._stream_finished = False
        
        # State machine variables for parsing <think>...</think> tags in the stream
        self._in_think = False
        self._tag_buffer = ""
        self._emit_queue: list[StreamingToken] = []
        # Set once the model starts writing a tool call as prose instead of
        # using the native tool_calls channel. Everything from that point on is
        # markup, not something the user should read, so it is captured here
        # and parsed at end-of-stream rather than emitted.
        self._in_tool_markup = False
        self._tool_markup = ""
        
        # Pre-process the initial buffer
        for token in buffer:
            self._process_content(token)

    def _emit_char(self, t_type: str, char: str) -> None:
        if self._emit_queue and self._emit_queue[-1].token_type == t_type:
            # Combine consecutive tokens of the same type
            new_val = self._emit_queue[-1] + char
            self._emit_queue[-1] = StreamingToken(new_val, t_type)
        else:
            self._emit_queue.append(StreamingToken(char, t_type))

    #: Openings that mean "the rest of this message is a tool call written as
    #: prose". Matching is done on a growing prefix so a tag split across
    #: several stream chunks is still caught.
    _TOOL_MARKUP_OPENERS = ("<tool_call>", "<function=")

    def _process_content(self, content: str) -> None:
        if self._in_tool_markup:
            self._tool_markup += content
            return

        if not self._tag_buffer and "<" not in content:
            t_type = "thought" if self._in_think else "token"
            self._emit_queue.append(StreamingToken(content, t_type))
            return

        for c in content:
            if self._in_tool_markup:
                self._tool_markup += c
                continue

            if self._tag_buffer:
                test_buffer = self._tag_buffer + c
                is_prefix_think = "<think>".startswith(test_buffer)
                is_prefix_unthink = "</think>".lower().startswith(test_buffer.lower())
                lowered = test_buffer.casefold()
                is_prefix_tool = any(
                    opener.startswith(lowered) for opener in self._TOOL_MARKUP_OPENERS
                )
                is_tool_open = any(
                    lowered == opener or lowered.startswith(opener)
                    for opener in self._TOOL_MARKUP_OPENERS
                )

                if is_tool_open:
                    # Stop emitting: the remainder of this message is markup.
                    self._in_tool_markup = True
                    self._tool_markup = test_buffer
                    self._tag_buffer = ""
                elif test_buffer == "<think>":
                    self._in_think = True
                    self._tag_buffer = ""
                elif test_buffer.casefold() == "</think>":
                    self._in_think = False
                    self._tag_buffer = ""
                elif is_prefix_think or is_prefix_unthink or is_prefix_tool:
                    self._tag_buffer = test_buffer
                else:
                    # Flush self._tag_buffer
                    for bc in self._tag_buffer:
                        self._emit_char("thought" if self._in_think else "token", bc)
                    self._tag_buffer = ""
                    # Process current character c
                    if c == "<":
                        self._tag_buffer = "<"
                    else:
                        self._emit_char("thought" if self._in_think else "token", c)
            else:
                if c == "<":
                    self._tag_buffer = "<"
                else:
                    self._emit_char("thought" if self._in_think else "token", c)

    def _flush_remaining(self) -> None:
        if self._in_tool_markup:
            # Markup is never shown to the user; __anext__ parses it instead.
            return
        if self._tag_buffer:
            t_type = "thought" if self._in_think else "token"
            for bc in self._tag_buffer:
                self._emit_char(t_type, bc)
            self._tag_buffer = ""

    def __aiter__(self) -> StreamingContent:
        return self

    async def __anext__(self) -> str:
        if self._emit_queue:
            val = self._emit_queue.pop(0)
            self.response_obj.full_text += val
            if not self.garbled_checked:
                self.garbled_buffer.append(val)
                if len(self.garbled_buffer) >= GARBLED_CHECK_TOKENS:
                    _check_garbled("".join(self.garbled_buffer))
                    self.garbled_checked = True
            return val

        if self._stream_finished:
            raise StopAsyncIteration

        try:
            while True:
                chunk = await self.response_stream.__anext__()
                if not chunk or not getattr(chunk, "choices", None):
                    continue
                choice = chunk.choices[0] if chunk.choices else None
                if not choice or not getattr(choice, "delta", None):
                    continue
                delta = choice.delta
                
                # Check for native tool calls
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

                # Process reasoning_content
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    self._emit_char("thought", reasoning)

                # Process normal content
                content = delta.content
                if content:
                    self._process_content(content)

                if self._emit_queue:
                    val = self._emit_queue.pop(0)
                    self.response_obj.full_text += val
                    if not self.garbled_checked:
                        self.garbled_buffer.append(val)
                        if len(self.garbled_buffer) >= GARBLED_CHECK_TOKENS:
                            _check_garbled("".join(self.garbled_buffer))
                            self.garbled_checked = True
                    return val
        except StopAsyncIteration:
            self._stream_finished = True
            self._flush_remaining()
            
            if hasattr(self, '_tool_calls_map') and self._tool_calls_map:
                self.response_obj.tool_calls = _parse_native_tool_calls(self._tool_calls_map.values())
            elif not self.response_obj.tool_calls:
                # The model wrote the call as prose instead of using the native
                # channel. It was withheld from the user during streaming; parse
                # it here so the turn still performs the action.
                markup = self._tool_markup
                if markup:
                    fallback = _parse_json_mode_tool_calls(markup)
                    if fallback:
                        self.response_obj.tool_calls = fallback
                elif "<tool_call>" in self.response_obj.full_text or \
                        "<function=" in self.response_obj.full_text:
                    text = self.response_obj.full_text
                    fallback = _parse_json_mode_tool_calls(text)
                    if fallback:
                        self.response_obj.tool_calls = fallback
                    self.response_obj.full_text = _strip_tool_call_markup(text)

            if not self.garbled_checked and self.garbled_buffer:
                _check_garbled("".join(self.garbled_buffer))
                self.garbled_checked = True
                
            if self._emit_queue:
                val = self._emit_queue.pop(0)
                self.response_obj.full_text += val
                return val
                
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
        prefill: str | None = None,
    ) -> LLMResponse:
        if not messages:
            raise ValueError("messages must be non-empty (precondition §9.1)")

        api_messages: list[dict[str, Any]] = []
        for i, msg in enumerate(messages):
            if msg.get("role") == "system" and i > 0:
                # Many Jinja chat templates (e.g. Qwen 3.5, Llama 3) disallow non-first system messages.
                api_messages.append({
                    "role": "user",
                    "content": f"[Chỉ dẫn hệ thống: {msg.get('content', '')}]",
                })
            else:
                api_messages.append(dict(msg))

        if prefill:
            api_messages.append({"role": "assistant", "content": prefill})

        # Determine candidate models (primary + fallback)
        from config import settings
        candidate_models = [self.model]
        fallback_model = settings.heavy_llm_model if self.model != settings.heavy_llm_model else settings.llm_model
        if fallback_model and fallback_model not in candidate_models:
            candidate_models.append(fallback_model)

        last_exc: Exception | None = None
        for model_idx, model_name in enumerate(candidate_models):
            for attempt in range(2):
                try:
                    kwargs: dict[str, Any] = {
                        "model": model_name,
                        "messages": api_messages,
                        "stream": bool(stream),
                    }
                    if tools:
                        kwargs["tools"] = tools

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
                        # Strip any leftover markup so it never reaches the user, even
                        # when the call could not be parsed back out.
                        return LLMResponse(
                            tool_calls=[], content_stream=None,
                            full_text=_strip_tool_call_markup(content),
                        )

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
                        if not chunk or not getattr(chunk, "choices", None):
                            continue
                        choice = chunk.choices[0] if chunk.choices else None
                        if not choice or not getattr(choice, "delta", None):
                            continue
                        delta = choice.delta
                        
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
                    if tools and ("<tool_call>" in buffered_text or "<function=" in buffered_text):
                        is_tool_call = True

                    if is_tool_call:
                        # Consume all remaining chunks
                        async for chunk in response_stream:
                            if not chunk or not getattr(chunk, "choices", None):
                                continue
                            choice = chunk.choices[0] if chunk.choices else None
                            if not choice or not getattr(choice, "delta", None):
                                continue
                            delta = choice.delta
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
                        return LLMResponse(
                            tool_calls=[], content_stream=None,
                            full_text=_strip_tool_call_markup(full_text),
                        )

                    # Normal text response - return real-time stream
                    llm_response = LLMResponse(tool_calls=[], content_stream=None, full_text="")
                    llm_response.content_stream = StreamingContent(buffered_tokens, response_stream, llm_response)
                    return llm_response

                except GarbledOutputError:
                    raise
                except (APIConnectionError, APITimeoutError, APIError, Exception) as exc:
                    last_exc = exc
                    logger.warning(
                        "LLM API error on model %s (attempt %d/2): %s",
                        model_name,
                        attempt + 1,
                        exc,
                    )
                    await asyncio.sleep(0.5 * (attempt + 1))

        if isinstance(last_exc, (APIConnectionError, APITimeoutError)):
            logger.warning("LLM API unavailable: %s", last_exc)
            raise LLMUnavailableError(f"LLM API not reachable: {last_exc!s}") from last_exc
        if isinstance(last_exc, APIError):
            status_code = getattr(last_exc, "status_code", None)
            if status_code and status_code >= 500:
                raise LLMUnavailableError(f"LLM API returned {status_code}") from last_exc
            raise LLMUnavailableError(f"LLM API error: {last_exc!s}") from last_exc
        if last_exc:
            raise LLMUnavailableError(f"LLM API unexpected error: {last_exc!s}") from last_exc
        raise LLMUnavailableError("LLM API call failed")

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
    "StreamingToken",
    "ToolCall",
]
