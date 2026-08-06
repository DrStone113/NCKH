"""Per-turn routing: how much machinery does this message actually deserve?

Every turn used to pay the same cost — full system prompt, full tool catalog,
the same model — whether the user wrote "cảm ơn bạn" or asked for a 12-week
cutting plan. That is the main reason simple messages felt slow.

This module classifies a turn with pure heuristics (no extra LLM round-trip,
so it adds well under a millisecond) into one of three tiers:

``chitchat``
    Greetings, thanks, acknowledgements. Light prompt, light model, **no
    tools offered at all** — which removes the biggest chunk of prompt tokens
    and stops small models from making pointless ``get_user_profile`` calls.
``simple``
    A single concrete question or a short logging statement. Light model,
    full prompt with tools.
``complex``
    Analysis, planning, comparison, troubleshooting, anything multi-part.
    Routed to the heavy model, which is where reasoning quality actually
    matters.

The classifier is deliberately conservative: when in doubt it returns
``simple`` rather than ``chitchat`` (a wrong ``chitchat`` call would strip
tools from a turn that needed them), and escalates to ``complex`` on any
strong signal.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CHITCHAT = "chitchat"
SIMPLE = "simple"
COMPLEX = "complex"


@dataclass(frozen=True, slots=True)
class TurnPlan:
    """Routing decision for a single user turn."""

    tier: str
    use_heavy_model: bool
    offer_tools: bool
    prompt_mode: str
    max_steps: int

    @property
    def is_chitchat(self) -> bool:
        return self.tier == CHITCHAT


# --------------------------------------------------------------------------- #
# Lexicons
# --------------------------------------------------------------------------- #

# Exact-match set: only fires when the whole message is one of these.
_CHITCHAT_EXACT: frozenset[str] = frozenset({
    "hi", "hello", "hey", "chào", "chào bạn", "chào em", "chào anh", "chào chị",
    "xin chào", "chao", "xin chao", "alo", "hế lô", "helu",
    "chào buổi sáng", "chào buổi tối", "good morning", "good night",
    "cảm ơn", "cám ơn", "cảm ơn bạn", "cảm ơn nhé", "cảm ơn nha", "cam on",
    "thanks", "thank you", "thanks bạn", "tks", "tnx",
    "ok", "oke", "okay", "okie", "ừ", "uh", "ừm", "vâng", "dạ", "được",
    "hiểu rồi", "biết rồi", "rõ rồi", "ngon", "tuyệt", "hay quá", "giỏi quá",
    "tạm biệt", "bye", "goodbye", "bai", "chào nhé", "hẹn gặp lại",
    "bạn là ai", "bạn tên gì", "bạn làm được gì", "giúp gì được",
    "test", "hello world", "?", "??", "...",
})

# Any of these words means the turn needs real reasoning.
_COMPLEX_TOKENS: tuple[str, ...] = (
    "kế hoạch", "lộ trình", "giáo án", "thực đơn tuần", "menu tuần", "lịch tập",
    "phân tích", "đánh giá", "nhận xét", "tổng kết", "báo cáo", "thống kê",
    "so sánh", "khác nhau", "nên chọn", "cái nào tốt hơn",
    "tại sao", "vì sao", "lý do", "nguyên nhân", "giải thích",
    "không giảm", "không tăng", "chững", "chậm lại", "mãi mà", "hoài mà",
    "bị sao", "có vấn đề", "sai ở đâu", "khắc phục", "cải thiện",
    "tuần này", "tuần qua", "tháng này", "tháng qua", "mấy tuần", "mấy tháng",
    "xu hướng", "tiến độ", "tiến triển",
    "tiểu đường", "huyết áp", "mỡ máu", "gout", "gút", "dạ dày", "thận",
    "mang thai", "có bầu", "cho con bú", "bệnh nền",
    "tối ưu", "điều chỉnh", "thiết kế", "xây dựng", "lên chương trình",
    # Evidence-seeking questions. These usually trigger a web lookup, and the
    # synthesis step afterwards — weighing sources, noting disagreement — is
    # exactly what the heavy model is better at.
    "nghiên cứu", "bằng chứng", "khoa học", "chứng minh", "thật không",
    "có đúng là", "tin được không", "khuyến nghị", "hướng dẫn", "tiêu chuẩn",
    "tác dụng phụ", "tương tác", "liều lượng", "an toàn không", "có hại",
    "thực hư", "tài liệu", "nguồn nào",
)

# Strong "just do the thing" signals — cheap even if the sentence is longish.
_SIMPLE_TOKENS: tuple[str, ...] = (
    "bao nhiêu calo", "bao nhiêu kcal", "bao nhiêu đạm", "bao nhiêu protein",
    "ghi lại", "ghi vào", "log", "vừa ăn", "vừa tập", "mình ăn", "tôi ăn",
    "mình tập", "tôi tập", "cân nặng hôm nay", "uống nước",
)

_QUESTION_WORDS = ("?", "gì", "nào", "sao", "bao nhiêu", "mấy", "có nên", "được không")


def _normalise(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[!?.,:;~\-_*#\"']+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


_AFFIRMATIVE_RESPONSES: frozenset[str] = frozenset({
    "có", "có chứ", "có nhé", "ừ", "ừm", "vâng", "dạ", "được", "được nhé",
    "ok", "oke", "okay", "okie", "ghi đi", "ghi lại", "ghi nhé", "lưu lại", "lưu đi",
    "đồng ý", "uh", "dạ có", "vâng ạ"
})


def classify_turn(user_text: str, *, history_len: int = 0) -> TurnPlan:
    """Classify ``user_text`` into a :class:`TurnPlan`.

    ``history_len`` is the number of prior turns in the session; a message
    like "ừ" mid-conversation is an acknowledgement, but the very first
    message of a session is more likely a real (if terse) request.
    """
    if not isinstance(user_text, str) or not user_text.strip():
        return TurnPlan(SIMPLE, False, True, "full", 4)

    cleaned = _normalise(user_text)
    words = cleaned.split()

    # Mid-conversation affirmative responses (e.g. "có", "vâng", "ok" after an AI question)
    # MUST keep tools enabled so the model can execute the confirmed action.
    if history_len > 0 and (cleaned in _AFFIRMATIVE_RESPONSES or (len(words) <= 3 and any(a in cleaned for a in _AFFIRMATIVE_RESPONSES))):
        return TurnPlan(SIMPLE, False, True, "full", 4)

    # ---- tier 1: chitchat ------------------------------------------------- #
    if cleaned in _CHITCHAT_EXACT:
        return TurnPlan(CHITCHAT, False, False, "light", 1)
    # "cảm ơn bạn nhiều nhé" — starts with a chitchat phrase and adds nothing.
    if len(words) <= 5 and any(
        cleaned.startswith(phrase) for phrase in _CHITCHAT_EXACT
    ) and not any(q in cleaned for q in _QUESTION_WORDS):
        return TurnPlan(CHITCHAT, False, False, "light", 1)

    # ---- tier 3: complex -------------------------------------------------- #
    hits = [tok for tok in _COMPLEX_TOKENS if tok in cleaned]
    if hits:
        logger.debug("Turn routed complex on tokens=%s", hits[:3])
        return TurnPlan(COMPLEX, True, True, "full", 6)

    # Long, multi-clause messages carry more than one ask. Note the question
    # marks are counted on the RAW text — ``_normalise`` strips punctuation, so
    # counting on ``cleaned`` would always yield zero.
    if len(words) >= 35 or user_text.count("?") >= 2:
        return TurnPlan(COMPLEX, True, True, "full", 6)

    # ---- tier 2: simple --------------------------------------------------- #
    if any(tok in cleaned for tok in _SIMPLE_TOKENS) or len(words) <= 12:
        return TurnPlan(SIMPLE, False, True, "full", 4)

    return TurnPlan(SIMPLE, False, True, "full", 5)


__all__ = ["CHITCHAT", "COMPLEX", "SIMPLE", "TurnPlan", "classify_turn"]
