"""Tests for per-turn routing (:mod:`services.agent.turn_router`).

The router decides how much machinery a message gets. Two failure modes matter
and they are asymmetric:

- Misrouting a real request to ``chitchat`` strips its tools, so the bot answers
  from thin air. This is the expensive mistake.
- Misrouting chit-chat to ``simple`` merely costs a few tokens.

So the tests below lean hard on "when in doubt, keep the tools".
"""

from __future__ import annotations

import pytest

from services.agent.turn_router import CHITCHAT, COMPLEX, SIMPLE, classify_turn


@pytest.mark.parametrize(
    "text",
    [
        "chào bạn",
        "Xin chào!",
        "hi",
        "cảm ơn nhé",
        "Cảm ơn bạn nhiều",
        "ok",
        "oke",
        "vâng",
        "hiểu rồi",
        "tạm biệt",
        "bạn là ai",
    ],
)
def test_greetings_and_acknowledgements_are_chitchat(text):
    plan = classify_turn(text)
    assert plan.tier == CHITCHAT
    assert plan.offer_tools is False
    assert plan.prompt_mode == "light"
    assert plan.use_heavy_model is False


@pytest.mark.parametrize(
    "text",
    [
        "100g ức gà bao nhiêu calo?",
        "trưa nay mình ăn phở bò",
        "sáng nay chạy 30 phút",
        "tối nay ăn gì được?",
        "hôm nay mình còn bao nhiêu calo",
        "ghi lại giúp mình 500ml nước",
    ],
)
def test_single_concrete_requests_are_simple(text):
    plan = classify_turn(text)
    assert plan.tier == SIMPLE
    assert plan.offer_tools is True
    assert plan.use_heavy_model is False


@pytest.mark.parametrize(
    "text",
    [
        "lên kế hoạch giảm 5kg trong 3 tháng cho mình",
        "phân tích giúp mình tuần vừa rồi ăn uống thế nào",
        "tại sao mình tập mãi mà cân không giảm",
        "mình bị tiểu đường type 2 thì ăn cơm được không",
        "so sánh giúp mình whey với đạm thực vật",
        "mình đang mang thai tháng thứ 4 thì tập được gì",
        "tuần này mình tập thế nào",
    ],
)
def test_analysis_and_planning_go_to_the_heavy_model(text):
    plan = classify_turn(text)
    assert plan.tier == COMPLEX
    assert plan.use_heavy_model is True
    assert plan.offer_tools is True
    assert plan.max_steps >= 6


def test_long_multi_part_message_is_complex():
    text = (
        "mình 25 tuổi nặng 78kg cao 1m72 làm văn phòng ngồi nhiều ít vận động "
        "muốn giảm còn 70kg nhưng không muốn bỏ cơm và mình chỉ tập được buổi "
        "tối ở nhà thôi không có tạ gì cả thì nên bắt đầu thế nào cho hợp lý"
    )
    assert classify_turn(text).tier == COMPLEX


def test_two_questions_in_one_message_is_complex():
    assert classify_turn("ăn tối muộn có mập không? mấy giờ nên ăn?").tier == COMPLEX


def test_blank_input_stays_safe():
    """Empty text must not be routed to the tool-less chitchat path."""
    plan = classify_turn("")
    assert plan.offer_tools is True


def test_question_word_prevents_chitchat_misroute():
    """'chào bạn mình ăn gì' is a request wearing a greeting as a hat."""
    plan = classify_turn("chào bạn, tối nay ăn gì?")
    assert plan.tier != CHITCHAT
    assert plan.offer_tools is True


def test_chitchat_budget_is_a_single_step():
    """A greeting never needs a second LLM round-trip."""
    assert classify_turn("chào bạn").max_steps == 1
