from __future__ import annotations

import pytest

from services.agent.semantic_router_service import (
    RestrictedJSONServerSLMAdapter,
    SemanticRouterMode,
    SemanticRouterService,
)
from services.agent.turn_intent import INTENT_VERSION, TurnIntent, TurnIntentDecision


class _Adapter:
    def __init__(self, decision: TurnIntentDecision) -> None:
        self.decision = decision
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "approved-test-model"

    async def parse(self, text: str, *, candidates: tuple[str, ...]) -> TurnIntentDecision:
        self.calls += 1
        return self.decision


def _decision(**overrides: object) -> TurnIntentDecision:
    values: dict[str, object] = {
        "intent_version": INTENT_VERSION,
        "primary_intent": TurnIntent.MEAL_SUGGESTION,
        "secondary_intents": (),
        "health_context": (),
        "negated_actions": (),
        "explicit_write_action": None,
        "clarification_required": False,
        "confidence": 0.95,
        "reason_codes": ("TEST",),
        "method": "TEST",
    }
    values.update(overrides)
    return TurnIntentDecision(**values)


@pytest.mark.asyncio
async def test_unconfigured_shadow_router_uses_deterministic_safe_fallback():
    result = await SemanticRouterService(mode="shadow").parse("Tối nay ăn gì?")

    assert result.parser_type == "DETERMINISTIC_CANDIDATE"
    assert result.verifier_status == "FALLBACK"
    assert result.verifier_reason_codes == ("MODEL_CONFIGURATION_MISSING",)
    assert result.slm_invoked is False
    assert "raw_text" not in result.to_debug_dict()


@pytest.mark.asyncio
async def test_high_confidence_deterministic_case_does_not_call_slm():
    adapter = _Adapter(_decision())
    result = await SemanticRouterService(slm_adapter=adapter).parse("Tối nay ăn gì?")

    assert result.verifier_status == "VALID"
    assert result.slm_invoked is False
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_urgent_health_guard_overrides_an_untrusted_semantic_adapter():
    adapter = _Adapter(_decision(primary_intent=TurnIntent.GENERAL_WELLNESS))

    result = await SemanticRouterService(slm_adapter=adapter).parse(
        "Da noi man sau khi an va moi bat dau sung"
    )

    assert result.parser_type == "DETERMINISTIC_SAFETY_GUARD"
    assert result.decision.primary_intent == TurnIntent.HEALTH_QUERY
    assert result.decision.health_context == ("URGENT",)
    assert result.decision.explicit_write_action is None
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_low_confidence_case_can_use_verified_server_slm_parse():
    adapter = _Adapter(_decision())
    result = await SemanticRouterService(slm_adapter=adapter).parse("nay an j de giam mo")

    assert adapter.calls == 1
    assert result.parser_type == "SERVER_SLM"
    assert result.decision.primary_intent == TurnIntent.MEAL_SUGGESTION
    assert result.verifier_status == "VALID"


@pytest.mark.asyncio
async def test_negated_write_from_slm_is_rejected_and_never_becomes_authoritative():
    adapter = _Adapter(
        _decision(
            primary_intent=TurnIntent.PLAN_LIFECYCLE,
            negated_actions=("WRITE",),
            explicit_write_action="PLAN_LIFECYCLE",
        )
    )
    result = await SemanticRouterService(
        slm_adapter=adapter, slm_confidence_threshold=0.99
    ).parse("lên kế hoạch ngày mai")

    assert result.parser_type == "DETERMINISTIC_FALLBACK"
    assert result.verifier_status == "INVALID"
    assert result.verifier_reason_codes == ("NEGATED_WRITE_CONFLICT",)
    assert result.decision.explicit_write_action is None


class _Response:
    tool_calls = []

    def __init__(self, full_text: str) -> None:
        self.full_text = full_text


class _Client:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def chat(self, messages, **kwargs):
        self.kwargs = kwargs
        return _Response(
            '{"primary_intent":"MEAL_SUGGESTION","secondary_intents":[],"health_context":[],"negated_actions":[],"explicit_write_action":null,"clarification_required":false,"confidence":0.9,"reason_codes":["TEST"]}'
        )


@pytest.mark.asyncio
async def test_restricted_adapter_has_no_tools_and_requires_exact_json_schema():
    client = _Client()
    adapter = RestrictedJSONServerSLMAdapter(client, model_name="approved-test-model")

    decision = await adapter.parse("nay an j", candidates=(TurnIntent.MEAL_SUGGESTION,))

    assert decision.primary_intent == TurnIntent.MEAL_SUGGESTION
    assert client.kwargs == {"tools": None, "stream": False, "max_tokens": 160}
