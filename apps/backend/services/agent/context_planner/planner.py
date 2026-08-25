"""Deterministic D3.0 planner and structural shadow bundle builder."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import time
from typing import Any, Iterable, Mapping

from .classifier import IntentClassification, classify_intent
from .contracts import (
    BUNDLE_VERSION, PLAN_VERSION, ContextBundle, ContextPlan, ContextSection,
    DataStatus, EvidenceRequirement, Freshness, FreshnessRequirement,
    MemoryPolicy, MissingDataAction, RagPolicy, SourceId, ValidatorId,
)
from .matrix import ALL_KNOWN_TOOLS, INTENT_SOURCE_MATRIX
from .registry import SOURCE_REGISTRY


_WRITE_TOOL_BY_ACTION = {
    "LOG_MEAL": "log_meal", "LOG_WEIGHT": "log_weight",
    "LOG_EXERCISE": "log_exercise", "LOG_LIFESTYLE": "log_lifestyle",
    "NAVIGATE": "navigate_to_screen",
}
_WRITE_TOOLS = frozenset({
    "log_meal", "log_weight", "log_exercise", "log_lifestyle",
    "set_lifestyle_reminder", "navigate_to_screen", "create_long_term_plan",
    "mark_plan_item_complete", "create_plan", "append_plan_items",
})
_LOW_LEVEL_PLAN_TOOLS = frozenset({"create_plan", "append_plan_items"})
_SECTION_BY_SOURCE = {
    SourceId.PROFILE: "USER_PROFILE", SourceId.NUTRITION_SAFETY: "HARD_CONSTRAINTS",
    SourceId.DAILY_NUTRITION: "TODAY_STATUS", SourceId.CANONICAL_NUTRITION: "TODAY_STATUS",
    SourceId.TODAY_EXERCISE: "RECENT_EXERCISE", SourceId.EXERCISE_HISTORY: "RECENT_EXERCISE",
    SourceId.MEAL_HISTORY: "RELEVANT_HISTORY", SourceId.WEIGHT_HISTORY: "WEIGHT_PROGRESS",
    SourceId.LIFESTYLE: "LIFESTYLE", SourceId.ACTIVE_PLAN: "ACTIVE_PLAN",
    SourceId.SAVED_MEALS: "RELEVANT_MEMORY", SourceId.CONFIRMED_MEMORY: "RELEVANT_MEMORY",
    SourceId.RECENT_CONVERSATION: "RECENT_CONVERSATION", SourceId.FOOD_DATABASE: "FOOD_REFERENCE",
    SourceId.DISH_DATABASE: "DISH_REFERENCE", SourceId.RAG: "EVIDENCE",
    SourceId.MEDICAL_EVIDENCE: "EVIDENCE",
}


@dataclass(frozen=True, slots=True)
class ShadowPlanningResult:
    classification: IntentClassification
    plan: ContextPlan
    bundle: ContextBundle
    latency_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification.to_dict(),
            "plan": self.plan.to_dict(), "bundle": self.bundle.to_dict(),
            "latency_ms": round(self.latency_ms, 3),
        }


def _ordered(enum_type: type, values: Iterable[Any]) -> tuple[Any, ...]:
    wanted = set(values)
    return tuple(item for item in enum_type if item in wanted)


def _stronger_rag(values: Iterable[RagPolicy]) -> RagPolicy:
    items = set(values)
    return RagPolicy.REQUIRED if RagPolicy.REQUIRED in items else RagPolicy.OPTIONAL if RagPolicy.OPTIONAL in items else RagPolicy.FORBIDDEN


def _stronger_memory(values: Iterable[MemoryPolicy]) -> MemoryPolicy:
    items = set(values)
    return MemoryPolicy.REQUIRED if MemoryPolicy.REQUIRED in items else MemoryPolicy.OPTIONAL if MemoryPolicy.OPTIONAL in items else MemoryPolicy.FORBIDDEN


def _status(value: Any) -> DataStatus:
    raw = str(value or "NOT_LOADED").upper()
    return DataStatus(raw) if raw in DataStatus._value2member_map_ else DataStatus.NOT_LOADED


class ContextPlanner:
    def __init__(self, *, context_budget_characters: int = 6000) -> None:
        self.context_budget_characters = context_budget_characters

    def create_plan(self, query: str, *, available_tool_names: Iterable[str] = ALL_KNOWN_TOOLS) -> tuple[IntentClassification, ContextPlan]:
        classification = classify_intent(query)
        intents = (classification.primary_intent, *classification.secondary_intents)
        policies = [INTENT_SOURCE_MATRIX[item] for item in intents]
        required = set().union(*(set(item.required) for item in policies))
        optional = set().union(*(set(item.optional) for item in policies)) - required
        requested = required | optional
        forbidden = set().union(*(set(item.forbidden) for item in policies)) - requested

        freshness: dict[SourceId, Freshness] = {}
        rank = {Freshness.ANY: 0, Freshness.RECENT: 1, Freshness.TODAY: 2, Freshness.LIVE: 3}
        for policy in policies:
            for source, value in policy.freshness:
                if source not in freshness or rank[value] > rank[freshness[source]]:
                    freshness[source] = value
        for source in required:
            freshness.setdefault(source, Freshness.ANY)

        offered = set(available_tool_names)
        tools = set().union(*(set(item.tools) for item in policies)) & offered
        tools -= _WRITE_TOOLS
        if classification.explicit_write and classification.action_kind in _WRITE_TOOL_BY_ACTION:
            tool = _WRITE_TOOL_BY_ACTION[classification.action_kind]
            if tool in offered:
                tools.add(tool)
        tools -= _LOW_LEVEL_PLAN_TOOLS
        evidence_values = {item.evidence for item in policies}
        evidence = EvidenceRequirement.SAFETY_GROUNDED if EvidenceRequirement.SAFETY_GROUNDED in evidence_values else EvidenceRequirement.GROUNDED if EvidenceRequirement.GROUNDED in evidence_values else EvidenceRequirement.NONE
        plan = ContextPlan(
            plan_version=PLAN_VERSION, primary_intent=classification.primary_intent,
            secondary_intents=classification.secondary_intents,
            required_sources=_ordered(SourceId, required), optional_sources=_ordered(SourceId, optional),
            forbidden_sources=_ordered(SourceId, forbidden),
            freshness_requirements=tuple(FreshnessRequirement(item, freshness[item]) for item in SourceId if item in freshness),
            required_calculations=tuple(dict.fromkeys(calc for policy in policies for calc in policy.calculations)),
            permitted_tools=tuple(sorted(tools)), forbidden_tools=tuple(sorted(offered - tools)),
            rag_policy=_stronger_rag(item.rag for item in policies),
            memory_policy=_stronger_memory(item.memory for item in policies),
            evidence_requirement=evidence,
            required_validators=_ordered(ValidatorId, (validator for policy in policies for validator in policy.validators)),
            clarification_required=classification.clarification_required,
            planner_reason_codes=classification.reason_codes,
        )
        return classification, plan

    def resolve_statuses(self, user_context: Any, memory_context: Any) -> dict[SourceId, DataStatus]:
        statuses = {source: DataStatus.NOT_LOADED for source in SourceId}
        statuses[SourceId.FOOD_DATABASE] = DataStatus.KNOWN
        statuses[SourceId.DISH_DATABASE] = DataStatus.KNOWN
        if isinstance(user_context, Mapping):
            explicit = user_context.get("source_statuses")
            if isinstance(explicit, Mapping):
                for key, value in explicit.items():
                    try:
                        statuses[SourceId(str(key))] = _status(value)
                    except ValueError:
                        continue
            if user_context.get("nutrition_safety") is not None or user_context.get("nutrition_safety_profile") is not None:
                statuses[SourceId.NUTRITION_SAFETY] = DataStatus.KNOWN
            calculation_manifest = user_context.get("calculation_manifest")
            if isinstance(calculation_manifest, Mapping):
                outputs = calculation_manifest.get("outputs")
                canonical_status = str(outputs.get("status", "")) if isinstance(outputs, Mapping) else ""
                # READY is the only ordinary prescriptive canonical state.
                # Unsupported, unavailable, specialist-gated, and empty demo
                # output remain explicitly unavailable to the shadow bundle.
                statuses[SourceId.CANONICAL_NUTRITION] = (
                    DataStatus.KNOWN if canonical_status == "READY" else DataStatus.MISSING
                )
            if user_context.get("profile") is not None or any(
                key in user_context for key in ("age", "height", "weight", "equation_sex")
            ):
                statuses[SourceId.PROFILE] = DataStatus.KNOWN
            manifest = user_context.get("state_manifest")
            if isinstance(manifest, Mapping):
                source_fields: dict[SourceId, list[DataStatus]] = {}
                for field, envelope in manifest.items():
                    if not isinstance(envelope, Mapping):
                        continue
                    name = str(field).lower()
                    mapped = SourceId.DAILY_NUTRITION if any(x in name for x in ("meal", "nutrition", "calories_consumed")) else SourceId.TODAY_EXERCISE if "exercise" in name else SourceId.PROFILE if "weight" in name else SourceId.LIFESTYLE if any(x in name for x in ("lifestyle", "sleep", "stress")) else SourceId.ACTIVE_PLAN if "plan" in name else None
                    if mapped:
                        source_fields.setdefault(mapped, []).append(_status(envelope.get("status")))
                severity = [DataStatus.CONFLICT, DataStatus.ERROR, DataStatus.STALE, DataStatus.NOT_LOADED, DataStatus.MISSING, DataStatus.KNOWN]
                for source, values in source_fields.items():
                    statuses[source] = next(item for item in severity if item in values)
        if memory_context is not None:
            if getattr(memory_context, "pinned_facts", None):
                statuses[SourceId.CONFIRMED_MEMORY] = DataStatus.KNOWN
            if getattr(memory_context, "history", None):
                statuses[SourceId.RECENT_CONVERSATION] = DataStatus.KNOWN
            if getattr(memory_context, "rag_chunks", None):
                statuses[SourceId.RAG] = DataStatus.KNOWN
        return statuses

    def build_bundle(self, plan: ContextPlan, statuses: Mapping[SourceId, DataStatus], *, current_production_context_size_characters: int) -> ContextBundle:
        freshness = {item.source_id: item.freshness for item in plan.freshness_requirements}
        missing: list[SourceId] = []
        actions: list[MissingDataAction] = []
        action_by_status = {DataStatus.STALE: "REFRESH_SOURCE", DataStatus.ERROR: "RETRY_SOURCE", DataStatus.CONFLICT: "RESOLVE_CONFLICT", DataStatus.MISSING: "LOAD_SOURCE", DataStatus.NOT_LOADED: "LOAD_SOURCE"}
        for source in plan.required_sources:
            observed = statuses.get(source, DataStatus.NOT_LOADED)
            if observed != DataStatus.KNOWN:
                missing.append(source)
                action = "RETRIEVE_SOURCE" if source in {SourceId.RAG, SourceId.MEDICAL_EVIDENCE} else action_by_status[observed]
                actions.append(MissingDataAction(source, observed, freshness.get(source, Freshness.ANY), action))

        included = list(plan.required_sources)
        optional_order = sorted(plan.optional_sources, key=lambda source: (-SOURCE_REGISTRY[source].priority, source.value))
        used = sum(SOURCE_REGISTRY[source].estimated_characters for source in included)
        trimmed: list[SourceId] = []
        for source in optional_order:
            chars = SOURCE_REGISTRY[source].estimated_characters
            if used + chars <= self.context_budget_characters:
                included.append(source); used += chars
            else:
                trimmed.append(source)

        grouped: dict[str, list[SourceId]] = {}
        for source in included:
            grouped.setdefault(_SECTION_BY_SOURCE[source], []).append(source)
        sections: list[ContextSection] = []
        required_set = set(plan.required_sources)
        for section_id in sorted(grouped):
            sources = tuple(grouped[section_id])
            chars = sum(SOURCE_REGISTRY[item].estimated_characters for item in sources)
            sections.append(ContextSection(
                section_id=section_id, sources=sources,
                source_status=tuple((item, statuses.get(item, DataStatus.NOT_LOADED)) for item in sources),
                included_fields=tuple(f"{item.value.lower()}.typed_fields" for item in sources),
                estimated_characters=chars, estimated_tokens=math.ceil(chars / 4),
                priority=max(SOURCE_REGISTRY[item].priority for item in sources),
                required=any(item in required_set for item in sources),
            ))
        return ContextBundle(
            bundle_version=BUNDLE_VERSION, sections=tuple(sections),
            missing_required_sources=tuple(missing), missing_data_actions=tuple(actions),
            trimmed_optional_sources=tuple(trimmed), planned_context_size_characters=used,
            planned_context_size_tokens=math.ceil(used / 4),
            current_production_context_size_characters=current_production_context_size_characters,
            current_production_context_size_tokens=math.ceil(current_production_context_size_characters / 4),
            budget_characters=self.context_budget_characters,
        )

    def plan_shadow(self, query: str, *, user_context: Any = None, memory_context: Any = None, available_tool_names: Iterable[str] = ALL_KNOWN_TOOLS, current_production_context_size_characters: int = 0) -> ShadowPlanningResult:
        started = time.perf_counter()
        classification, plan = self.create_plan(query, available_tool_names=available_tool_names)
        statuses = self.resolve_statuses(user_context, memory_context)
        # The production memory loader currently runs before this shadow hook.
        # If it already produced RAG chunks, an explicit query_rag tool would
        # duplicate retrieval in the planned architecture, so suppress it.
        if statuses[SourceId.RAG] == DataStatus.KNOWN and "query_rag" in plan.permitted_tools:
            plan = replace(
                plan,
                permitted_tools=tuple(item for item in plan.permitted_tools if item != "query_rag"),
                forbidden_tools=tuple(sorted(set(plan.forbidden_tools) | {"query_rag"})),
                planner_reason_codes=(*plan.planner_reason_codes, "RAG_ALREADY_AVAILABLE_NO_DUPLICATE"),
            )
        bundle = self.build_bundle(plan, statuses, current_production_context_size_characters=current_production_context_size_characters)
        return ShadowPlanningResult(classification, plan, bundle, (time.perf_counter() - started) * 1000)


__all__ = ["ContextPlanner", "ShadowPlanningResult"]
