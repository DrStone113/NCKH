"""Hard, testable per-turn limits for paid LLM work.

The governor never changes health, allergy, consent or persistence rules.  It
only bounds how much model context/output/call fan-out a routed turn may buy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import settings
from services.agent.turn_router import CHITCHAT, COMPLEX, TurnPlan


@dataclass(frozen=True, slots=True)
class TurnCostLimits:
    mode: str
    prompt_mode: str
    max_llm_calls: int
    max_output_tokens: int | None
    history_turn_limit: int

    def estimated_input_tokens(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
    ) -> int:
        # Conservative dependency-free estimate for budget telemetry. Provider
        # usage remains authoritative when it is available.
        import json

        characters = len(json.dumps(messages, ensure_ascii=False, default=str))
        if tools:
            characters += len(json.dumps(tools, ensure_ascii=False, default=str))
        return (characters + 3) // 4


def limits_for_turn(plan: TurnPlan) -> TurnCostLimits:
    if settings.llm_cost_optimization_mode == "off":
        return TurnCostLimits(
            mode="off",
            prompt_mode=plan.prompt_mode,
            max_llm_calls=max(1, plan.max_steps + 1),
            max_output_tokens=None,
            history_turn_limit=settings.max_history_turns,
        )
    if plan.tier == CHITCHAT:
        return TurnCostLimits(
            mode="optimized",
            prompt_mode="light",
            max_llm_calls=1,
            max_output_tokens=settings.llm_chitchat_max_output_tokens,
            history_turn_limit=0,
        )
    if plan.tier == COMPLEX:
        return TurnCostLimits(
            mode="optimized",
            prompt_mode="compact",
            max_llm_calls=settings.llm_complex_max_calls,
            max_output_tokens=settings.llm_complex_max_output_tokens,
            history_turn_limit=settings.llm_complex_history_turns,
        )
    return TurnCostLimits(
        mode="optimized",
        prompt_mode="compact",
        max_llm_calls=settings.llm_simple_max_calls,
        max_output_tokens=settings.llm_simple_max_output_tokens,
        history_turn_limit=settings.llm_simple_history_turns,
    )


__all__ = ["TurnCostLimits", "limits_for_turn"]
