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


@dataclass(frozen=True, slots=True)
class ResearchExecutionResult:
    final_response: str
    model_actual: str
    tool_calls: tuple[dict[str, Any], ...]


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
    ) -> None:
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

        return ResearchLLMResponse(
            content=str(getattr(message, "content", "") or ""),
            model_actual=str(getattr(response, "model", "") or config.model),
            tool_calls=tuple(parsed_calls),
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

        if not response.tool_calls:
            return ResearchExecutionResult(
                final_response=response.content,
                model_actual=actual_model,
                tool_calls=tuple(recorded_calls),
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
