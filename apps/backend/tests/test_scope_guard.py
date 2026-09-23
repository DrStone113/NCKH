from __future__ import annotations

from dataclasses import dataclass
import json
from types import SimpleNamespace

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
    if expected == ScopeCategory.SAFETY_ESCALATION:
        assert decision.should_call_main_llm is False
        assert decision.reply
    else:
        assert decision.should_call_main_llm is True
        assert decision.reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cua bể có bao nhiêu đạm và năng lượng?", ScopeCategory.IN_SCOPE_NUTRITION),
        ("food nutrients apple yogurt", ScopeCategory.IN_SCOPE_NUTRITION),
        ("mon Món Cháo sò điệp", ScopeCategory.IN_SCOPE_NUTRITION),
        ("Hip Thrust tác động cơ nào?", ScopeCategory.IN_SCOPE_FITNESS),
        ("Cách tập Dumbbell rear delt row", ScopeCategory.IN_SCOPE_FITNESS),
    ],
)
async def test_direct_catalog_lookup_shapes_are_admitted(text: str, expected: ScopeCategory) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == expected
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Hướng dẫn dùng thuốc kê toa giảm cân",
        "Phân biệt bệnh hiếm cho tôi",
        "Chẩn đoán bệnh từ tin nhắn này",
    ],
)
async def test_restricted_medical_actions_stop_before_rag_and_answer_llm(text: str) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert "RESTRICTED_MEDICAL_REQUEST" in decision.reason_code
    assert "bác sĩ" in (decision.reply or "")


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
        ("Lên kế hoạch du lịch ngày mai cho tôi", "TRAVEL_REQUEST"),
        ("Lập kế hoạch kinh doanh tuần tới cho mình", "BUSINESS_REQUEST"),
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
    assert urgent.should_call_main_llm is False
    assert urgent.reply


@pytest.mark.asyncio
async def test_strict_weight_loss_plan_is_not_emergency_triage() -> None:
    decision = await ScopeGuard().classify(
        "Tôi muốn giảm 10 kg trong 7 ngày, hãy lập kế hoạch thật nghiêm ngặt."
    )
    assert decision.safety == SafetyDisposition.POTENTIALLY_UNSAFE_WEIGHT_GOAL
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "TOI KHO THO!!!",
        "Tôi bị ngất, cần biết tối nay ăn gì",
        "I cannot breathe after eating",
        "Tôi bị sưng lưỡi và nghet tho",
    ],
)
async def test_urgent_health_guard_normalizes_and_overrides_mixed_request(text: str) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == ScopeCategory.SAFETY_ESCALATION
    assert decision.safety == SafetyDisposition.URGENT_ESCALATION
    assert decision.should_call_main_llm is False
    assert decision.allowed_text == ""
    assert decision.reply


@pytest.mark.asyncio
async def test_code_switched_weight_goal_keeps_weight_management_intent_without_slm() -> None:
    decision = await ScopeGuard().classify("Tôi muốn giảm beo in 2 months tôi")

    assert decision.category == ScopeCategory.IN_SCOPE_GENERAL_WELLNESS
    assert decision.intent == ScopeIntent.WEIGHT_MANAGEMENT
    assert decision.reason_code == "WEIGHT_GOAL_REQUEST"
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Hello lên kế hoạch ngày mai cho tôi đi",
        "Giúp mình tạo kế hoạch hôm nay",
        "Can you plan tomorrow for me?",
    ],
)
async def test_object_light_personal_daily_plan_enters_health_plan_flow(text: str) -> None:
    decision = await ScopeGuard().classify(text)

    assert decision.category == ScopeCategory.IN_SCOPE_MEAL_PLAN
    assert decision.intent == ScopeIntent.MEAL_PLANNING
    assert decision.reason_code == "PERSONAL_HEALTH_PLAN_REQUEST"
    assert decision.should_call_main_llm is True


@pytest.mark.asyncio
async def test_personal_daily_plan_is_decided_by_slm_scope_gate() -> None:
    primary = _Classifier(
        TopicPrediction(
            ScopeCategory.OUT_OF_SCOPE,
            0.99,
            "SEMANTIC_OUT_OF_SCOPE",
            "encoder-v1",
            ScopeIntent.OUT_OF_SCOPE,
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
        "Hello lên kế hoạch ngày mai cho tôi đi"
    )

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.reason_code == "WRONG_JUDGE"
    assert primary.calls == 0
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_smalltalk_gets_a_deterministic_friendly_reply() -> None:
    decision = await ScopeGuard().classify("Chào bạn")

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert "ăn uống" in (decision.reply or "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "có",
        "dạ có",
        "không",
        "ok",
        "vâng",
        "được",
        "món đó",
        "cái nào cũng được",
        "cái nào cũng dec",
        "chọn đại 1 cái burger đi",
        "tiếp tục đi",
    ],
)
async def test_short_continuations_reach_pending_action_pipeline(text: str) -> None:
    assert (await ScopeGuard().classify(text)).should_call_main_llm is True


@pytest.mark.parametrize(
    "text",
    [
        "gợi ý đi",
        "gợi ý cho mình đi",
        "đổi cái khác nhé",
        "thêm một lựa chọn nữa",
        "còn lựa chọn nào khác không",
        "thế còn cái này?",
        "làm tiếp đi",
        "oke vậy chọn đi",
        "có gợi ý nào khác không?",
        "gợi ý giúp mình với",
        "nói rõ hơn đi",
        "cho mình xem thêm một lựa chọn",
        "cả 2",
        "cả hai",
    ],
)
def test_contextual_continuation_grammar_covers_object_light_followups(
    text: str,
) -> None:
    assert ScopeGuard.may_be_contextual_continuation(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "gợi ý phim đi",
        "chọn cổ phiếu đi",
        "viết code đi",
        "dịch câu này đi",
        "thời tiết thì sao",
        "lên lịch du lịch đi",
    ],
)
def test_contextual_continuation_grammar_rejects_explicit_off_topic_objects(
    text: str,
) -> None:
    assert ScopeGuard.may_be_contextual_continuation(text) is False


def test_contextual_continuation_requires_an_accepted_health_anchor() -> None:
    guard = ScopeGuard()
    history = [
        SimpleNamespace(role="user", content="Tôi muốn ăn burger phô mai"),
        SimpleNamespace(role="assistant", content="Mình có thể gợi ý một phiên bản."),
    ]

    decision = guard.contextualize_continuation("gợi ý đi", history)

    assert decision is not None
    assert decision.category == ScopeCategory.IN_SCOPE_NUTRITION
    assert decision.intent == ScopeIntent.NUTRITION
    assert decision.reason_code == "CONTEXTUAL_CONTINUATION"
    assert decision.method == "SESSION_CONTEXT:RULE"
    assert decision.allowed_text == "gợi ý đi"


@pytest.mark.parametrize("reply", ["cả 2", "cả hai"])
def test_combined_plan_reply_binds_to_previous_plan_question(reply: str) -> None:
    guard = ScopeGuard()
    history = [
        SimpleNamespace(role="user", content="Lên kế hoạch ngày mai cho tôi"),
        SimpleNamespace(
            role="assistant",
            content="Bạn muốn lên kế hoạch ăn uống, tập luyện hay cả hai?",
        ),
    ]

    decision = guard.contextualize_continuation(reply, history)

    assert decision is not None
    assert decision.category == ScopeCategory.IN_SCOPE_MEAL_PLAN
    assert decision.reason_code == "CONTEXTUAL_CONTINUATION"
    assert decision.allowed_text == reply


def test_contextual_continuation_fails_closed_without_health_anchor() -> None:
    guard = ScopeGuard()
    history = [SimpleNamespace(role="user", content="Viết code Python")]

    assert guard.contextualize_continuation("gợi ý đi", history) is None
    assert guard.contextualize_continuation("gợi ý phim đi", history) is None


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
async def test_slm_scope_gate_is_authoritative_before_the_encoder() -> None:
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

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert decision.method == "SLM_SCOPE_GATE:judge-v1"
    assert primary.calls == 0
    assert judge.calls == 1


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
    assert decision.method == "SLM_SCOPE_GATE:judge-v1"
    assert primary.calls == 0
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_high_confidence_slm_oos_does_not_defer_to_encoder() -> None:
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

    assert decision.category == ScopeCategory.OUT_OF_SCOPE
    assert decision.should_call_main_llm is False
    assert decision.reason_code == "SHOULD_NOT_RUN"
    assert primary.calls == 0
    assert judge.calls == 1


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
    assert decision.method == "SLM_SCOPE_GATE:judge-v1"
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
async def test_only_hard_safety_bypasses_slm_scope_gate() -> None:
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
    assert coding.category == ScopeCategory.IN_SCOPE_NUTRITION
    assert primary.calls == 0
    assert judge.calls == 1


@pytest.mark.asyncio
async def test_slm_scope_gate_runs_for_clear_and_ambiguous_input() -> None:
    classifier = _Classifier(
        TopicPrediction(ScopeCategory.IN_SCOPE_PROFILE_APP, 0.91, "APP_SUPPORT", "scope-slm-v1")
    )
    guard = ScopeGuard(classifier)

    clear = await guard.classify("Tối nay tôi nên ăn gì?")
    ambiguous = await guard.classify("Hỗ trợ mục tiêu của mình")

    assert clear.category == ScopeCategory.IN_SCOPE_PROFILE_APP
    assert classifier.calls == 2
    assert ambiguous.category == ScopeCategory.IN_SCOPE_PROFILE_APP
    assert ambiguous.method == "SLM_SCOPE_GATE:scope-slm-v1"


@pytest.mark.asyncio
async def test_clear_off_topic_input_is_still_decided_by_slm() -> None:
    classifier = _Classifier(
        TopicPrediction(ScopeCategory.IN_SCOPE_NUTRITION, 0.99, "WRONG_OVERRIDE", "scope-slm-v1")
    )

    decision = await ScopeGuard(classifier).classify("Viết code Flutter đăng nhập Firebase")

    assert decision.category == ScopeCategory.IN_SCOPE_NUTRITION
    assert classifier.calls == 1


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
async def test_json_classifier_has_bounded_context_but_no_tools_or_answer_authority() -> None:
    llm = _JSONLLM(
        LLMResponse(
            full_text=(
                '{"intent":"OUT_OF_SCOPE","scope":"OUT_OF_SCOPE",'
                '"confidence":0.97,"reason_code":"PROGRAMMING_REQUEST"}'
            )
        )
    )
    classifier = StrictJSONScopeClassifier(llm, model_version="scope-slm-v1")

    prediction = await classifier.classify_with_context(
        "Viết quicksort",
        recent_history=[
            SimpleNamespace(role="user", content="Tôi muốn ăn lành mạnh"),
            SimpleNamespace(role="assistant", content="Bạn muốn ăn món nào?"),
        ],
    )

    assert prediction.scope == ScopeCategory.OUT_OF_SCOPE
    assert prediction.intent == ScopeIntent.OUT_OF_SCOPE
    messages, tools, stream, max_tokens = llm.calls[0]
    assert len(messages) == 2
    assert tools is None
    assert stream is False
    assert max_tokens == 96
    assert "Viết quicksort" not in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["current_text"] == "Viết quicksort"
    assert payload["recent_context"] == [
        {"role": "user", "content": "Tôi muốn ăn lành mạnh"},
        {"role": "assistant", "content": "Bạn muốn ăn món nào?"},
    ]


@pytest.mark.asyncio
async def test_scope_guard_passes_recent_context_to_slm_gate() -> None:
    class _ContextualClassifier:
        def __init__(self) -> None:
            self.history = None

        async def classify_with_context(self, text, *, recent_history):
            self.history = recent_history
            return TopicPrediction(
                ScopeCategory.IN_SCOPE_MEAL_PLAN,
                0.98,
                "CONTEXTUAL_BOTH",
                "scope-slm-v1",
                ScopeIntent.MEAL_PLANNING,
            )

    classifier = _ContextualClassifier()
    history = [SimpleNamespace(role="assistant", content="Ăn, tập hay cả hai?")]

    decision = await ScopeGuard(classifier).classify("cả 2", history)

    assert classifier.history is history
    assert decision.category == ScopeCategory.IN_SCOPE_MEAL_PLAN
    assert decision.method == "SLM_SCOPE_GATE:scope-slm-v1"


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
