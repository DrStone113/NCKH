"""Fixed-model LLM execution for research mode."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from openai import AsyncOpenAI

from services.agent.tool_registry import ToolRegistry
from services.experiment.config import ExperimentConfig
from services.experiment.errors import ExperimentError, safe_error_detail
from services.experiment.tools import execute_research_tool


@dataclass(frozen=True, slots=True)
class ResearchToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ResearchLLMResponse:
    content: str
    model_actual: str
    tool_calls: tuple[ResearchToolCall, ...] = ()
    token_usage: dict[str, int] | None = None
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ResearchExecutionResult:
    final_response: str
    model_actual: str
    tool_calls: tuple[dict[str, Any], ...]
    token_usage: dict[str, int] | None = None
    finish_reasons: tuple[str | None, ...] = ()


class ResearchCompletionClient(Protocol):
    async def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        config: ExperimentConfig,
    ) -> ResearchLLMResponse: ...


class FixedOpenAIResearchClient:
    """One configured model, one attempt, explicit generation parameters."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        openai_client: Any | None = None,
        timeout_seconds: float = 120.0,
        reasoning_effort: str | None = None,
    ) -> None:
        self._reasoning_effort = (
            reasoning_effort.strip().lower() if reasoning_effort else None
        )
        if self._reasoning_effort not in {
            None,
            "none",
            "low",
            "medium",
            "high",
            "max",
        }:
            raise ValueError(
                "reasoning_effort must be none, low, medium, high, or max"
            )
        self._client = openai_client or AsyncOpenAI(
            base_url=base_url.rstrip("/"),
            api_key=api_key or "dummy-key",
            timeout=timeout_seconds,
            max_retries=0,
        )

    @classmethod
    def from_backend_settings(cls) -> "FixedOpenAIResearchClient":
        from config import settings

        return cls(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            reasoning_effort=settings.llm_reasoning_effort,
        )

    async def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
        config: ExperimentConfig,
    ) -> ResearchLLMResponse:
        kwargs: dict[str, Any] = {
            "model": config.model,
            "messages": [dict(message) for message in messages],
            "stream": False,
            "temperature": config.temperature,
            "seed": config.seed,
            "max_tokens": config.max_tokens,
        }
        if tools:
            kwargs["tools"] = list(tools)
            kwargs["tool_choice"] = "auto"
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort

        try:
            # There is intentionally no retry and no alternative model here.
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ExperimentError(
                "EXPERIMENT_LLM_FAILED", safe_error_detail(exc)
            ) from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ExperimentError("EXPERIMENT_LLM_INVALID_RESPONSE", "no choices")
        message = choices[0].message
        finish_reason = getattr(choices[0], "finish_reason", None)

        parsed_calls: list[ResearchToolCall] = []
        for index, raw_call in enumerate(getattr(message, "tool_calls", None) or []):
            function = getattr(raw_call, "function", None)
            name = str(getattr(function, "name", "") or "").strip()
            raw_arguments = getattr(function, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ExperimentError(
                    "EXPERIMENT_INVALID_TOOL_ARGUMENTS", name or f"tool-{index}"
                ) from exc
            if not name or not isinstance(arguments, dict):
                raise ExperimentError(
                    "EXPERIMENT_INVALID_TOOL_ARGUMENTS", name or f"tool-{index}"
                )
            parsed_calls.append(
                ResearchToolCall(
                    id=str(getattr(raw_call, "id", "") or f"call-{index}"),
                    name=name,
                    arguments=arguments,
                )
            )

        usage = getattr(response, "usage", None)
        token_usage: dict[str, int] = {}
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = (
                usage.get(field)
                if isinstance(usage, dict)
                else getattr(usage, field, None)
            )
            if isinstance(value, int) and value >= 0:
                token_usage[field] = value

        return ResearchLLMResponse(
            content=str(getattr(message, "content", "") or ""),
            model_actual=str(getattr(response, "model", "") or config.model),
            tool_calls=tuple(parsed_calls),
            token_usage=token_usage or None,
            finish_reason=(str(finish_reason) if finish_reason is not None else None),
        )


async def execute_fixed_agent(
    *,
    client: ResearchCompletionClient,
    initial_messages: Sequence[dict[str, Any]],
    tool_schemas: Sequence[dict[str, Any]],
    tool_registry: ToolRegistry,
    config: ExperimentConfig,
) -> ResearchExecutionResult:
    """Run the fixed LLM/tool loop for at most ``max_agent_steps`` calls."""

    messages = [dict(message) for message in initial_messages]
    recorded_calls: list[dict[str, Any]] = []
    actual_model: str | None = None
    accumulated_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    has_token_usage = False
    finish_reasons: list[str | None] = []

    for step in range(1, config.max_agent_steps + 1):
        response = await client.complete(
            messages=messages,
            tools=tool_schemas,
            config=config,
        )
        if actual_model is None:
            actual_model = response.model_actual
        elif actual_model != response.model_actual:
            raise ExperimentError(
                "EXPERIMENT_MODEL_CHANGED",
                f"{actual_model} -> {response.model_actual}",
            )

        if response.token_usage:
            has_token_usage = True
            for field in accumulated_usage:
                accumulated_usage[field] += int(response.token_usage.get(field, 0))
        finish_reasons.append(response.finish_reason)

        if not response.tool_calls:
            return ResearchExecutionResult(
                final_response=response.content,
                model_actual=actual_model,
                tool_calls=tuple(recorded_calls),
                token_usage=(dict(accumulated_usage) if has_token_usage else None),
                finish_reasons=tuple(finish_reasons),
            )

        if not tool_schemas:
            raise ExperimentError("EXPERIMENT_TOOL_NOT_ALLOWED")
        if step == config.max_agent_steps:
            raise ExperimentError("EXPERIMENT_MAX_STEPS_EXCEEDED")

        assistant_calls = []
        for call in response.tool_calls:
            assistant_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                }
            )
        messages.append(
            {
                "role": "assistant",
                "content": response.content,
                "tool_calls": assistant_calls,
            }
        )

        for call in response.tool_calls:
            started = time.perf_counter()
            try:
                result = await execute_research_tool(
                    tool_registry, call.name, call.arguments
                )
            except ExperimentError as exc:
                recorded_calls.append(
                    {
                        "step": step,
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": None,
                        "ok": False,
                        "error": str(exc),
                        "latency_ms": round(
                            (time.perf_counter() - started) * 1000, 3
                        ),
                    }
                )
                raise

            recorded_calls.append(
                {
                    "step": step,
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                    "result": result,
                    "ok": True,
                    "error": None,
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000, 3
                    ),
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(
                        result,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )

    raise ExperimentError("EXPERIMENT_MAX_STEPS_EXCEEDED")


__all__ = [
    "FixedOpenAIResearchClient",
    "ResearchCompletionClient",
    "ResearchExecutionResult",
    "ResearchLLMResponse",
    "ResearchToolCall",
    "execute_fixed_agent",
]
