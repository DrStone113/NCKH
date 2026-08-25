"""Version-controlled intent-to-source/tool policy matrix."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .contracts import (
    EvidenceRequirement,
    Freshness,
    Intent,
    MATRIX_VERSION,
    MemoryPolicy,
    RagPolicy,
    SourceId,
    ValidatorId,
)


ALL_KNOWN_TOOLS = frozenset({
    "get_user_profile", "get_today_meals", "get_meal_log_range", "log_meal",
    "calculate_tdee", "search_food_nutrition", "suggest_dish",
    "get_today_exercises", "get_exercise_log_range", "get_weight_history",
    "log_exercise", "log_weight", "suggest_workout", "get_lifestyle_logs",
    "log_lifestyle", "set_lifestyle_reminder", "get_active_plan",
    "mark_plan_item_complete", "navigate_to_screen", "create_long_term_plan",
    "create_plan", "append_plan_items", "query_rag", "search_medical_knowledge",
})


@dataclass(frozen=True, slots=True)
class IntentPolicy:
    required: tuple[SourceId, ...] = ()
    optional: tuple[SourceId, ...] = ()
    forbidden: tuple[SourceId, ...] = ()
    freshness: tuple[tuple[SourceId, Freshness], ...] = ()
    calculations: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    rag: RagPolicy = RagPolicy.FORBIDDEN
    memory: MemoryPolicy = MemoryPolicy.FORBIDDEN
    evidence: EvidenceRequirement = EvidenceRequirement.NONE
    validators: tuple[ValidatorId, ...] = ()


P = IntentPolicy
S = SourceId
V = ValidatorId
F = Freshness


INTENT_SOURCE_MATRIX: Mapping[Intent, IntentPolicy] = MappingProxyType({
    Intent.DAILY_NUTRITION_STATUS: P(
        required=(S.CANONICAL_NUTRITION, S.DAILY_NUTRITION), optional=(S.PROFILE,),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY, S.EXERCISE_HISTORY),
        freshness=((S.CANONICAL_NUTRITION, F.LIVE), (S.DAILY_NUTRITION, F.LIVE)),
        calculations=("DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1",),
        tools=("get_today_meals", "calculate_tdee"),
        validators=(V.NUMERIC_CONSISTENCY, V.CURRENT_STATE_FRESHNESS),
    ),
    Intent.MEAL_RECOMMENDATION: P(
        required=(S.PROFILE, S.NUTRITION_SAFETY, S.CONFIRMED_MEMORY, S.DISH_DATABASE),
        optional=(S.CANONICAL_NUTRITION, S.DAILY_NUTRITION, S.ACTIVE_PLAN, S.SAVED_MEALS),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY),
        freshness=((S.PROFILE, F.LIVE), (S.NUTRITION_SAFETY, F.LIVE), (S.CONFIRMED_MEMORY, F.ANY), (S.DISH_DATABASE, F.ANY)),
        tools=("get_user_profile", "suggest_dish", "get_today_meals", "get_active_plan"),
        memory=MemoryPolicy.REQUIRED,
        validators=(V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT, V.CURRENT_STATE_FRESHNESS),
    ),
    Intent.FOOD_NUTRITION_LOOKUP: P(
        required=(S.FOOD_DATABASE,), optional=(S.PROFILE,),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY, S.EXERCISE_HISTORY),
        freshness=((S.FOOD_DATABASE, F.ANY),), tools=("search_food_nutrition",),
        validators=(V.NUMERIC_CONSISTENCY,),
    ),
    Intent.MEAL_OR_DIET_EVALUATION: P(
        required=(S.CANONICAL_NUTRITION, S.DAILY_NUTRITION, S.NUTRITION_SAFETY),
        optional=(S.PROFILE, S.CONFIRMED_MEMORY, S.ACTIVE_PLAN),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.EXERCISE_HISTORY),
        freshness=((S.CANONICAL_NUTRITION, F.LIVE), (S.DAILY_NUTRITION, F.LIVE), (S.NUTRITION_SAFETY, F.LIVE)),
        calculations=("DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1",),
        tools=("get_today_meals", "calculate_tdee", "get_active_plan"),
        memory=MemoryPolicy.OPTIONAL,
        validators=(V.NUMERIC_CONSISTENCY, V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT, V.CURRENT_STATE_FRESHNESS),
    ),
    Intent.WEIGHT_PROGRESS: P(
        required=(S.WEIGHT_HISTORY,), optional=(S.PROFILE, S.LIFESTYLE),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY),
        freshness=((S.WEIGHT_HISTORY, F.RECENT),), calculations=("WEIGHT_TREND",),
        tools=("get_weight_history",), validators=(V.NUMERIC_CONSISTENCY, V.CURRENT_STATE_FRESHNESS),
    ),
    Intent.EXERCISE_RECOVERY: P(
        required=(S.TODAY_EXERCISE, S.LIFESTYLE), optional=(S.CANONICAL_NUTRITION, S.DAILY_NUTRITION, S.PROFILE),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY),
        freshness=((S.TODAY_EXERCISE, F.TODAY), (S.LIFESTYLE, F.RECENT)),
        tools=("get_today_exercises", "get_lifestyle_logs", "get_today_meals"),
        validators=(V.CURRENT_STATE_FRESHNESS, V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT),
    ),
    Intent.WORKOUT_RECOMMENDATION: P(
        required=(S.PROFILE, S.TODAY_EXERCISE), optional=(S.EXERCISE_HISTORY, S.LIFESTYLE, S.ACTIVE_PLAN),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY),
        freshness=((S.PROFILE, F.LIVE), (S.TODAY_EXERCISE, F.TODAY)),
        tools=("get_user_profile", "get_today_exercises", "suggest_workout"),
        validators=(V.CURRENT_STATE_FRESHNESS, V.PLAN_CONSISTENCY),
    ),
    Intent.PLAN_MANAGEMENT: P(
        required=(S.ACTIVE_PLAN,), optional=(S.PROFILE, S.CANONICAL_NUTRITION, S.NUTRITION_SAFETY),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY, S.EXERCISE_HISTORY),
        freshness=((S.ACTIVE_PLAN, F.LIVE),),
        tools=("get_active_plan", "create_long_term_plan", "mark_plan_item_complete"),
        validators=(V.PLAN_CONSISTENCY, V.CURRENT_STATE_FRESHNESS, V.PERSISTENCE_CONFIRMATION),
    ),
    Intent.PROFILE_OR_CONSTRAINT_UPDATE: P(
        required=(S.PROFILE,), optional=(S.NUTRITION_SAFETY, S.CONFIRMED_MEMORY),
        forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY, S.EXERCISE_HISTORY),
        freshness=((S.PROFILE, F.LIVE),), tools=("get_user_profile", "navigate_to_screen"),
        memory=MemoryPolicy.OPTIONAL,
        validators=(V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT, V.PERSISTENCE_CONFIRMATION),
    ),
    Intent.GENERAL_NUTRITION_KNOWLEDGE: P(
        required=(S.RAG,), optional=(S.PROFILE,),
        forbidden=(S.MEAL_HISTORY, S.EXERCISE_HISTORY, S.DAILY_NUTRITION, S.MEDICAL_EVIDENCE),
        freshness=((S.RAG, F.ANY),), tools=("query_rag",), rag=RagPolicy.REQUIRED,
        evidence=EvidenceRequirement.GROUNDED, validators=(V.EVIDENCE_GROUNDING,),
    ),
    Intent.EVIDENCE_HEALTH_QUESTION: P(
        required=(S.MEDICAL_EVIDENCE, S.NUTRITION_SAFETY), optional=(S.PROFILE,),
        forbidden=(S.RAG, S.MEAL_HISTORY, S.EXERCISE_HISTORY, S.DAILY_NUTRITION),
        freshness=((S.MEDICAL_EVIDENCE, F.RECENT), (S.NUTRITION_SAFETY, F.LIVE)),
        tools=("search_medical_knowledge",), rag=RagPolicy.REQUIRED,
        evidence=EvidenceRequirement.SAFETY_GROUNDED,
        validators=(V.EVIDENCE_GROUNDING, V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT),
    ),
    Intent.FOLLOWUP_EXPLANATION: P(
        required=(S.RECENT_CONVERSATION,), optional=(S.CONFIRMED_MEMORY, S.DISH_DATABASE, S.FOOD_DATABASE),
        forbidden=(S.MEAL_HISTORY, S.EXERCISE_HISTORY, S.MEDICAL_EVIDENCE),
        freshness=((S.RECENT_CONVERSATION, F.RECENT),), tools=(), rag=RagPolicy.OPTIONAL,
        memory=MemoryPolicy.REQUIRED, validators=(V.NUMERIC_CONSISTENCY, V.DIETARY_CONSTRAINT, V.ALLERGY_CONSTRAINT),
    ),
    Intent.APP_ACTION: P(
        required=(), optional=(S.PROFILE,), forbidden=(S.RAG, S.MEDICAL_EVIDENCE, S.MEAL_HISTORY, S.EXERCISE_HISTORY),
        tools=("log_meal", "log_weight", "log_exercise", "log_lifestyle", "set_lifestyle_reminder", "navigate_to_screen"),
        validators=(V.PERSISTENCE_CONFIRMATION,),
    ),
    Intent.SMALLTALK_OR_OTHER: P(
        required=(), optional=(),
        forbidden=(S.NUTRITION_SAFETY, S.DAILY_NUTRITION, S.TODAY_EXERCISE, S.MEAL_HISTORY, S.EXERCISE_HISTORY, S.WEIGHT_HISTORY, S.LIFESTYLE, S.ACTIVE_PLAN, S.SAVED_MEALS, S.CONFIRMED_MEMORY, S.RAG, S.MEDICAL_EVIDENCE, S.CANONICAL_NUTRITION),
        tools=(), memory=MemoryPolicy.FORBIDDEN,
    ),
})


def matrix_payload() -> dict[str, object]:
    return {
        "matrix_version": MATRIX_VERSION,
        "intents": {
            intent.value: {
                "required_sources": [item.value for item in policy.required],
                "optional_sources": [item.value for item in policy.optional],
                "forbidden_sources": [item.value for item in policy.forbidden],
                "freshness": {source.value: freshness.value for source, freshness in policy.freshness},
                "tools": list(policy.tools),
                "rag_policy": policy.rag.value,
                "memory_policy": policy.memory.value,
                "validators": [item.value for item in policy.validators],
            }
            for intent, policy in INTENT_SOURCE_MATRIX.items()
        },
    }


__all__ = ["ALL_KNOWN_TOOLS", "INTENT_SOURCE_MATRIX", "IntentPolicy", "matrix_payload"]
