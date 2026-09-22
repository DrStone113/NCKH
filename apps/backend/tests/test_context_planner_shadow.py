from dataclasses import FrozenInstanceError
import json

import pytest
from pydantic import ValidationError

from config import Settings, settings
from services.agent.context_planner import ContextPlanner, Intent, SourceId, classify_intent
from services.agent.context_planner.contracts import (
    BUNDLE_VERSION, INTENT_VERSION, MATRIX_VERSION, PLAN_VERSION,
    SOURCE_REGISTRY_VERSION, VALIDATOR_REGISTRY_VERSION, DataStatus, RagPolicy,
)
from services.agent.context_planner.development_scenarios import DEVELOPMENT_SCENARIOS
from services.agent.context_planner.evaluator import evaluate_scenarios
from services.agent.context_planner.matrix import ALL_KNOWN_TOOLS, INTENT_SOURCE_MATRIX
from services.agent.context_planner.registry import SOURCE_REGISTRY, VALIDATOR_REGISTRY
from services.agent.context_trace import ContextTraceRecorder
from services.agent.llm_client import LLMResponse
from services.agent.memory_service import Context
from services.agent.orchestrator import AgentOrchestrator


def test_versioned_taxonomy_registry_and_matrix_are_complete():
    assert INTENT_VERSION == "context-intent-v1"
    assert PLAN_VERSION == "context-plan-v1"
    assert BUNDLE_VERSION == "context-bundle-v1"
    assert MATRIX_VERSION == "context-source-matrix-v1"
    assert SOURCE_REGISTRY_VERSION == "context-source-registry-v1"
    assert VALIDATOR_REGISTRY_VERSION == "context-validator-v1"
    assert set(INTENT_SOURCE_MATRIX) == set(Intent)
    assert set(SOURCE_REGISTRY) == set(SourceId)
    assert len(VALIDATOR_REGISTRY) == 7


def test_plan_is_immutable_serializable_and_deterministic():
    planner = ContextPlanner()
    first_classification, first = planner.create_plan("Hôm nay tôi còn bao nhiêu protein?")
    second_classification, second = planner.create_plan("Hôm nay tôi còn bao nhiêu protein?")
    assert first_classification == second_classification
    assert first == second
    json.dumps(first.to_dict())
    with pytest.raises(FrozenInstanceError):
        first.primary_intent = Intent.SMALLTALK_OR_OTHER


def test_multi_intent_merges_sources_without_forbidden_overlap():
    _, plan = ContextPlanner().create_plan("Hôm nay còn bao nhiêu protein và gợi ý bữa tối?")
    assert plan.primary_intent == Intent.DAILY_NUTRITION_STATUS
    assert plan.secondary_intents == (Intent.MEAL_RECOMMENDATION,)
    assert SourceId.CANONICAL_NUTRITION in plan.required_sources
    assert SourceId.NUTRITION_SAFETY in plan.required_sources
    assert not (set(plan.required_sources) | set(plan.optional_sources)) & set(plan.forbidden_sources)


@pytest.mark.parametrize(
    ("query", "policy", "tool"),
    [
        ("Hôm nay còn bao nhiêu calo?", RagPolicy.FORBIDDEN, "get_today_meals"),
        ("Xu hướng cân nặng 7 ngày?", RagPolicy.FORBIDDEN, "get_weight_history"),
        ("Chất xơ là gì?", RagPolicy.REQUIRED, "query_rag"),
        ("Bằng chứng y khoa về chất xơ và bệnh tiểu đường?", RagPolicy.REQUIRED, "search_medical_knowledge"),
    ],
)
def test_rag_and_tool_gating(query, policy, tool):
    _, plan = ContextPlanner().create_plan(query)
    assert plan.rag_policy == policy
    assert tool in plan.permitted_tools
    if policy == RagPolicy.FORBIDDEN:
        assert "query_rag" not in plan.permitted_tools


@pytest.mark.parametrize(
    "query",
    [
        "Theo hướng dẫn quốc gia, hạn chế thực phẩm bất lợi cần lưu ý gì?",
        "RNI về nhu cầu năng lượng và mức hoạt động là gì?",
        "Lưu ý dinh dưỡng về EPA và DHA",
        "Thông tin sức khỏe cơ bản về thiếu máu",
        "health muscle cramps",
    ],
)
def test_reference_questions_use_grounded_rag_without_fixture_specific_matching(query):
    classification, plan = ContextPlanner().create_plan(query)
    assert classification.primary_intent == Intent.GENERAL_NUTRITION_KNOWLEDGE
    assert plan.rag_policy == RagPolicy.REQUIRED
    assert "query_rag" in plan.permitted_tools


@pytest.mark.parametrize(
    "query",
    [
        "Đậu đỏ có bao nhiêu đạm và năng lượng?",
        "dinh dưỡng bí xanh",
        "Nutrition facts for apples with skin",
        "food nutrients canned beans",
    ],
)
def test_food_metric_query_shapes_use_the_structured_food_lookup(query):
    classification, plan = ContextPlanner().create_plan(query)
    assert classification.primary_intent == Intent.FOOD_NUTRITION_LOOKUP
    assert "search_food_nutrition" in plan.permitted_tools
    assert "query_rag" not in plan.permitted_tools


def test_write_tools_require_explicit_precise_intent_and_low_level_helpers_never_leak():
    planner = ContextPlanner()
    _, mention = planner.create_plan("Bữa trưa của tôi có cơm")
    _, write = planner.create_plan("Ghi lại bữa ăn trưa của tôi")
    assert not set(mention.permitted_tools) & {"log_meal", "log_weight", "log_exercise"}
    assert "log_meal" in write.permitted_tools
    assert "log_weight" not in write.permitted_tools
    for query in ("Kế hoạch hiện tại của tôi?", "Tạo kế hoạch hiện tại cho tôi", "hello"):
        _, plan = planner.create_plan(query)
        assert "create_plan" not in plan.permitted_tools
        assert "append_plan_items" not in plan.permitted_tools


def test_memory_and_freshness_policies_are_explicit():
    planner = ContextPlanner()
    _, meal = planner.create_plan("Gợi ý bữa tối Việt Nam giàu protein")
    _, smalltalk = planner.create_plan("Xin chào")
    _, weight = planner.create_plan("Xu hướng cân nặng 7 ngày?")
    assert meal.memory_policy.value == "REQUIRED"
    assert smalltalk.memory_policy.value == "FORBIDDEN"
    freshness = {item.source_id: item.freshness.value for item in weight.freshness_requirements}
    assert freshness[SourceId.WEIGHT_HISTORY] == "RECENT"


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (DataStatus.STALE, "REFRESH_SOURCE"),
        (DataStatus.ERROR, "RETRY_SOURCE"),
        (DataStatus.CONFLICT, "RESOLVE_CONFLICT"),
        (DataStatus.NOT_LOADED, "LOAD_SOURCE"),
        (DataStatus.MISSING, "LOAD_SOURCE"),
    ],
)
def test_missing_data_preserves_d1_status_semantics(status, action):
    planner = ContextPlanner()
    _, plan = planner.create_plan("Xu hướng cân nặng 7 ngày?")
    bundle = planner.build_bundle(
        plan, {SourceId.WEIGHT_HISTORY: status},
        current_production_context_size_characters=10000,
    )
    assert bundle.missing_required_sources == (SourceId.WEIGHT_HISTORY,)
    assert bundle.missing_data_actions[0].observed_status == status
    assert bundle.missing_data_actions[0].action == action


def test_context_budget_never_trims_required_safety_or_canonical_state():
    planner = ContextPlanner(context_budget_characters=1000)
    _, plan = planner.create_plan("Hôm nay còn bao nhiêu protein và gợi ý bữa tối?")
    statuses = {source: DataStatus.KNOWN for source in SourceId}
    bundle = planner.build_bundle(plan, statuses, current_production_context_size_characters=15000)
    included = {source for section in bundle.sections for source in section.sources}
    assert set(plan.required_sources) <= included
    assert SourceId.NUTRITION_SAFETY in included
    assert SourceId.CANONICAL_NUTRITION in included
    assert bundle.trimmed_optional_sources
    assert bundle.current_production_context_size_characters == 15000


def test_evidence_route_is_grounded_and_not_app_state_prescriptive():
    _, plan = ContextPlanner().create_plan("Bằng chứng lâm sàng về dinh dưỡng và bệnh tiểu đường?")
    assert plan.primary_intent == Intent.EVIDENCE_HEALTH_QUESTION
    assert SourceId.MEDICAL_EVIDENCE in plan.required_sources
    assert SourceId.NUTRITION_SAFETY in plan.required_sources
    assert SourceId.RAG in plan.forbidden_sources
    assert "search_medical_knowledge" in plan.permitted_tools
    assert "query_rag" not in plan.permitted_tools
    assert not set(plan.permitted_tools) & {"log_meal", "log_weight", "create_long_term_plan"}


@pytest.mark.parametrize("canonical_status", ["UNSUPPORTED", "INPUT_UNAVAILABLE", "REQUIRES_SPECIALIST_GUIDANCE"])
def test_non_ready_canonical_state_is_never_promoted_to_known(canonical_status):
    planner = ContextPlanner()
    statuses = planner.resolve_statuses(
        {"calculation_manifest": {"outputs": {"status": canonical_status}}}, None
    )
    assert statuses[SourceId.CANONICAL_NUTRITION] == DataStatus.MISSING


def test_ready_canonical_and_structured_safety_are_known_but_stale_weight_stays_stale():
    statuses = ContextPlanner().resolve_statuses(
        {
            "age": 30,
            "weight": 70,
            "nutrition_safety_profile": {"pregnancy": "UNKNOWN"},
            "calculation_manifest": {"outputs": {"status": "READY"}},
            "state_manifest": {"profile.current_weight": {"status": "STALE"}},
        },
        None,
    )
    assert statuses[SourceId.NUTRITION_SAFETY] == DataStatus.KNOWN
    assert statuses[SourceId.CANONICAL_NUTRITION] == DataStatus.KNOWN
    assert statuses[SourceId.PROFILE] == DataStatus.STALE


def test_bundle_preview_contains_structure_not_sensitive_values():
    result = ContextPlanner().plan_shadow(
        "Gợi ý bữa tối cho tôi", user_context={"profile": {"name": "Sensitive Name"}}
    )
    payload = json.dumps(result.bundle.to_dict())
    assert "Sensitive Name" not in payload
    assert "typed_fields" in payload


def test_existing_automatic_rag_suppresses_duplicate_explicit_query_tool():
    memory = Context(rag_chunks=[object()], rag_requested=True, rag_result_status="FOUND")
    result = ContextPlanner().plan_shadow(
        "Chất xơ là gì?", memory_context=memory,
        available_tool_names=ALL_KNOWN_TOOLS,
    )
    assert result.plan.rag_policy == RagPolicy.REQUIRED
    assert SourceId.RAG not in result.bundle.missing_required_sources
    assert "query_rag" not in result.plan.permitted_tools
    assert "RAG_ALREADY_AVAILABLE_NO_DUPLICATE" in result.plan.planner_reason_codes


def test_feature_flag_is_off_by_default_and_enforced_mode_is_rejected():
    assert Settings(_env_file=None).context_planner_mode == "off"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, context_planner_mode="enforced")


def test_context_trace_records_shadow_structure():
    result = ContextPlanner().plan_shadow("Hôm nay còn bao nhiêu calo?")
    recorder = ContextTraceRecorder("query", enabled=True)
    recorder.capture_shadow(result)
    assert recorder.trace.shadow_primary_intent == "DAILY_NUTRITION_STATUS"
    assert recorder.trace.shadow_context_plan["plan_version"] == PLAN_VERSION
    assert recorder.trace.shadow_rag_policy == "RAG_FORBIDDEN"
    assert recorder.trace.planner_latency_ms is not None


def test_synthetic_oracles_and_metrics_meet_shadow_gate():
    assert len(DEVELOPMENT_SCENARIOS) == 60
    assert len({item.scenario_id for item in DEVELOPMENT_SCENARIOS}) == 60
    metrics = evaluate_scenarios()["overall"]
    assert metrics["primary_intent_accuracy"] == 1.0
    assert metrics["required_source_recall"] == 1.0
    assert metrics["forbidden_source_violation_rate"] == 0.0
    assert metrics["rag_routing_accuracy"] == 1.0
    assert metrics["tool_precision"] == 1.0
    assert metrics["tool_recall"] == 1.0
    assert metrics["missing_data_accuracy"] == 1.0
    assert metrics["determinism_rate"] == 1.0


class _Tools:
    def schemas(self):
        return []

    def names(self):
        return list(ALL_KNOWN_TOOLS)


class _Memory:
    async def loadContext(self, session_id, user_text):
        return Context()


class _Store:
    def __init__(self):
        self.turns = []

    async def appendTurn(self, *args):
        self.turns.append(args)


class _Dispatcher:
    async def dispatch(self, *args):
        raise AssertionError("no tool call expected")


class _CapturingLLM:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools, *args, **kwargs):
        self.calls.append((json.loads(json.dumps(messages)), tools))
        return LLMResponse(full_text="identical response")


@pytest.mark.asyncio
async def test_shadow_mode_does_not_change_prompt_tools_or_response(monkeypatch):
    async def run(mode):
        monkeypatch.setattr(settings, "context_planner_mode", mode)
        llm, store = _CapturingLLM(), _Store()
        orchestrator = AgentOrchestrator(llm, _Tools(), _Memory(), store, _Dispatcher())
        await orchestrator.handleChatMessage("session", "Xin chào")
        return llm.calls, store.turns

    off_calls, off_turns = await run("off")
    shadow_calls, shadow_turns = await run("shadow")
    assert off_calls == shadow_calls
    assert off_turns == shadow_turns
