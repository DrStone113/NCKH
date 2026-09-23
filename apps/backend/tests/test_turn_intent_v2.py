import json
from pathlib import Path

import pytest

from services.agent.turn_intent import TurnIntent, classify_turn_intent, is_urgent_health_text


def test_single_meal_does_not_become_plan():
    decision = classify_turn_intent("Tối nay ăn gì?")
    assert decision.primary_intent == TurnIntent.MEAL_SUGGESTION
    assert decision.clarification_required is False


def test_menu_and_workout_are_multi_intent_combined_only_when_planning():
    decision = classify_turn_intent("Lên ăn uống và tập luyện cho 7 ngày")
    assert decision.primary_intent == TurnIntent.COMBINED_PLAN


def test_menu_schedule_is_not_combined_plan():
    decision = classify_turn_intent("Lên thực đơn giảm cân 3 ngày")
    assert decision.primary_intent == TurnIntent.MENU_SCHEDULE
    assert TurnIntent.COMBINED_PLAN not in decision.intents


def test_bare_plan_defaults_to_combined_health_plan():
    decision = classify_turn_intent("Lên kế hoạch ngày mai cho tôi")
    assert decision.primary_intent == TurnIntent.COMBINED_PLAN
    assert decision.clarification_required is False


def test_negated_save_cannot_become_write_intent():
    decision = classify_turn_intent("Đừng lưu kế hoạch này")
    assert "WRITE" in decision.negated_actions
    assert decision.explicit_write_action is None


def test_profile_update_is_not_misclassified_as_an_observation_write():
    decision = classify_turn_intent("Hãy ghi lại dị ứng trong hồ sơ là đậu phộng")

    assert decision.primary_intent == TurnIntent.PROFILE_UPDATE
    assert decision.explicit_write_action is None


def test_health_is_overlay_for_meal_request():
    decision = classify_turn_intent("Đau dạ dày thì tối nay ăn gì?")
    assert decision.primary_intent == TurnIntent.MEAL_SUGGESTION
    assert decision.health_context == ("HEALTH",)


@pytest.mark.parametrize(
    "text",
    [
        "da noi man sau khi an va moi bat dau sung co nguy hiem khong",
        "Tôi sốt cao kèm cứng cổ, có cần đi khám gấp không?",
        "I cannot breathe after eating",
        "TOI DANG NGHI DEN VIEC TU LAM HAI BAN THAN",
    ],
)
def test_urgent_red_flag_categories_are_normalized_before_semantic_routing(text):
    decision = classify_turn_intent(text)

    assert is_urgent_health_text(text) is True
    assert decision.primary_intent == TurnIntent.HEALTH_QUERY
    assert decision.health_context == ("URGENT",)
    assert decision.explicit_write_action is None


def test_negated_red_flag_does_not_create_an_urgent_admission():
    assert is_urgent_health_text("Tôi không đau ngực và vẫn thở bình thường") is False


def test_gradual_weight_goal_is_not_collapsed_into_a_self_harm_phrase():
    decision = classify_turn_intent("Lập thực đơn để giảm cân từ từ")

    assert is_urgent_health_text("Lập thực đơn để giảm cân từ từ") is False
    assert decision.primary_intent == TurnIntent.MENU_SCHEDULE


@pytest.mark.parametrize("text", ["Tôi bị ngất", "Tôi bị ngạt thở", "toi bi ngat"])
def test_fainting_or_suffocation_still_requires_urgent_triage(text):
    assert is_urgent_health_text(text) is True


def test_strict_weight_loss_plan_is_not_mistaken_for_fainting():
    text = "Tôi muốn giảm 10 kg trong 7 ngày, hãy lập kế hoạch thật nghiêm ngặt."
    assert is_urgent_health_text(text) is False


def test_action_intents_outrank_mentioned_meal_or_workout_topics():
    assert classify_turn_intent("Ghi nhận bữa sáng tôi đã ăn").primary_intent == TurnIntent.OBSERVATION_LOG
    assert classify_turn_intent("Trong kế hoạch hiện tại, chuyển buổi tập sang thứ sáu").primary_intent == TurnIntent.PLAN_EDIT
    assert classify_turn_intent("Cập nhật giờ ngủ thường lệ thành mười một giờ").primary_intent == TurnIntent.PROFILE_UPDATE


def test_medical_question_after_exercise_is_a_health_query():
    decision = classify_turn_intent("Đau đầu kéo dài sau khi tập có cần đi khám không?")

    assert decision.primary_intent == TurnIntent.HEALTH_QUERY
    assert decision.health_context == ("HEALTH",)


def test_development_routing_corpus_has_expected_typed_contracts():
    fixture = Path(__file__).with_name("fixtures") / "turn_intent_development_v1.json"
    for case in json.loads(fixture.read_text(encoding="utf-8")):
        decision = classify_turn_intent(case["text"])
        if "primary" in case:
            assert decision.primary_intent == case["primary"], case["text"]
        if "clarification" in case:
            assert decision.clarification_required is case["clarification"], case["text"]
        if "negated" in case:
            assert case["negated"] in decision.negated_actions, case["text"]
        if case.get("health"):
            assert decision.health_context, case["text"]
