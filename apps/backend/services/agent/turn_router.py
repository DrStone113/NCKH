"""Per-turn routing: how much machinery does this message actually deserve?

Every turn used to pay the same cost — full system prompt, full tool catalog,
the same model — whether the user wrote "cảm ơn bạn" or asked for a 12-week
cutting plan. That is the main reason simple messages felt slow.

This module classifies a turn with pure heuristics (no extra LLM round-trip,
so it adds well under a millisecond). A scope gate first distinguishes app
questions from unrelated requests; accepted turns then enter one of three
cost tiers:

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
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

CHITCHAT = "chitchat"
SIMPLE = "simple"
COMPLEX = "complex"

IN_SCOPE = "in_scope"
OUT_OF_SCOPE = "out_of_scope"
CONTEXTUAL_SCOPE = "contextual_scope"


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
    "giúp tôi với", "giúp mình với", "bạn còn đó không", "bạn ở đó không",
    "test", "hello world",
})

# Only these harmless courtesy modifiers may extend an exact chitchat phrase.
# Any other trailing content is treated as a real request and keeps the full
# prompt/tools. This intentionally prefers a little extra latency over losing
# health or action context after words such as "chào", "ok" or "ừ".
_CHITCHAT_TAIL_WORDS: frozenset[str] = frozenset({
    "ạ", "bạn", "đó", "hen", "lắm", "luôn", "mình", "nè", "nha", "nhé",
    "nhen", "nhiều", "ơi", "quá", "rất", "thôi", "vậy",
})

# High-risk signals are checked before acknowledgements and chitchat. They
# always receive the full safety prompt, tools and the stronger model even
# when the message starts with a greeting or a short "ok".
_SAFETY_TOKENS: tuple[str, ...] = (
    "đau ngực", "dau nguc", "khó thở", "kho tho", "chóng mặt", "chong mat",
    "bị ngất", "bi ngat", "sắp ngất", "sap ngat", "co giật", "co giat",
    "nhịp tim", "nhip tim", "tim đập nhanh", "tim dap nhanh",
    "sốc phản vệ", "soc phan ve", "quá liều", "qua lieu",
    "tự làm hại", "tu lam hai", "tự tử", "tu tu",
)

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

# Scope routing is intentionally local and deterministic. It is not a second
# model call: obvious off-topic requests are rejected before memory, tools or
# the LLM are touched. Signals are accent-folded so typed Vietnamese without
# diacritics behaves the same way.
_APP_SCOPE_CUES: tuple[str, ...] = (
    "an", "uong", "mon", "bua", "thuc don", "dinh duong", "calo", "kcal",
    "protein", "carb", "chat beo", "thuc pham", "nguyen lieu", "cach lam",
    "cong thuc", "nau", "khau phan", "di ung", "kieng", "vitamin", "whey",
    "creatine", "tap", "bai tap", "workout", "gym", "chay", "di bo",
    "the duc", "van dong", "co bap", "chan thuong", "bi dau", "con dau",
    "dau nguc", "dau goi", "dau vai", "dau lung", "can nang", "kg", "bmi",
    "tdee", "giam can", "tang can", "ngu", "mat ngu", "stress", "tam trang",
    "uong nuoc", "met", "suc khoe", "benh", "thuoc", "huyet ap",
    "tieu duong", "tim mach", "mang thai", "cho con bu", "nhac toi",
    "nhac minh", "mo trang", "mo man hinh", "ung dung", "ke hoach",
    "nhat ky", "ghi lai", "ghi vao", "luu lai", "ho so", "thuc hien the nao",
)

_STRICT_OUT_OF_SCOPE_CUES: tuple[str, ...] = (
    "lap trinh", "viet code", "python", "javascript", "java", "c++", "sql",
    "html", "css", "debug", "loi phan mem", "thuat toan", "may tinh",
    "an ninh mang", "dich sang", "dich cau", "viet van", "lam tho",
    "ke chuyen", "truyen cuoi", "chinh tri", "bau cu", "tong thong",
    "quoc hoi", "tin tuc", "chung khoan", "bitcoin", "ty gia", "am nhac",
    "bai hat", "ca si", "dien vien", "phim", "game", "du lich", "khach san",
    "ve may bay", "ai la", "thu do", "lich su", "quoc gia", "dia ly",
    "giai phuong trinh", "dao ham", "tich phan", "hinh hoc", "dai so",
    "so nguyen to",
)

_WEATHER_CUES: tuple[str, ...] = (
    "thoi tiet", "du bao thoi tiet", "nhiet do ngoai troi", "hom nay co mua",
    "troi mua", "troi nang",
)

_FITNESS_WEATHER_CONTEXT: tuple[str, ...] = (
    "tap", "chay", "di bo", "workout", "van dong", "ngoai troi",
)


def _normalise(text: str) -> str:
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[!?.,:;~\-_*#\"']+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _fold_scope_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("đ", "d")
    value = "".join(
        char if char.isalnum() or char.isspace() else " " for char in value
    )
    return " ".join(value.split())


def _has_scope_cue(text: str, cues: tuple[str, ...]) -> bool:
    padded = f" {text} "
    return any(f" {cue} " in padded for cue in cues)


def classify_scope(user_text: str, *, history_len: int | None = None) -> str:
    """Classify whether a turn belongs to the app without calling an LLM.

    ``CONTEXTUAL_SCOPE`` means the text itself is ambiguous (for example
    "vì sao?") and prior chat is needed. Callers can run the function again
    with the actual ``history_len`` after loading lightweight memory.
    """
    if not isinstance(user_text, str) or not user_text.strip():
        return IN_SCOPE

    cleaned = _normalise(user_text)
    if (
        cleaned in _CHITCHAT_EXACT
        or cleaned in _AFFIRMATIVE_RESPONSES
        or _is_extended_chitchat(cleaned)
    ):
        return IN_SCOPE

    folded = _fold_scope_text(user_text)
    has_app_scope = _has_scope_cue(folded, _APP_SCOPE_CUES)

    # Programming, general-knowledge and creative requests remain out of
    # scope even when they mention a health term incidentally (for example
    # "viết code tính BMI").
    if _has_scope_cue(folded, _STRICT_OUT_OF_SCOPE_CUES):
        return OUT_OF_SCOPE

    # Weather is relevant only when the user directly connects it to safe
    # movement or exercise; pure forecasts belong to another application.
    if _has_scope_cue(folded, _WEATHER_CUES):
        if _has_scope_cue(folded, _FITNESS_WEATHER_CONTEXT):
            return IN_SCOPE
        return OUT_OF_SCOPE

    # Pure arithmetic is rejected, while nutrition quantities such as
    # "200 g cơm bao nhiêu kcal" are retained by the app cues above.
    if not has_app_scope:
        compact = re.sub(r"\s+", "", user_text)
        if re.fullmatch(r"[\d()+\-*/%^=.,]+", compact):
            return OUT_OF_SCOPE
        if re.search(r"\d\s*[+\-*/%^]\s*\d", user_text) and _has_scope_cue(
            folded, ("bang bao nhieu", "tinh", "ket qua")
        ):
            return OUT_OF_SCOPE

    if has_app_scope:
        return IN_SCOPE

    if history_len is None:
        return CONTEXTUAL_SCOPE
    if history_len > 0 and len(folded.split()) <= 16:
        return IN_SCOPE
    return OUT_OF_SCOPE


def _is_extended_chitchat(cleaned: str) -> bool:
    """Accept only an exact courtesy phrase plus allowlisted filler words."""

    for phrase in sorted(
        _CHITCHAT_EXACT,
        key=lambda item: (len(item.split()), len(item)),
        reverse=True,
    ):
        prefix = phrase + " "
        if not cleaned.startswith(prefix):
            continue
        tail = cleaned[len(prefix):].split()
        return bool(tail) and all(word in _CHITCHAT_TAIL_WORDS for word in tail)
    return False


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

    if any(token in cleaned for token in _SAFETY_TOKENS):
        return TurnPlan(COMPLEX, True, True, "full", 6)

    # Mid-conversation affirmative responses (e.g. "có", "vâng", "ok" after an AI question)
    # MUST keep tools enabled so the model can execute the confirmed action.
    if history_len > 0 and (cleaned in _AFFIRMATIVE_RESPONSES or (len(words) <= 3 and any(a in cleaned for a in _AFFIRMATIVE_RESPONSES))):
        return TurnPlan(SIMPLE, False, True, "full", 4)

    # ---- tier 1: chitchat ------------------------------------------------- #
    if cleaned in _CHITCHAT_EXACT:
        return TurnPlan(CHITCHAT, False, False, "light", 1)
    # "cảm ơn bạn nhiều nhé" is still courtesy-only, while "chào bạn tôi đau
    # ngực" and "ừ tôi muốn ăn phở" contain meaningful trailing content.
    if _is_extended_chitchat(cleaned):
        return TurnPlan(CHITCHAT, False, False, "light", 1)

    # ---- tier 3: complex -------------------------------------------------- #
    hits = [tok for tok in _COMPLEX_TOKENS if tok in cleaned]
    if hits:
        logger.debug("Turn routed complex on tokens=%s", hits[:3])
        return TurnPlan(COMPLEX, True, True, "full", 6)

    # Long, multi-clause messages carry more than one ask. Note the question
    # marks are counted on the RAW text — ``_normalise`` strips punctuation, so
    # counting on ``cleaned`` would always yield zero.
    if len(words) >= 35 or (cleaned and user_text.count("?") >= 2):
        return TurnPlan(COMPLEX, True, True, "full", 6)

    # ---- tier 2: simple --------------------------------------------------- #
    if any(tok in cleaned for tok in _SIMPLE_TOKENS) or len(words) <= 12:
        return TurnPlan(SIMPLE, False, True, "full", 4)

    return TurnPlan(SIMPLE, False, True, "full", 5)


__all__ = [
    "CHITCHAT", "COMPLEX", "CONTEXTUAL_SCOPE", "IN_SCOPE", "OUT_OF_SCOPE",
    "SIMPLE", "TurnPlan", "classify_scope", "classify_turn",
]
