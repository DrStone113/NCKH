from __future__ import annotations

from dataclasses import dataclass

import pytest

from services.agent.llm_client import LLMResponse, ToolCall
from services.agent.scope_guard import (
    SafetyDisposition,
    ScopeCategory,
    ScopeGuard,
    ScopeIntent,
    StrictJSONScopeClassifier,
    TopicPrediction,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Thực đơn giảm cân cho người đau dạ dày?", ScopeCategory.IN_SCOPE_MEAL_PLAN),
        ("Tối nay tôi nên ăn gì?", ScopeCategory.IN_SCOPE_NUTRITION),
        ("Gợi ý bài tập tại nhà 30 phút", ScopeCategory.IN_SCOPE_FITNESS),
        ("Đêm qua tôi ngủ 5 tiếng", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("Tôi muốn giảm 2 kí treong 2 th tôi", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("Tôi muốn giảm beo in 2 months tôi", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("toi wanna lose fat trong 2 months", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("Tôi muốn tăng 3 ký trong 6 tuần", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("Hiện tại tôi nặng 62 kilo", ScopeCategory.IN_SCOPE_GENERAL_WELLNESS),
        ("Tôi đau ngực và khó thở", ScopeCategory.SAFETY_ESCALATION),
        ("Flutter app này đang hiển thị sai lượng kcal của tôi", ScopeCategory.IN_SCOPE_PROFILE_APP),
        ("Thời tiết nóng thế này nên uống bao nhiêu nước?", ScopeCategory.IN_SCOPE_NUTRITION),
        ("Tôi vừa ăn gà nấu hạt dẻ", ScopeCategory.IN_SCOPE_NUTRITION),
    ],
)
async def test_application_and_health_questions_reach_main_pipeline(text: str, expected: ScopeCategory) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == expected
    assert decision.should_call_main_llm is True
    assert decision.reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("1 + 1 bằng mấy?", "MATH_REQUEST"),
        ("Thời tiết hôm nay thế nào?", "WEATHER_REQUEST"),
        ("Viết cho tôi code Flutter đăng nhập Firebase", "PROGRAMMING_REQUEST"),
        ("Viết thuật toán quicksort bằng Python", "PROGRAMMING_REQUEST"),
        ("Dịch câu này sang tiếng Anh", "TRANSLATION_REQUEST"),
        ("Lên kế hoạch du lịch Đà Nẵng", "TRAVEL_REQUEST"),
    ],
)
async def test_clear_off_topic_questions_are_blocked(text: str, reason: str) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert reason in decision.reason_code
    assert decision.reply


@pytest.mark.asyncio
async def test_technology_noun_is_not_a_blacklist() -> None:
    decision = await ScopeGuard().classify("Python có bao nhiêu protein?")

    assert decision.category == ScopeCategory.AMBIGUOUS
    assert decision.reason_code == "COLLIDING_CONTEXT"
    assert decision.should_call_main_llm is False
    assert "lập trình" not in (decision.reply or "")


@pytest.mark.asyncio
async def test_character_count_is_not_mistaken_for_colloquial_weight() -> None:
    decision = await ScopeGuard().classify("Viết hàm giảm 2 kí tự bằng Python")

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.reason_code == "PROGRAMMING_REQUEST"
    assert decision.should_call_main_llm is False


@pytest.mark.asyncio
async def test_aggressive_weight_goal_stays_in_scope_with_separate_safety_signal() -> None:
    aggressive = await ScopeGuard().classify("Tôi muốn giảm 10kg trong 2 tuần")
    gradual = await ScopeGuard().classify("Tôi muốn giảm 2 kí trong 2 tháng thôi")
    urgent = await ScopeGuard().classify("Tôi bị đau ngực và khó thở")

    assert aggressive.category == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert aggressive.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert aggressive.safety == SafetyDisposition.POTENTIALLY_UNSAFE_WEIGHT_GOAL
    assert aggressive.should_call_main_llm is True
    assert gradual.safety == SafetyDisposition.NONE
    assert urgent.safety == SafetyDisposition.URGENT_ESCALATION


@pytest.mark.asyncio
async def test_code_switched_weight_goal_keeps_weight_management_intent_without_slm() -> None:
    decision = await ScopeGuard().classify("Tôi muốn giảm beo in 2 months tôi")

    assert decision.category == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert decision.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert decision.reason_code == "WEIGHT_GOAL_REQUEST"
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
async def test_smalltalk_gets_a_deterministic_friendly_reply() -> None:
    decision = await ScopeGuard().classify("Chào bạn")

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert "ăn uống" in (decision.reply or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["có", "dạ có", "không", "ok", "vâng", "được", "món đó"])
async def test_short_continuations_reach_pending_action_pipeline(text: str) -> None:
    assert (await ScopeGuard().classify(text)).should_call_main_llm is True


@dataclass
class _Classifier:
    prediction: TopicPrediction
    calls: int = 0

    async def classify(self, text: str) -> TopicPrediction:
        self.calls += 1
        return self.prediction


@dataclass
class _FailingClassifier:
    calls: int = 0

    async def classify(self, text: str) -> TopicPrediction:
        self.calls += 1
        raise RuntimeError("classifier unavailable")


@pytest.mark.asyncio
async def test_hybrid_router_accepts_high_confidence_weight_intent_without_judge() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.IN_SCOPE_GENERAL_WELLNESS,
            0.96,
            "SEMANTIC_WEIGHT_MANAGEMENT",
            "encoder-v1",
            ScopeIntent.WEIGHT_MANAGEMENT,
        )
    )
    judge = _Classifier(
        TopicPrediction(
            ScopeCategory.OUT_OF_SCOPE,
            0.99,
            "WRONG_JUDGE",
            "judge-v1",
            ScopeIntent.OUT_OF_SCOPE,
        )
    )
    decision = await ScopeGuard(judge, primary_classifier=primary).classify(
        "Tôi muốn giảm 2 kí trong 2 tháng thôi"
    )

    assert decision.category == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert decision.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert decision.should_call_main_llm is True
    assert decision.method == "SMALL_INTENT_CLASSIFIER:encoder-v1"
    assert primary.calls == 1
    assert judge.calls == 0


@pytest.mark.asyncio
async def test_hybrid_router_sends_uncertain_prediction_to_json_judge() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.AMBIGUOUS,
            0.70,
            "UNCERTAIN",
            "encoder-v1",
            ScopeIntent.AMBIGUOUS,
        )
    )
    judge = _Classifier(
        TopicPrediction(
            ScopeCategory.IN_SCOPE_PROFILE_APP,
            0.93,
            "APP_SUPPORT",
            "judge-v1",
            ScopeIntent.APP_HEALTH_DATA,
        )
    )
    decision = await ScopeGuard(judge, primary_classifier=primary).classify(
        "Hỗ trợ mục tiêu của mình"
    )

    assert decision.category == ScopeCategory.IN_SCOPE_PROFILE_APP
    assert decision.method == "LLM_SCOPE_JUDGE:judge-v1"
    assert primary.calls == 1
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_hybrid_router_keeps_very_low_confidence_input_ambiguous() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.OUT_OF_SCOPE,
            0.30,
            "LOW_SIGNAL",
            "encoder-v1",
            ScopeIntent.OUT_OF_SCOPE,
        )
    )
    judge = _Classifier(
        TopicPrediction(
            ScopeCategory.OUT_OF_SCOPE,
            0.99,
            "SHOULD_NOT_RUN",
            "judge-v1",
            ScopeIntent.OUT_OF_SCOPE,
        )
    )
    decision = await ScopeGuard(judge, primary_classifier=primary).classify("Cái đó ổn chứ?")

    assert decision.category == ScopeCategory.AMBIGUOUS
    assert decision.should_call_main_llm is False
    assert decision.reason_code == "LOW_CONFIDENCE_INTENT"
    assert judge.calls == 0


@pytest.mark.asyncio
async def test_hybrid_router_judges_rule_classifier_disagreement() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.OUT_OF_SCOPE,
            0.96,
            "SEMANTIC_OUT_OF_SCOPE",
            "encoder-v1",
            ScopeIntent.OUT_OF_SCOPE,
        )
    )
    judge = _Classifier(
        TopicPrediction(
            ScopeCategory.IN_SCOPE_NUTRITION,
            0.94,
            "NUTRITION_CONTEXT",
            "judge-v1",
            ScopeIntent.NUTRITION,
        )
    )
    decision = await ScopeGuard(judge, primary_classifier=primary).classify(
        "Tính bằng Python giúp tôi lượng protein mỗi ngày"
    )

    assert decision.category == ScopeCategory.IN_SCOPE_NUTRITION
    assert decision.method == "LLM_SCOPE_JUDGE:judge-v1"
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
async def test_hybrid_router_falls_back_to_clear_health_rule_when_encoder_is_unavailable() -> None:
    primary = _FailingClassifier()
    decision = await ScopeGuard(primary_classifier=primary).classify(
        "Tôi muốn giảm 2 kí trong 2 tháng thôi"
    )

    assert decision.category == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert decision.reason_code == "WEIGHT_GOAL_REQUEST"
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
async def test_hard_safety_and_explicit_oos_rules_bypass_both_models() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.IN_SCOPE_NUTRITION,
            0.99,
            "SHOULD_NOT_RUN",
            "encoder-v1",
            ScopeIntent.NUTRITION,
        )
    )
    judge = _Classifier(
        TopicPrediction(
            ScopeCategory.IN_SCOPE_NUTRITION,
            0.99,
            "SHOULD_NOT_RUN",
            "judge-v1",
            ScopeIntent.NUTRITION,
        )
    )
    guard = ScopeGuard(judge, primary_classifier=primary)

    safety = await guard.classify("Tôi bị đau ngực và khó thở")
    coding = await guard.classify("Viết code đăng nhập bằng Flutter")

    assert safety.category == ScopeCategory.SAFETY_ESCALATION
    assert coding.category == ScopeCategory.OUT_OF_SCOPE
    assert primary.calls == 0
    assert judge.calls == 0


@pytest.mark.asyncio
async def test_small_classifier_runs_only_for_ambiguous_input() -> None:
    classifier = _Classifier(
        TopicPrediction(ScopeCategory.IN_SCOPE_PROFILE_APP, 0.91, "APP_SUPPORT", "scope-slm-v1")
    )
    guard = ScopeGuard(classifier)

    clear = await guard.classify("Tối nay tôi nên ăn gì?")
    ambiguous = await guard.classify("Hỗ trợ mục tiêu của mình")

    assert clear.category == ScopeCategory.IN_SCOPE_NUTRITION
    assert classifier.calls == 1
    assert ambiguous.category == ScopeCategory.IN_SCOPE_PROFILE_APP
    assert ambiguous.method == "LLM_SCOPE_JUDGE:scope-slm-v1"


@pytest.mark.asyncio
async def test_clear_off_topic_input_never_calls_small_classifier() -> None:
    classifier = _Classifier(
        TopicPrediction(ScopeCategory.IN_SCOPE_NUTRITION, 0.99, "WRONG_OVERRIDE", "scope-slm-v1")
    )

    decision = await ScopeGuard(classifier).classify("Viết code Flutter đăng nhập Firebase")

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert classifier.calls == 0


@pytest.mark.asyncio
async def test_low_confidence_classifier_fails_closed() -> None:
    classifier = _Classifier(
        TopicPrediction(ScopeCategory.IN_SCOPE_NUTRITION, 0.70, "NUTRITION", "scope-slm-v1")
    )
    decision = await ScopeGuard(classifier).classify("Hỗ trợ mục tiêu của mình")

    assert decision.category == ScopeCategory.AMBIGUOUS
    assert decision.should_call_main_llm is False


class _JSONLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls: list[tuple] = []

    async def chat(self, messages, tools, stream, max_tokens=None):
        self.calls.append((messages, tools, stream, max_tokens))
        return self.response


@pytest.mark.asyncio
async def test_json_classifier_has_no_tools_history_or_answer_authority() -> None:
    llm = _JSONLLM(
        LLMResponse(
            full_text=(
                '{"intent":"OUT_OF_SCOPE","scope":"OUT_OF_SCOPE",'
                '"confidence":0.97,"reason_code":"PROGRAMMING_REQUEST"}'
            )
        )
    )
    classifier = StrictJSONScopeClassifier(llm, model_version="scope-slm-v1")

    prediction = await classifier.classify("Viết quicksort")

    assert prediction.scope == ScopeCategory.OUT_OF_SCOPE
    assert prediction.intent == ScopeIntent.OUT_OF_SCOPE
    messages, tools, stream, max_tokens = llm.calls[0]
    assert len(messages) == 2
    assert tools is None
    assert stream is False
    assert max_tokens == 96
    assert "Viết quicksort" not in messages[0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(
            full_text=(
                '```json\n{"intent":"OUT_OF_SCOPE","scope":"OUT_OF_SCOPE",'
                '"confidence":0.9,"reason_code":"X"}\n```'
            )
        ),
        LLMResponse(
            full_text=(
                '{"intent":"OUT_OF_SCOPE","scope":"OUT_OF_SCOPE",'
                '"confidence":0.9,"reason_code":"X","answer":"2"}'
            )
        ),
        LLMResponse(tool_calls=[ToolCall(id="x", name="answer", arguments={})]),
    ],
)
async def test_json_classifier_rejects_wrappers_extra_fields_and_tools(response: LLMResponse) -> None:
    classifier = StrictJSONScopeClassifier(_JSONLLM(response), model_version="scope-slm-v1")

    with pytest.raises((ValueError, TypeError)):
        await classifier.classify("mơ hồ")


@pytest.mark.asyncio
async def test_mixed_request_forwards_only_health_fragment_and_returns_fixed_refusal() -> None:
    decision = await ScopeGuard().classify(
        "Hôm nay tôi nên ăn bao nhiêu protein, tiện thể viết code C++ cho tôi"
    )

    assert decision.is_mixed is True
    assert decision.allowed_text == "Hôm nay tôi nên ăn bao nhiêu protein"
    assert "lập trình" in (decision.reply_suffix or "")
    assert "code" not in decision.allowed_text.casefold()
