"""Typed, multi-intent turn decisions shared by scope, tools and Plan flow."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable


INTENT_VERSION = "turn-intent-v2"


class TurnIntent:
    MEAL_SUGGESTION = "MEAL_SUGGESTION"
    MENU_SCHEDULE = "MENU_SCHEDULE"
    WORKOUT_SCHEDULE = "WORKOUT_SCHEDULE"
    COMBINED_PLAN = "COMBINED_PLAN"
    PLAN_EDIT = "PLAN_EDIT"
    PLAN_LIFECYCLE = "PLAN_LIFECYCLE"
    OBSERVATION_LOG = "OBSERVATION_LOG"
    HEALTH_QUERY = "HEALTH_QUERY"
    PROFILE_UPDATE = "PROFILE_UPDATE"
    GENERAL_WELLNESS = "GENERAL_WELLNESS"


@dataclass(frozen=True, slots=True)
class TurnIntentDecision:
    intent_version: str
    primary_intent: str
    secondary_intents: tuple[str, ...]
    health_context: tuple[str, ...]
    negated_actions: tuple[str, ...]
    explicit_write_action: str | None
    clarification_required: bool
    confidence: float
    reason_codes: tuple[str, ...]
    method: str = "SEMANTIC_TURN_RULES_V2"

    @property
    def intents(self) -> tuple[str, ...]:
        return (self.primary_intent, *self.secondary_intents)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_version": self.intent_version,
            "primary_intent": self.primary_intent,
            "secondary_intents": list(self.secondary_intents),
            "health_context": list(self.health_context),
            "negated_actions": list(self.negated_actions),
            "explicit_write_action": self.explicit_write_action,
            "clarification_required": self.clarification_required,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
            "method": self.method,
        }


def normalize_turn_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold().replace("đ", "d"))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _has(text: str, phrases: Iterable[str]) -> bool:
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases)


_URGENT_SIMPLE_CUES = (
    "dau nguc", "tuc nguc", "kho tho", "nghet tho", "khong tho duoc",
    "shortness of breath", "cannot breathe", "ngat", "bat tinh", "mat y thuc",
    "co giat", "seizure", "phan ve", "soc phan ve", "sung luoi", "sung hong",
    "chay mau khong cam", "chay mau nhieu", "xuat huyet", "bleeding heavily",
    "meo mieng", "yeu liet nua nguoi", "noi lap", "dot quy", "stroke",
    "qua lieu", "overdose", "tu lam hai", "muon chet", "khong muon song",
    "self harm", "suicide",
)
_URGENT_NEGATION_PREFIXES = ("khong ", "ko ", "chua ", "not ", "no ")


def _unnegated_phrase(text: str, phrase: str) -> bool:
    padded = f" {text} "
    if f" {phrase} " not in padded:
        return False
    return not any(f" {prefix}{phrase} " in padded for prefix in _URGENT_NEGATION_PREFIXES)


def is_urgent_health_text(text: str) -> bool:
    """Detect emergency red flags before any statistical semantic routing.

    The function intentionally models categories rather than fixture wording:
    single high-risk cues, allergic skin reaction plus swelling/breathing
    compromise, and fever plus meningeal stiffness.  Input normalization is
    shared with turn intent so Vietnamese diacritics, case and punctuation do
    not change admission behavior.
    """
    # Keep this spelling check before tone removal. Vietnamese self-harm and
    # "gradually" phrases can otherwise normalize to the same ASCII tokens.
    raw = unicodedata.normalize("NFC", str(text or "")).casefold()
    raw = re.sub(r"\s+", " ", raw).strip()
    if "tự tử" in raw:
        return True
    normalized = normalize_turn_text(text)
    if any(_unnegated_phrase(normalized, phrase) for phrase in _URGENT_SIMPLE_CUES):
        return True
    allergic_skin = _has(normalized, ("noi man", "phat ban", "may day", "hives", "rash"))
    allergic_compromise = any(
        _unnegated_phrase(normalized, phrase)
        for phrase in ("sung", "kho tho", "nghet tho", "sung moi", "sung luoi", "sung hong")
    )
    if allergic_skin and allergic_compromise:
        return True
    return _unnegated_phrase(normalized, "sot cao") and _unnegated_phrase(
        normalized, "cung co"
    )


def classify_turn_intent(text: str) -> TurnIntentDecision:
    normalized = normalize_turn_text(text)
    if not normalized:
        return TurnIntentDecision(
            INTENT_VERSION, TurnIntent.GENERAL_WELLNESS, (), (), (), None,
            True, 0.0, ("EMPTY_INPUT",)
        )

    meal = _has(normalized, (
        "an gi", "bua sang", "bua trua", "bua toi", "bua an", "ba bua", "an dung gio", "mon gi",
        "mon an", "goi y mon", "nen an", "dinner", "lunch", "breakfast",
        "meal", "an uong", "thuc don", "menu", "lich an", "ke hoach an", "ke hoach dinh duong",
    ))
    meal_suggestion = _has(normalized, ("an gi", "nen an", "mon gi", "mon j", "mon nao", "mon toi", "bua toi", "bua trua", "bua sang")) or (
        _has(normalized, ("goi y", "suggest"))
        and _has(normalized, ("mon", "bua", "meal"))
    )
    menu = _has(normalized, ("thuc don", "menu", "lich an", "ke hoach an", "ke hoach dinh duong", "meal plan"))
    reminder = _has(normalized, ("nhac toi", "nhac nho", "reminder", "remind me"))
    workout = not reminder and _has(normalized, (
        "lich tap", "ke hoach tap", "bai tap", "tap luyen", "chuong trinh", "gian co",
        "van dong", "di bo", "workout", "exercise", "gym", "tap gi", "tap",
    ))
    plan_word = _has(normalized, (
        "ke hoach", "plan", "ban xem truoc", "ban da luu", "ban sua doi",
        "ke hoach hien tai",
    ))
    create_word = _has(normalized, ("lap", "len", "tao", "xay dung", "create", "build", "make"))
    edit_word = _has(normalized, ("sua", "doi", "thay", "them", "bo", "xoa", "chuyen", "giam", "move", "replace", "edit"))
    lifecycle_word = _has(normalized, ("luu", "lưu", "kich hoat", "active", "tam dung", "huy", "cancel"))
    log_word = _has(normalized, ("ghi", "ghi lai", "ghi nhan", "nhat ky", "log", "record", "da an", "da tap"))
    profile_field = _has(normalized, (
        "can nang", "chieu cao", "muc van dong", "muc tieu", "che do an",
        "di ung", "gio ngu", "so buoi tap", "ho so", "profile", "weight",
        "height", "activity level", "diet", "sleep",
    ))
    profile_update = profile_field and _has(normalized, (
        "cap nhat", "sua", "doi", "dat", "ghi lai", "update", "change",
    ))
    lifecycle_word = lifecycle_word or _has(normalized, ("dong ke hoach", "archive plan"))
    comparison = _has(normalized, ("so sanh", "compare", "doi chieu"))
    advisory_only = _has(normalized, ("chi tu van", "just advise", "only advise"))
    urgent = is_urgent_health_text(text)
    health = urgent or _has(normalized, (
        "chong mat", "dau dau", "dau nguc", "kho tho", "ngat", "sot", "buon non", "dau bung",
        "dau day", "da day", "tieu duong", "huyet ap", "di ung", "chan thuong", "benh", "thuoc", "suc khoe",
    ))
    medical_question = _has(normalized, (
        "can di kham", "co can kham", "nguy hiem khong", "co sao khong",
        "can gap bac si", "can cap cuu",
    ))

    negated: list[str] = []
    negation = _has(normalized, (
        "khong", "ko", "chua", "dung", "khong can", "bo qua", "skip",
        "don't", "do not", "never",
    ))
    if negation:
        if _has(normalized, ("luu", "save", "ghi", "record", "log")):
            negated.append("WRITE")
        if _has(normalized, ("tao", "lap", "len", "create", "build", "plan")):
            negated.append("CREATE_PLAN")

    explicit_write = None
    # A profile field can be mentioned with "ghi lại" but remains a typed
    # profile update, not an observation-log command.  This avoids exposing a
    # generic write path for allergy/health-profile edits.
    if log_word and not negation and not profile_update:
        explicit_write = "OBSERVATION_LOG"
    elif lifecycle_word and plan_word and not negation:
        explicit_write = "PLAN_LIFECYCLE"

    intents: list[str] = []
    reasons: list[str] = []
    if health:
        reasons.append("HEALTH_CONTEXT")
    goal_focused_plan = _has(normalized, ("giam can", "tang can"))
    broad_health_plan = _has(normalized, ("cai thien suc khoe", "health plan"))
    if plan_word and lifecycle_word and not comparison:
        intents.append(TurnIntent.PLAN_LIFECYCLE)
        reasons.append("PLAN_LIFECYCLE")
    elif menu and create_word and not workout:
        intents.append(TurnIntent.MENU_SCHEDULE)
        reasons.append("MENU_SCHEDULE")
    elif workout and meal and create_word and not profile_update:
        intents.append(TurnIntent.COMBINED_PLAN)
        reasons.append("MULTI_DOMAIN_PLAN")
    elif plan_word and create_word and broad_health_plan:
        intents.append(TurnIntent.COMBINED_PLAN)
        reasons.append("BROAD_HEALTH_PLAN")
    elif plan_word and create_word and goal_focused_plan:
        intents.append(TurnIntent.MENU_SCHEDULE)
        reasons.append("GOAL_FOCUSED_MENU_PLAN")
    elif plan_word and create_word and not (meal or workout):
        # A generic daily plan in this health app means meals plus a workout.
        # Explicit menu-only and workout-only requests are handled above.
        intents.append(TurnIntent.COMBINED_PLAN)
        reasons.append("DEFAULT_COMBINED_PLAN")
    else:
        # Action intents keep their meaning even when a meal or workout is
        # mentioned. Confirmation and authorization are still downstream.
        if log_word and not profile_update and not advisory_only:
            intents.append(TurnIntent.OBSERVATION_LOG)
            reasons.append("OBSERVATION_LOG")
        if plan_word and edit_word:
            intents.append(TurnIntent.PLAN_EDIT)
            reasons.append("PLAN_EDIT")
        if menu:
            intents.append(TurnIntent.MENU_SCHEDULE)
            reasons.append("MENU_SCHEDULE")
        elif meal_suggestion:
            intents.append(TurnIntent.MEAL_SUGGESTION)
            reasons.append("MEAL_SUGGESTION")
        if workout:
            intents.append(TurnIntent.WORKOUT_SCHEDULE)
            reasons.append("WORKOUT_SCHEDULE")
        if profile_update:
            # Recommendation remains primary when it is explicitly requested
            # alongside a profile change; standalone profile updates lead.
            if meal_suggestion:
                intents.append(TurnIntent.PROFILE_UPDATE)
            else:
                intents.insert(0, TurnIntent.PROFILE_UPDATE)
            reasons.append("PROFILE_UPDATE")
    if explicit_write:
        intents.append(explicit_write)
        reasons.append("EXPLICIT_WRITE")

    if health:
        # A medical-risk question remains health-led even if it mentions a
        # prior workout. Explicit meal selection stays a separate user task.
        if not intents:
            intents.append(TurnIntent.HEALTH_QUERY)
        elif (
            medical_question
            and not meal_suggestion
            and not profile_update
            and TurnIntent.HEALTH_QUERY not in intents
        ):
            intents.insert(0, TurnIntent.HEALTH_QUERY)

    if not intents:
        intents = [TurnIntent.GENERAL_WELLNESS]
        reasons.append("NO_TYPED_DOMAIN")

    # Keep health as an overlay, never as a reason to discard the task.
    primary = intents[0]
    secondary = tuple(dict.fromkeys(intents[1:]))
    clarification = False
    if primary == TurnIntent.MEAL_SUGGESTION and menu:
        primary = TurnIntent.MENU_SCHEDULE
        secondary = tuple(item for item in secondary if item != TurnIntent.MEAL_SUGGESTION)
    confidence = 0.92 if (
        len(intents) > 1 or meal or workout or health or plan_word or profile_update or log_word
    ) else 0.55
    if clarification:
        confidence = 0.42
    return TurnIntentDecision(
        INTENT_VERSION, primary, secondary,
        (("URGENT",) if urgent else ("HEALTH",)) if health else (),
        tuple(negated), explicit_write, clarification, confidence,
        tuple(dict.fromkeys(reasons)),
    )


__all__ = ["INTENT_VERSION", "TurnIntent", "TurnIntentDecision", "classify_turn_intent", "is_urgent_health_text", "normalize_turn_text"]
