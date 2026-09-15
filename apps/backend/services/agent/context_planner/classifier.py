"""Deterministic, interpretable English/Vietnamese intent classification."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from .contracts import INTENT_VERSION, Intent


@dataclass(frozen=True, slots=True)
class IntentClassification:
    intent_version: str
    primary_intent: Intent
    secondary_intents: tuple[Intent, ...]
    confidence: float
    method: str
    reason_codes: tuple[str, ...]
    clarification_required: bool
    explicit_write: bool
    action_kind: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "intent_version": self.intent_version,
            "primary_intent": self.primary_intent.value,
            "secondary_intents": [item.value for item in self.secondary_intents],
            "confidence": self.confidence,
            "method": self.method,
            "reason_codes": list(self.reason_codes),
            "clarification_required": self.clarification_required,
            "explicit_write": self.explicit_write,
            "action_kind": self.action_kind,
        }


def _normalized(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", without_marks).strip()


def _has(text: str, *phrases: str) -> bool:
    padded = f" {text} "
    return any(f" {phrase} " in padded for phrase in phrases)


_PRIORITY = tuple(Intent)


def classify_intent(query: str) -> IntentClassification:
    """Classify a turn without an LLM, tools, retrieval, or mutable state."""

    text = _normalized(query)
    scores: dict[Intent, int] = {}
    reasons: dict[Intent, list[str]] = {}

    def add(intent: Intent, score: int, reason: str) -> None:
        scores[intent] = scores.get(intent, 0) + score
        reasons.setdefault(intent, []).append(reason)

    # Mentions never grant writes; an explicit mutation verb and object do.
    write_verb = _has(
        text, "log", "record", "save", "ghi", "ghi lai", "ghi nhan",
        "luu", "cap nhat", "them",
    )
    action_kind: str | None = None
    if write_verb and _has(text, "bua an", "mon an", "meal", "food", "breakfast", "lunch", "dinner"):
        action_kind = "LOG_MEAL"
    elif write_verb and _has(text, "can nang", "weight", "kg"):
        action_kind = "LOG_WEIGHT"
    elif write_verb and _has(text, "bai tap", "tap luyen", "exercise", "workout"):
        action_kind = "LOG_EXERCISE"
    elif write_verb and _has(text, "giac ngu", "sleep", "stress", "loi song", "lifestyle"):
        action_kind = "LOG_LIFESTYLE"
    elif _has(text, "mo man hinh", "navigate", "open screen"):
        action_kind = "NAVIGATE"
    if action_kind:
        add(Intent.APP_ACTION, 12, f"EXPLICIT_{action_kind}")

    if _has(text, "di ung", "allergy", "khong an hai san", "tranh hai san", "seafood restriction", "an chay", "vegetarian", "vegan"):
        add(Intent.PROFILE_OR_CONSTRAINT_UPDATE, 9, "EXPLICIT_CONSTRAINT")

    daily_words = _has(text, "hom nay", "today", "trong ngay")
    remaining = _has(text, "con bao nhieu", "remain", "remaining", "con lai", "da an bao nhieu")
    nutrition_metric = _has(text, "calo", "calorie", "calories", "kcal", "protein", "dam", "carb", "fat", "chat beo", "macro")
    if (daily_words and nutrition_metric) or (remaining and nutrition_metric):
        add(Intent.DAILY_NUTRITION_STATUS, 10, "CURRENT_NUTRITION_STATE")

    if _has(text, "an qua", "overeating", "vuot muc", "qua nhieu calo", "qua muc"):
        add(Intent.MEAL_OR_DIET_EVALUATION, 12, "DIET_EVALUATION")
    if _has(text, "thuc don", "menu", "phu hop muc tieu", "dap ung muc tieu", "danh gia bua"):
        add(Intent.MEAL_OR_DIET_EVALUATION, 9, "MENU_COMPATIBILITY")

    recommendation = _has(text, "goi y", "de xuat", "recommend", "suggest", "nen an gi", "what should i eat")
    meal_words = _has(text, "bua toi", "bua trua", "bua sang", "bua an", "mon an", "mon", "dinner", "lunch", "breakfast", "meal", "post workout")
    if recommendation and meal_words:
        add(Intent.MEAL_RECOMMENDATION, 10, "MEAL_RECOMMENDATION")
    if _has(text, "sau tap", "post workout", "phuc hoi sau tap") and meal_words:
        add(Intent.MEAL_RECOMMENDATION, 8, "POST_WORKOUT_MEAL")

    if _has(text, "dinh duong cua", "nutrition of", "bao nhieu calo trong", "protein trong", "tra cuu thuc pham", "nutrients in"):
        add(Intent.FOOD_NUTRITION_LOOKUP, 10, "FOOD_DATABASE_LOOKUP")
    if _has(text, "can nang", "weight") and _has(text, "xu huong", "trend", "7 ngay", "bay ngay", "tuan qua", "progress", "thay doi"):
        add(Intent.WEIGHT_PROGRESS, 11, "WEIGHT_TREND")
    if _has(text, "ke hoach", "plan") and _has(text, "hien tai", "active", "dang theo", "tien do", "status", "hoan thanh"):
        add(Intent.PLAN_MANAGEMENT, 10, "ACTIVE_PLAN_STATUS")
    if _has(text, "tai sao", "vi sao", "why") and _has(text, "truoc", "previous", "vua", "mon do", "recommended"):
        add(Intent.FOLLOWUP_EXPLANATION, 11, "PRIOR_TURN_PROVENANCE")

    evidence = _has(text, "bang chung", "evidence", "nghien cuu", "clinical", "lam sang", "y khoa", "systematic review")
    health = _has(text, "benh", "disease", "tieu duong", "diabetes", "huyet ap", "cholesterol", "ung thu", "medical", "suc khoe")
    if evidence and health:
        add(Intent.EVIDENCE_HEALTH_QUESTION, 13, "MEDICAL_EVIDENCE_REQUEST")

    general_question = _has(text, "la gi", "what is", "tai sao", "why", "loi ich", "benefit", "benefits", "nen an bao nhieu", "how much")
    nutrition_topic = _has(text, "chat xo", "fibre", "fiber", "vitamin", "dinh duong", "protein", "carbohydrate", "chat beo")
    if general_question and nutrition_topic and not daily_words and not evidence:
        add(Intent.GENERAL_NUTRITION_KNOWLEDGE, 7, "GENERAL_NUTRITION_EXPLANATION")

    workout_words = _has(text, "bai tap", "tap luyen", "workout", "exercise")
    if recommendation and workout_words and action_kind != "LOG_EXERCISE":
        add(Intent.WORKOUT_RECOMMENDATION, 10, "WORKOUT_RECOMMENDATION")
    lifestyle = _has(text, "giac ngu", "sleep", "stress", "cang thang", "met moi", "recovery", "phuc hoi", "loi song")
    if lifestyle and not action_kind:
        add(Intent.EXERCISE_RECOVERY, 8, "RECOVERY_OR_LIFESTYLE")
    casual = _has(text, "xin chao", "hello", "hi", "cam on", "thank you", "ban khoe khong", "chao buoi")
    if casual:
        add(Intent.SMALLTALK_OR_OTHER, 6, "CASUAL_CONVERSATION")

    if not scores:
        return IntentClassification(
            INTENT_VERSION, Intent.SMALLTALK_OR_OTHER, (), 0.45,
            "DETERMINISTIC_SAFE_FALLBACK", ("NO_STRONG_RULE",), True, False, None,
        )
    ordered = sorted(scores, key=lambda item: (-scores[item], _PRIORITY.index(item)))
    primary = ordered[0]
    secondary = tuple(item for item in ordered[1:] if scores[item] >= 8 and scores[item] >= scores[primary] - 5)
    if primary == Intent.FOLLOWUP_EXPLANATION:
        secondary = ()
    elif primary == Intent.MEAL_OR_DIET_EVALUATION:
        secondary = tuple(item for item in secondary if item != Intent.DAILY_NUTRITION_STATUS)
    clarification = len(secondary) > 1 or (scores[primary] < 7 and primary != Intent.SMALLTALK_OR_OTHER)
    confidence = min(0.99, 0.60 + scores[primary] / 30.0)
    reason_codes = tuple(dict.fromkeys(reasons[primary] + [f"SECONDARY_{item.value}" for item in secondary]))
    return IntentClassification(
        INTENT_VERSION, primary, secondary, confidence, "DETERMINISTIC_RULES",
        reason_codes, clarification, action_kind is not None, action_kind,
    )


__all__ = ["IntentClassification", "classify_intent"]
