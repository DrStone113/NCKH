"""Validation boundary for untrusted mobile semantic-router observations.

The validated value is telemetry only. It is never merged into user context,
model prompts, Context Planner inputs, safety decisions or tool permissions.
"""

from __future__ import annotations

from typing import Any, Final


SCHEMA_VERSION: Final[str] = "semantic-parse-v1"
ROUTER_VERSION: Final[str] = "semantic-router-s1-v1"
KNOWN_INTENTS: Final[frozenset[str]] = frozenset(
    {
        "DAILY_NUTRITION_STATUS",
        "MEAL_RECOMMENDATION",
        "FOOD_NUTRITION_LOOKUP",
        "MEAL_OR_DIET_EVALUATION",
        "WEIGHT_PROGRESS",
        "EXERCISE_RECOVERY",
        "WORKOUT_RECOMMENDATION",
        "PLAN_MANAGEMENT",
        "PROFILE_OR_CONSTRAINT_UPDATE",
        "GENERAL_NUTRITION_KNOWLEDGE",
        "EVIDENCE_HEALTH_QUESTION",
        "FOLLOWUP_EXPLANATION",
        "APP_ACTION",
        "SMALLTALK_OR_OTHER",
    }
)
KNOWN_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "LOG_MEAL",
        "LOG_WEIGHT",
        "LOG_EXERCISE",
        "LOG_LIFESTYLE",
        "CREATE_PLAN",
        "SAVE_PLAN",
        "ACTIVATE_PLAN",
        "UPDATE_PROFILE",
        "DELETE_RECORD",
    }
)
_MODES = frozenset({"off", "shadow", "enforced"})
_AMBIGUITY = frozenset(
    {"LEXICAL", "DOMAIN", "REFERENCE", "CONFLICT", "MISSING_REQUIRED_CONTEXT"}
)
_CONFIRMATIONS = frozenset({"AFFIRM", "REJECT", "CLARIFY"})
_TRANSFORMS = frozenset(
    {
        "UNICODE_CONTROL_REMOVED",
        "WHITESPACE_COLLAPSED",
        "UNAMBIGUOUS_CHAT_TOKEN_CANDIDATE",
        "AMBIGUOUS_CHAT_TOKEN_CANDIDATE",
        "REPEATED_CHARACTER_CANDIDATE",
    }
)
_REASON_CODES = frozenset(
    {
        "MODE_OFF",
        "PENDING_ACTION_AUTHORITATIVE",
        "DETERMINISTIC_HIGH_CONFIDENCE",
        "MODEL_CONFIGURATION_MISSING",
        "MODEL_UNAVAILABLE",
        "MODEL_READ_FAILED",
        "CHECKSUM_MISMATCH",
        "UNSUPPORTED_PLATFORM",
        "SLM_VERIFIED",
        "VERIFIER_REJECTED",
        "INFERENCE_TIMEOUT",
        "INVALID_STRUCTURED_OUTPUT",
        "INFERENCE_FAILED",
    }
)
_PARSER_SOURCES = frozenset(
    {"PENDING_ACTION_FAST_PATH", "DETERMINISTIC_CANDIDATE", "LEGACY_FALLBACK", "ON_DEVICE_SLM"}
)
_VERIFIER_STATUSES = frozenset({"VALID", "INVALID", "FALLBACK"})
_UNCERTAINTY = frozenset(
    {"ROUTE_CONFIDENT", "ROUTE_UNCERTAIN", "CLARIFICATION_REQUIRED"}
)


class SemanticShadowValidationError(ValueError):
    pass


def _short_enum(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise SemanticShadowValidationError(f"INVALID_{field.upper()}")
    return value


def _enum_list(value: Any, allowed: frozenset[str], field: str, limit: int = 8) -> list[str]:
    if not isinstance(value, list) or len(value) > limit:
        raise SemanticShadowValidationError(f"INVALID_{field.upper()}")
    return [_short_enum(item, allowed, field) for item in value]


def validate_semantic_shadow_message(data: Any) -> dict[str, Any]:
    """Return a bounded allowlisted observation or raise.

    Raw/normalized text, entities, prompts, tokens and user/profile data have no
    accepted field and therefore cannot cross this boundary.
    """

    if not isinstance(data, dict):
        raise SemanticShadowValidationError("INVALID_MESSAGE")
    turn_id = data.get("turn_id")
    if not isinstance(turn_id, str) or not 1 <= len(turn_id) <= 64:
        raise SemanticShadowValidationError("INVALID_TURN_ID")
    raw = data.get("observation")
    if not isinstance(raw, dict):
        raise SemanticShadowValidationError("INVALID_OBSERVATION")
    mode = _short_enum(raw.get("mode"), _MODES, "mode")
    slm_invoked = raw.get("slm_invoked")
    raw_length = raw.get("raw_length")
    reason_code = raw.get("reason_code")
    if not isinstance(slm_invoked, bool):
        raise SemanticShadowValidationError("INVALID_SLM_INVOKED")
    if not isinstance(raw_length, int) or isinstance(raw_length, bool) or not 0 <= raw_length <= 20_000:
        raise SemanticShadowValidationError("INVALID_RAW_LENGTH")
    reason_code = _short_enum(reason_code, _REASON_CODES, "reason_code")

    transforms_raw = raw.get("normalization_transforms", [])
    if not isinstance(transforms_raw, list) or len(transforms_raw) > 8:
        raise SemanticShadowValidationError("INVALID_TRANSFORMS")
    transforms: list[dict[str, Any]] = []
    for item in transforms_raw:
        if not isinstance(item, dict):
            raise SemanticShadowValidationError("INVALID_TRANSFORM")
        kind = _short_enum(item.get("kind"), _TRANSFORMS, "transform")
        count = item.get("count")
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 1000:
            raise SemanticShadowValidationError("INVALID_TRANSFORM_COUNT")
        transforms.append({"kind": kind, "count": count})

    candidate_scores_raw = raw.get("candidate_scores", {})
    if not isinstance(candidate_scores_raw, dict) or len(candidate_scores_raw) > 8:
        raise SemanticShadowValidationError("INVALID_CANDIDATE_SCORES")
    candidate_scores: dict[str, int] = {}
    for intent, score in candidate_scores_raw.items():
        safe_intent = _short_enum(intent, KNOWN_INTENTS, "candidate_score_intent")
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 100:
            raise SemanticShadowValidationError("INVALID_CANDIDATE_SCORE")
        candidate_scores[safe_intent] = score

    safe: dict[str, Any] = {
        "turn_id": turn_id,
        "mode": mode,
        "slm_invoked": slm_invoked,
        "reason_code": reason_code,
        "raw_length": raw_length,
        "normalization_transforms": transforms,
        "candidate_scores": candidate_scores,
        "authoritative_route": "LEGACY_BACKEND",
    }
    parse = raw.get("parse")
    if parse is None:
        return safe
    if not isinstance(parse, dict):
        raise SemanticShadowValidationError("INVALID_PARSE")
    if parse.get("schema_version") != SCHEMA_VERSION or parse.get("semantic_router_version") != ROUTER_VERSION:
        raise SemanticShadowValidationError("VERSION_MISMATCH")
    primary = _short_enum(parse.get("primary_intent"), KNOWN_INTENTS, "primary_intent")
    secondary = _enum_list(parse.get("secondary_intents"), KNOWN_INTENTS, "secondary_intents")
    candidates = _enum_list(parse.get("candidate_intents"), KNOWN_INTENTS, "candidate_intents")
    negated = _enum_list(parse.get("negated_actions"), KNOWN_ACTIONS, "negated_actions")
    write_intent = parse.get("write_intent")
    if not isinstance(write_intent, bool):
        raise SemanticShadowValidationError("INVALID_WRITE_INTENT")
    if write_intent and negated:
        raise SemanticShadowValidationError("NEGATED_WRITE_CONFLICT")
    confirmation = parse.get("confirmation_intent")
    if confirmation is not None:
        confirmation = _short_enum(confirmation, _CONFIRMATIONS, "confirmation_intent")
    ambiguity_status = parse.get("ambiguity_status")
    ambiguity_type = parse.get("ambiguity_type")
    if ambiguity_status not in {"NONE", "AMBIGUOUS"}:
        raise SemanticShadowValidationError("INVALID_AMBIGUITY_STATUS")
    if ambiguity_type is not None:
        ambiguity_type = _short_enum(ambiguity_type, _AMBIGUITY, "ambiguity_type")
    if (ambiguity_status == "NONE") != (ambiguity_type is None):
        raise SemanticShadowValidationError("AMBIGUITY_INCONSISTENT")
    latency_ms = parse.get("latency_ms")
    if not isinstance(latency_ms, int) or isinstance(latency_ms, bool) or not 0 <= latency_ms <= 120_000:
        raise SemanticShadowValidationError("INVALID_LATENCY")
    parser_source = _short_enum(parse.get("parser_source"), _PARSER_SOURCES, "parser_source")
    verifier_status = _short_enum(parse.get("verifier_status"), _VERIFIER_STATUSES, "verifier_status")
    uncertainty = _short_enum(parse.get("uncertainty"), _UNCERTAINTY, "uncertainty")
    if parse.get("normalizer_version") != "semantic-normalizer-v1" or parse.get("parser_version") != ROUTER_VERSION:
        raise SemanticShadowValidationError("COMPONENT_VERSION_MISMATCH")
    model_id = parse.get("model_id")
    quantization = parse.get("model_quantization")
    model_hash = parse.get("model_hash")
    if model_id not in {None, "Qwen/Qwen3-0.6B-GGUF"}:
        raise SemanticShadowValidationError("INVALID_MODEL_ID")
    if quantization not in {None, "Q4_K_M", "Q8_0"}:
        raise SemanticShadowValidationError("INVALID_QUANTIZATION")
    if model_hash is not None and (
        not isinstance(model_hash, str)
        or len(model_hash) != 64
        or any(character not in "0123456789abcdef" for character in model_hash.lower())
    ):
        raise SemanticShadowValidationError("INVALID_MODEL_HASH")

    safe["parse"] = {
        "schema_version": SCHEMA_VERSION,
        "semantic_router_version": ROUTER_VERSION,
        "normalizer_version": "semantic-normalizer-v1",
        "primary_intent": primary,
        "secondary_intents": secondary,
        "candidate_intents": candidates,
        "write_intent": write_intent,
        "negated_actions": negated,
        "confirmation_intent": confirmation,
        "ambiguity_status": ambiguity_status,
        "ambiguity_type": ambiguity_type,
        "parser_source": parser_source,
        "parser_version": ROUTER_VERSION,
        "model_id": model_id,
        "model_quantization": quantization,
        "model_hash": model_hash,
        "latency_ms": latency_ms,
        "verifier_status": verifier_status,
        "uncertainty": uncertainty,
    }
    return safe


__all__ = [
    "SemanticShadowValidationError",
    "validate_semantic_shadow_message",
]
