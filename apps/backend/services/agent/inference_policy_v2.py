"""Versioned cost-latency-quality routing for one chat turn.

Safety and data-integrity validators are hard constraints. The numeric score
only chooses among routes that already satisfy those constraints. The LinUCB
component is shadow-only and is never updated from live health traffic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from services.agent.context_planner import (
    ContextPlan,
    EvidenceRequirement,
    Intent,
    IntentClassification,
    RagPolicy,
)
from services.agent.cost_governor import TurnCostLimits
from services.agent.turn_router import TurnPlan


POLICY_VERSION = "inference-policy-v2.0.0"


class InferenceRoute(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    LIGHT_LLM = "LIGHT_LLM"
    HEAVY_LLM = "HEAVY_LLM"


class RetrievalMode(str, Enum):
    NONE = "NONE"
    EXACT_FIRST = "EXACT_FIRST"
    LEXICAL_FIRST = "LEXICAL_FIRST"
    HYBRID = "HYBRID"


_SAFE_PREFETCH_TOOLS = frozenset(
    {
        "get_user_profile",
        "get_today_meals",
        "get_today_exercises",
        "get_lifestyle_logs",
        "get_active_plan",
        "get_active_plan_v2",
    }
)


@dataclass(frozen=True, slots=True)
class InferenceDecisionV2:
    policy_version: str
    route: InferenceRoute
    primary_intent: str
    confidence: float
    required_sources: tuple[str, ...]
    optional_sources: tuple[str, ...]
    forbidden_sources: tuple[str, ...]
    prefetch_tools: tuple[str, ...]
    permitted_tools: tuple[str, ...]
    retrieval_mode: RetrievalMode
    max_llm_calls: int
    max_output_tokens: int | None
    history_turn_limit: int
    validators: tuple[str, ...]
    escalation_conditions: tuple[str, ...]
    clarification_required: bool
    expected_quality_risk: float
    estimated_relative_cost: float
    estimated_relative_latency: float

    def to_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "route": self.route.value,
            "primary_intent": self.primary_intent,
            "confidence": round(self.confidence, 4),
            "required_sources": list(self.required_sources),
            "optional_sources": list(self.optional_sources),
            "forbidden_sources": list(self.forbidden_sources),
            "prefetch_tools": list(self.prefetch_tools),
            "permitted_tools": list(self.permitted_tools),
            "retrieval_mode": self.retrieval_mode.value,
            "max_llm_calls": self.max_llm_calls,
            "max_output_tokens": self.max_output_tokens,
            "history_turn_limit": self.history_turn_limit,
            "validators": list(self.validators),
            "escalation_conditions": list(self.escalation_conditions),
            "clarification_required": self.clarification_required,
            "objective": {
                "expected_quality_risk": round(self.expected_quality_risk, 4),
                "estimated_relative_cost": round(self.estimated_relative_cost, 4),
                "estimated_relative_latency": round(self.estimated_relative_latency, 4),
            },
        }

    def feature_vector(self) -> tuple[float, ...]:
        return (
            1.0,
            self.confidence,
            1.0 if self.clarification_required else 0.0,
            min(len(self.required_sources), 8) / 8.0,
            min(len(self.permitted_tools), 8) / 8.0,
            1.0 if self.retrieval_mode == RetrievalMode.HYBRID else 0.0,
            min(len(self.validators), 7) / 7.0,
            self.expected_quality_risk,
        )


def decide_inference(
    classification: IntentClassification,
    context_plan: ContextPlan,
    turn_plan: TurnPlan,
    limits: TurnCostLimits,
) -> InferenceDecisionV2:
    evidence_required = (
        context_plan.evidence_requirement != EvidenceRequirement.NONE
    )
    if turn_plan.use_heavy_model or evidence_required:
        route = InferenceRoute.HEAVY_LLM
    else:
        route = InferenceRoute.LIGHT_LLM

    if context_plan.rag_policy == RagPolicy.REQUIRED:
        retrieval = RetrievalMode.HYBRID
    elif classification.primary_intent in {
        Intent.FOOD_NUTRITION_LOOKUP,
        Intent.MEAL_RECOMMENDATION,
        Intent.WORKOUT_RECOMMENDATION,
    }:
        retrieval = RetrievalMode.EXACT_FIRST
    elif context_plan.rag_policy == RagPolicy.OPTIONAL:
        retrieval = RetrievalMode.LEXICAL_FIRST
    else:
        retrieval = RetrievalMode.NONE

    high_confidence = (
        classification.confidence >= 0.85
        and not classification.clarification_required
    )
    prefetch = tuple(
        sorted(
            tool
            for tool in context_plan.permitted_tools
            if high_confidence and tool in _SAFE_PREFETCH_TOOLS
        )
    )
    validator_values = [item.value for item in context_plan.required_validators]
    if classification.explicit_write:
        validator_values.append("PERSISTENCE_CONFIRMATION")
    validators = tuple(dict.fromkeys(validator_values))
    quality_risk = min(
        1.0,
        (1.0 - classification.confidence)
        + (0.25 if evidence_required else 0.0)
        + (0.25 if classification.clarification_required else 0.0),
    )
    relative_cost = {
        InferenceRoute.DETERMINISTIC: 0.0,
        InferenceRoute.LIGHT_LLM: 0.35,
        InferenceRoute.HEAVY_LLM: 1.0,
    }[route]
    relative_latency = relative_cost + 0.12 * len(prefetch)

    return InferenceDecisionV2(
        policy_version=POLICY_VERSION,
        route=route,
        primary_intent=classification.primary_intent.value,
        confidence=classification.confidence,
        required_sources=tuple(item.value for item in context_plan.required_sources),
        optional_sources=tuple(item.value for item in context_plan.optional_sources),
        forbidden_sources=tuple(item.value for item in context_plan.forbidden_sources),
        prefetch_tools=prefetch,
        permitted_tools=context_plan.permitted_tools,
        retrieval_mode=retrieval,
        max_llm_calls=limits.max_llm_calls,
        max_output_tokens=limits.max_output_tokens,
        history_turn_limit=limits.history_turn_limit,
        validators=validators,
        escalation_conditions=(
            "MISSING_REQUIRED_SOURCE",
            "VALIDATOR_FAILED",
            "TOOL_FAILURE",
            "LOW_ROUTER_CONFIDENCE",
        ),
        clarification_required=classification.clarification_required,
        expected_quality_risk=quality_risk,
        estimated_relative_cost=relative_cost,
        estimated_relative_latency=relative_latency,
    )


@dataclass(frozen=True, slots=True)
class ShadowBanditRecommendation:
    arm: InferenceRoute
    scores: dict[str, float]
    propensities: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": "TRUSTED_SHADOW_ONLY",
            "arm": self.arm.value,
            "scores": {key: round(value, 6) for key, value in self.scores.items()},
            "propensities": {
                key: round(value, 6) for key, value in self.propensities.items()
            },
        }


class DiagonalLinUCBShadow:
    """Low-overhead constrained LinUCB approximation for offline learning.

    Runtime calls only :meth:`recommend`. Updates are deliberately exposed as
    :meth:`update_offline` so production request outcomes cannot silently alter
    routing policy.
    """

    def __init__(self, *, dimension: int = 8, alpha: float = 0.15) -> None:
        self.dimension = dimension
        self.alpha = alpha
        self._a = {
            arm: [1.0] * dimension
            for arm in InferenceRoute
        }
        self._b = {
            arm: [0.0] * dimension
            for arm in InferenceRoute
        }

    def recommend(
        self,
        features: Iterable[float],
        *,
        allowed_arms: Iterable[InferenceRoute],
    ) -> ShadowBanditRecommendation:
        vector = tuple(float(item) for item in features)
        if len(vector) != self.dimension:
            raise ValueError("INVALID_FEATURE_VECTOR")
        arms = tuple(dict.fromkeys(allowed_arms))
        if not arms:
            raise ValueError("NO_ALLOWED_ARMS")
        scores: dict[str, float] = {}
        for arm in arms:
            theta = [b / a for a, b in zip(self._a[arm], self._b[arm])]
            mean = sum(weight * value for weight, value in zip(theta, vector))
            uncertainty = self.alpha * math.sqrt(
                sum(value * value / a for value, a in zip(vector, self._a[arm]))
            )
            scores[arm.value] = mean + uncertainty
        best = max(arms, key=lambda arm: (scores[arm.value], arm.value))
        propensities = _softmax(scores)
        return ShadowBanditRecommendation(best, scores, propensities)

    def update_offline(
        self,
        arm: InferenceRoute,
        features: Iterable[float],
        reward: float,
    ) -> None:
        vector = tuple(float(item) for item in features)
        if len(vector) != self.dimension:
            raise ValueError("INVALID_FEATURE_VECTOR")
        bounded_reward = max(-1.0, min(1.0, float(reward)))
        for index, value in enumerate(vector):
            self._a[arm][index] += value * value
            self._b[arm][index] += bounded_reward * value


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    peak = max(scores.values())
    weights = {key: math.exp(value - peak) for key, value in scores.items()}
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


__all__ = [
    "DiagonalLinUCBShadow",
    "InferenceDecisionV2",
    "InferenceRoute",
    "POLICY_VERSION",
    "RetrievalMode",
    "ShadowBanditRecommendation",
    "decide_inference",
]
