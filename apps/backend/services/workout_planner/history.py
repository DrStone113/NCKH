"""Normalization of authoritative and legacy exercise history for E4.0."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from services.workout_planner.contracts import (
    ExercisePerformance,
    HistoryCoverage,
    StateObservation,
    StateStatus,
    TrainingState,
)


HISTORY_NORMALIZATION_VERSION = "exercise-history-normalization-v1.0.0"

LEGACY_HISTORY_COVERAGE: dict[str, str] = {
    "sessions_last_7d": "DERIVABLE",
    "sessions_last_28d": "DERIVABLE",
    "resistance_sessions_last_7d": "DERIVABLE",
    "aerobic_minutes_last_7d": "DERIVABLE",
    "last_session_at": "DERIVABLE",
    "last_exercise_performed_at": "DERIVABLE",
    "muscle_exposure_7d": "PARTIAL",
    "muscle_exposure_28d": "PARTIAL",
    "movement_exposure_7d": "PARTIAL",
    "movement_exposure_28d": "PARTIAL",
    "exercise_performance_history": "PARTIAL",
    "recent_sets": "MISSING",
    "recent_reps": "MISSING",
    "recent_load_kg": "MISSING",
    "recent_RPE": "MISSING",
    "recent_RIR": "MISSING",
    "completion_rate": "DERIVABLE",
    "missed_sessions": "MISSING",
    "reported_pain_events": "MISSING",
    "recent_substitutions": "MISSING",
    "active_workout_plan_status": "PARTIAL",
}


def legacy_history_coverage() -> dict[str, str]:
    """Return the explicit E4 classification of the current mobile log schema."""

    return dict(LEGACY_HISTORY_COVERAGE)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            try:
                parsed = datetime.combine(date.fromisoformat(raw[:10]), time.min)
            except ValueError:
                return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _observation(
    value: Any,
    *,
    computed_at: datetime,
    window: str,
    status: StateStatus,
    coverage: HistoryCoverage,
    provenance: str,
) -> StateObservation:
    return StateObservation(
        value=value,
        source="AUTHORITATIVE_EXERCISE_HISTORY",
        observation_window=window,
        computed_at=computed_at,
        status=status,
        provenance=f"{HISTORY_NORMALIZATION_VERSION}:{provenance}",
        coverage=coverage,
    )


def _unavailable_state(computed_at: datetime, status: StateStatus) -> TrainingState:
    def missing(window: str = "NOT_OBSERVED") -> StateObservation:
        return _observation(
            None,
            computed_at=computed_at,
            window=window,
            status=status,
            coverage=HistoryCoverage.MISSING,
            provenance="HISTORY_NOT_AVAILABLE_NO_ZERO_INFERENCE",
        )

    return TrainingState(
        status=status,
        history_reason_codes=("HISTORY_UNAVAILABLE",),
        sessions_last_7d=missing("7D"),
        sessions_last_28d=missing("28D"),
        resistance_sessions_last_7d=missing("7D"),
        aerobic_minutes_last_7d=missing("7D"),
        last_session_at=missing("ALL_AVAILABLE"),
        last_exercise_performed_at=missing("ALL_AVAILABLE"),
        muscle_exposure_7d=missing("7D"),
        muscle_exposure_28d=missing("28D"),
        movement_exposure_7d=missing("7D"),
        movement_exposure_28d=missing("28D"),
        exercise_performance_history=missing("ALL_AVAILABLE"),
        recent_sets=missing("MOST_RECENT_PERFORMANCE"),
        recent_reps=missing("MOST_RECENT_PERFORMANCE"),
        recent_load_kg=missing("MOST_RECENT_PERFORMANCE"),
        recent_rpe=missing("MOST_RECENT_PERFORMANCE"),
        recent_rir=missing("MOST_RECENT_PERFORMANCE"),
        completion_rate=missing("28D"),
        missed_sessions=missing("28D"),
        reported_pain_events=missing("28D"),
        recent_substitutions=missing("28D"),
        active_workout_plan_status=missing("CURRENT"),
    )


def _source_id(record: dict[str, Any]) -> int | None:
    direct = record.get("source_exercise_id")
    if isinstance(direct, int) and not isinstance(direct, bool):
        return direct
    template = str(record.get("exerciseTemplateId") or record.get("exercise_template_id") or "")
    if template.casefold().startswith("wger_"):
        try:
            return int(template.split("_", 1)[1])
        except (ValueError, IndexError):
            return None
    return None


def _performance(record: dict[str, Any], canonical: dict[str, Any], observed_at: datetime) -> ExercisePerformance | None:
    advanced_fields = {
        "completed_sets", "prescribed_sets", "sets", "reps", "load_kg", "rpe", "rir",
        "pain_reported", "technique_stable", "consecutive_successes", "consecutive_misses",
    }
    if not advanced_fields.intersection(record):
        return None
    reps_value = record.get("reps")
    if isinstance(reps_value, (list, tuple)):
        reps = tuple(int(item) for item in reps_value if isinstance(item, int) and not isinstance(item, bool))
    elif isinstance(reps_value, int) and not isinstance(reps_value, bool):
        reps = (reps_value,)
    else:
        reps = ()
    completed = record.get("completed")
    if completed is None:
        completed = record.get("isCompleted")
    return ExercisePerformance(
        canonical_exercise_id=canonical["exercise_id"],
        source_exercise_id=canonical["source_exercise_id"],
        observed_at=observed_at,
        completed_sets=record.get("completed_sets"),
        prescribed_sets=record.get("prescribed_sets", record.get("sets")),
        reps=reps,
        load_kg=float(record["load_kg"]) if isinstance(record.get("load_kg"), (int, float)) and not isinstance(record.get("load_kg"), bool) else None,
        rpe=float(record["rpe"]) if isinstance(record.get("rpe"), (int, float)) and not isinstance(record.get("rpe"), bool) else None,
        rir=float(record["rir"]) if isinstance(record.get("rir"), (int, float)) and not isinstance(record.get("rir"), bool) else None,
        completed=completed if isinstance(completed, bool) else None,
        pain_reported=record.get("pain_reported") if isinstance(record.get("pain_reported"), bool) else None,
        technique_stable=record.get("technique_stable") if isinstance(record.get("technique_stable"), bool) else None,
        consecutive_successes=max(0, int(record.get("consecutive_successes") or 0)),
        consecutive_misses=max(0, int(record.get("consecutive_misses") or 0)),
    )


def normalize_training_history(
    records: Iterable[dict[str, Any]] | None,
    *,
    computed_at: datetime | None = None,
    source_status: StateStatus = StateStatus.KNOWN,
    missed_sessions: int | None = None,
    active_workout_plan_status: str | None = None,
) -> TrainingState:
    """Build TrainingState without inventing missing legacy observations."""

    now = computed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if records is None or source_status in {StateStatus.NOT_LOADED, StateStatus.ERROR, StateStatus.STALE}:
        return _unavailable_state(now, source_status if source_status != StateStatus.KNOWN else StateStatus.NOT_LOADED)

    rows = [dict(item) for item in records]
    catalog = load_canonical_exercise_catalog()
    by_source = {item["source_exercise_id"]: item for item in catalog}
    by_canonical = {item["exercise_id"]: item for item in catalog}
    normalized: list[tuple[dict[str, Any], datetime, dict[str, Any] | None]] = []
    invalid_dates = 0
    for row in rows:
        observed = _parse_datetime(row.get("date") or row.get("performed_at") or row.get("completed_at"))
        if observed is None:
            invalid_dates += 1
            continue
        canonical = by_canonical.get(row.get("canonical_exercise_id")) or by_source.get(_source_id(row))
        normalized.append((row, observed, canonical))
    normalized.sort(key=lambda item: item[1])
    recent7 = [item for item in normalized if item[1] >= now - timedelta(days=7)]
    recent28 = [item for item in normalized if item[1] >= now - timedelta(days=28)]

    def counts(items: list[tuple[dict[str, Any], datetime, dict[str, Any] | None]], kind: str) -> tuple[tuple[str, int], ...]:
        counter: Counter[str] = Counter()
        for _, _, canonical in items:
            if canonical is None:
                continue
            if kind == "muscle":
                counter.update(muscle.get("name_en") or muscle.get("name") or str(muscle.get("id")) for muscle in canonical.get("primary_muscles") or [])
            else:
                movement = (canonical.get("movement_pattern") or {}).get("value")
                if movement and movement != "UNKNOWN":
                    counter[movement] += 1
        return tuple(sorted(counter.items()))

    mapped_count = sum(canonical is not None for _, _, canonical in normalized)
    exposure_coverage = HistoryCoverage.DERIVABLE if mapped_count == len(normalized) else HistoryCoverage.PARTIAL
    exposure_status = StateStatus.KNOWN if mapped_count or not normalized else StateStatus.UNKNOWN
    aerobic_types = {"cardio", "aerobic", "running", "cycling", "walking"}
    resistance7 = sum(str(row.get("type") or "").casefold() not in aerobic_types for row, _, _ in recent7)
    aerobic_minutes7 = sum(
        max(0, int(row.get("duration") or row.get("duration_min") or 0))
        for row, _, _ in recent7
        if str(row.get("type") or "").casefold() in aerobic_types
    )
    performances = tuple(
        performance
        for row, observed, canonical in normalized
        if canonical is not None
        for performance in [_performance(row, canonical, observed)]
        if performance is not None
    )
    latest_performance = performances[-1] if performances else None
    completed_values = [row.get("isCompleted") for row, _, _ in recent28 if isinstance(row.get("isCompleted"), bool)]
    pain_events = [item for item in performances if item.pain_reported is True and item.observed_at >= now - timedelta(days=28)]
    substitutions = [row.get("substituted_from") for row, observed, _ in recent28 if row.get("substituted_from")]
    reason_codes = ["HISTORY_AVAILABLE"]
    if invalid_dates:
        reason_codes.append("HISTORY_PARTIAL_INVALID_DATES")
    if mapped_count < len(normalized):
        reason_codes.append("HISTORY_PARTIAL_CATALOG_MAPPING")
    status = StateStatus.KNOWN if not invalid_dates else StateStatus.CONFLICT

    def known(value: Any, window: str, coverage: HistoryCoverage = HistoryCoverage.DERIVABLE, provenance: str = "DERIVED_FROM_LOGS") -> StateObservation:
        return _observation(value, computed_at=now, window=window, status=StateStatus.KNOWN, coverage=coverage, provenance=provenance)

    def missing(window: str, provenance: str) -> StateObservation:
        return _observation(None, computed_at=now, window=window, status=StateStatus.MISSING, coverage=HistoryCoverage.MISSING, provenance=provenance)

    recent_field_coverage = HistoryCoverage.PARTIAL if performances else HistoryCoverage.MISSING
    return TrainingState(
        status=status,
        history_reason_codes=tuple(reason_codes),
        sessions_last_7d=known(len(recent7), "7D"),
        sessions_last_28d=known(len(recent28), "28D"),
        resistance_sessions_last_7d=known(resistance7, "7D"),
        aerobic_minutes_last_7d=known(aerobic_minutes7, "7D"),
        last_session_at=known(normalized[-1][1] if normalized else None, "ALL_AVAILABLE", HistoryCoverage.DERIVABLE),
        last_exercise_performed_at=known(
            tuple(sorted((canonical["exercise_id"], observed) for _, observed, canonical in normalized if canonical is not None)),
            "ALL_AVAILABLE", exposure_coverage,
        ),
        muscle_exposure_7d=_observation(counts(recent7, "muscle"), computed_at=now, window="7D", status=exposure_status, coverage=exposure_coverage, provenance="CATALOG_JOIN_PRIMARY_MUSCLES"),
        muscle_exposure_28d=_observation(counts(recent28, "muscle"), computed_at=now, window="28D", status=exposure_status, coverage=exposure_coverage, provenance="CATALOG_JOIN_PRIMARY_MUSCLES"),
        movement_exposure_7d=_observation(counts(recent7, "movement"), computed_at=now, window="7D", status=exposure_status, coverage=exposure_coverage, provenance="CATALOG_JOIN_MOVEMENT_PATTERN"),
        movement_exposure_28d=_observation(counts(recent28, "movement"), computed_at=now, window="28D", status=exposure_status, coverage=exposure_coverage, provenance="CATALOG_JOIN_MOVEMENT_PATTERN"),
        exercise_performance_history=_observation(performances, computed_at=now, window="ALL_AVAILABLE", status=StateStatus.KNOWN if performances else StateStatus.MISSING, coverage=recent_field_coverage, provenance="ONLY_STORED_SET_LEVEL_FIELDS"),
        recent_sets=known(latest_performance.completed_sets, "MOST_RECENT_PERFORMANCE", recent_field_coverage, "STORED_VALUE") if latest_performance and latest_performance.completed_sets is not None else missing("MOST_RECENT_PERFORMANCE", "NOT_STORED_IN_LEGACY_LOG"),
        recent_reps=known(latest_performance.reps, "MOST_RECENT_PERFORMANCE", recent_field_coverage, "STORED_VALUE") if latest_performance and latest_performance.reps else missing("MOST_RECENT_PERFORMANCE", "NOT_STORED_IN_LEGACY_LOG"),
        recent_load_kg=known(latest_performance.load_kg, "MOST_RECENT_PERFORMANCE", recent_field_coverage, "STORED_VALUE") if latest_performance and latest_performance.load_kg is not None else missing("MOST_RECENT_PERFORMANCE", "NOT_STORED_IN_LEGACY_LOG"),
        recent_rpe=known(latest_performance.rpe, "MOST_RECENT_PERFORMANCE", recent_field_coverage, "STORED_VALUE") if latest_performance and latest_performance.rpe is not None else missing("MOST_RECENT_PERFORMANCE", "NOT_STORED_IN_LEGACY_LOG"),
        recent_rir=known(latest_performance.rir, "MOST_RECENT_PERFORMANCE", recent_field_coverage, "STORED_VALUE") if latest_performance and latest_performance.rir is not None else missing("MOST_RECENT_PERFORMANCE", "NOT_STORED_IN_LEGACY_LOG"),
        completion_rate=known(round(sum(completed_values) / len(completed_values), 4), "28D") if completed_values else missing("28D", "COMPLETION_NOT_STORED"),
        missed_sessions=known(missed_sessions, "28D", HistoryCoverage.AUTHORITATIVE_AVAILABLE, "ACTIVE_PLAN_COMPARISON") if missed_sessions is not None else missing("28D", "SCHEDULE_NOT_PROVIDED"),
        reported_pain_events=known(len(pain_events), "28D", HistoryCoverage.PARTIAL, "STORED_ENHANCED_LOG_ONLY") if performances else missing("28D", "PAIN_NOT_STORED_IN_LEGACY_LOG"),
        recent_substitutions=known(tuple(substitutions), "28D", HistoryCoverage.PARTIAL, "STORED_ENHANCED_LOG_ONLY") if substitutions else missing("28D", "SUBSTITUTION_NOT_STORED_IN_LEGACY_LOG"),
        active_workout_plan_status=known(active_workout_plan_status, "CURRENT", HistoryCoverage.AUTHORITATIVE_AVAILABLE, "ACTIVE_PLAN_SOURCE") if active_workout_plan_status is not None else missing("CURRENT", "ACTIVE_PLAN_NOT_PROVIDED"),
    )


__all__ = [
    "HISTORY_NORMALIZATION_VERSION",
    "LEGACY_HISTORY_COVERAGE",
    "legacy_history_coverage",
    "normalize_training_history",
]
