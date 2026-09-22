"""E4.1 adapters, persistence, and authoritative workout orchestration.

The module deliberately wraps the frozen E4.0 planner instead of copying its
selection or prescription logic.  Flutter/Firestore remains the authoritative
source for legacy profiles and legacy exercise logs; modern E4 plans/results
are persisted in PostgreSQL only after an explicit write request.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Iterable, Mapping
from uuid import uuid4

from sqlalchemy import text

from config import settings
from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from services.workout_planner.contracts import (
    ApplicabilityStatus,
    ExercisePerformance,
    ExerciseProfile,
    ExerciseSafetyProfile,
    ExperienceSource,
    HistoryCoverage,
    PainStatus,
    StateObservation,
    StateStatus,
    TrainingExperience,
    TrainingState,
    WorkoutPlan,
    WorkoutRequest,
)
from services.workout_planner.history import normalize_training_history
from services.workout_planner.planner import (
    PersonalizedWorkoutPlanner,
    build_session_requirement,
    evaluate_safety,
)
from services.workout_planner.presentation import WorkoutPlanPresenter, WorkoutResponseValidator
from services.workout_planner.validator import WorkoutPlanValidator
from services.plan_engine.request_normalization import normalize_workout_goal
from modules.wger.exercise_prescription_policy import ExercisePrescriptionPolicyError


INTEGRATION_VERSION = "workout-planner-e4-1-integration-v1.0.0"
_GOAL_MAP = {
    "maintain": "GENERAL_FITNESS",
    "general_fitness": "GENERAL_FITNESS",
    "lose_weight": "WEIGHT_MANAGEMENT",
    "weight_loss": "WEIGHT_MANAGEMENT",
    "weight_management": "WEIGHT_MANAGEMENT",
    "gain_muscle": "HYPERTROPHY",
    "muscle_gain": "HYPERTROPHY",
    "hypertrophy": "HYPERTROPHY",
    "strength": "STRENGTH",
    "muscular_endurance": "MUSCULAR_ENDURANCE",
    "mobility": "MOBILITY",
    "recovery": "MOBILITY",
    "power": "POWER",
    "aerobic_endurance": "AEROBIC_ENDURANCE",
    "endurance": "ENDURANCE",
}
_COMPLETION_STATUSES = frozenset({"COMPLETED", "PARTIALLY_COMPLETED", "SKIPPED", "CANCELLED"})
_PAIN_STATUSES = frozenset({"YES", "NO", "UNKNOWN"})
_PENDING_INTAKE_CONFIRMATION = "PENDING_CONFIRMATION"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _parse_datetime(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    else:
        return fallback
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _is_today_utc(value: Any) -> bool:
    """Whether a point-in-time safety answer was given today.

    A persisted ``NO`` is useful for a later recap, but it cannot serve as a
    standing clearance for a new training day. Invalid/missing timestamps are
    therefore deliberately stale rather than treated as current.
    """

    parsed = _parse_datetime(value, datetime.min.replace(tzinfo=timezone.utc))
    return parsed.date() == _now().date()


def _state(value: Any, default: StateStatus = StateStatus.UNKNOWN) -> StateStatus:
    try:
        return StateStatus(str(value).upper())
    except ValueError:
        return default


def _tuple_strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item).strip() for item in _as_list(value) if str(item).strip())


@dataclass(frozen=True, slots=True)
class WorkoutRuntimeContext:
    """Private dispatcher context; never exposed through an LLM tool schema."""

    user_id: str | None
    session_id: str | None
    user_context: Mapping[str, Any] | None
    db_session: Any | None


@dataclass(frozen=True, slots=True)
class ProfileAdapterResult:
    profile: ExerciseProfile
    field_statuses: dict[str, str]
    missing_authoritative_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CachedWorkoutPlan:
    plan_id: str
    user_id: str
    plan: WorkoutPlan
    profile: ExerciseProfile
    state: TrainingState
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IntegrationOutcome:
    status: str
    plan_id: str | None
    plan: WorkoutPlan | None
    presentation: dict[str, Any] | None
    validation: dict[str, Any]
    profile_field_statuses: dict[str, str]
    training_state_coverage: dict[str, str]
    latency_ms: dict[str, float]
    error_code: str | None = None

    def to_tool_payload(self) -> dict[str, Any]:
        return {
            "integration_version": INTEGRATION_VERSION,
            "status": self.status,
            "plan_id": self.plan_id,
            "presentation": self.presentation,
            "validation": self.validation,
            "profile_source_statuses": self.profile_field_statuses,
            "training_state_coverage": self.training_state_coverage,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
        }


class ExerciseProfileAdapter:
    """Turn an authoritative Flutter profile snapshot into an E4 profile."""

    def adapt(
        self,
        context: Mapping[str, Any] | None,
        *,
        goal_override: str | None = None,
    ) -> ProfileAdapterResult:
        source = _as_mapping(context)
        raw_profile = source.get("workout_profile")
        raw = _as_mapping(raw_profile)
        profile_present = isinstance(raw_profile, Mapping)
        statuses: dict[str, str] = {}

        def field_status(name: str, value: Any) -> StateStatus:
            status = StateStatus.KNOWN if value is not None else (
                StateStatus.MISSING if profile_present else StateStatus.NOT_LOADED
            )
            statuses[name] = status.value
            return status

        requested_goal = goal_override or source.get("health_goal")
        normalized_goal = _GOAL_MAP.get(str(requested_goal).strip().casefold()) if requested_goal else None
        goal_status = field_status("goal", normalized_goal)

        experience_raw = raw.get("training_experience")
        try:
            experience = TrainingExperience(str(experience_raw).upper())
        except ValueError:
            experience = TrainingExperience.UNKNOWN
        experience_status = field_status("training_experience", experience_raw)

        confirmation_raw = raw.get("intake_confirmation_status")
        confirmation = str(confirmation_raw).upper()
        # Existing manually maintained profiles predate the chat-intake
        # metadata and remain valid. Only a revision explicitly captured by
        # this flow is withheld until the user has confirmed its recap.
        statuses["intake_confirmation_status"] = (
            _PENDING_INTAKE_CONFIRMATION
            if confirmation == _PENDING_INTAKE_CONFIRMATION
            else StateStatus.KNOWN.value
            if profile_present
            else StateStatus.NOT_LOADED.value
        )

        pain_raw = raw.get("current_pain_status")
        pain_map = {
            "NO": PainStatus.NONE_REPORTED,
            "NONE": PainStatus.NONE_REPORTED,
            "NONE_REPORTED": PainStatus.NONE_REPORTED,
            "YES": PainStatus.SIGNIFICANT_CURRENT_PAIN,
            "SIGNIFICANT_CURRENT_PAIN": PainStatus.SIGNIFICANT_CURRENT_PAIN,
        }
        pain_status = pain_map.get(str(pain_raw).upper(), PainStatus.UNKNOWN)
        field_status("current_pain_status", pain_raw)
        # Chat-captured profiles must carry a same-day safety response.  Older
        # manually maintained profiles have no intake metadata, so retain
        # their established compatibility behaviour instead of treating an
        # absent historical timestamp as a new data error.
        is_chat_intake = confirmation in {
            _PENDING_INTAKE_CONFIRMATION,
            "CONFIRMED",
        }
        if (
            pain_raw is not None
            and is_chat_intake
            and not _is_today_utc(raw.get("safety_checked_at"))
        ):
            pain_status = PainStatus.UNKNOWN
            statuses["current_pain_status"] = StateStatus.STALE.value

        safety_raw = _as_mapping(raw.get("exercise_safety_profile"))
        nutrition_safety = _as_mapping(source.get("nutrition_safety_profile"))
        pregnancy_raw = safety_raw.get("pregnancy_status")
        if pregnancy_raw is None:
            pregnancy_answer = nutrition_safety.get("pregnancy")
            if pregnancy_answer == "no":
                pregnancy_raw = "NOT_APPLICABLE"
            elif pregnancy_answer == "yes":
                pregnancy_raw = "PREGNANT"
        age = source.get("age")
        age_value = int(age) if isinstance(age, int) and 10 <= age <= 120 else None
        warning_value = safety_raw.get("warning_symptoms")
        safety = ExerciseSafetyProfile(
            age=age_value,
            age_status=StateStatus.KNOWN if age_value is not None else StateStatus.MISSING,
            health_state=str(safety_raw.get("health_state") or "UNKNOWN"),
            health_state_status=field_status("safety.health_state", safety_raw.get("health_state")),
            pregnancy_status=str(pregnancy_raw or "UNKNOWN"),
            pregnancy_state_status=field_status("safety.pregnancy_status", pregnancy_raw),
            warning_symptoms=_tuple_strings(warning_value),
            warning_symptoms_status=field_status("safety.warning_symptoms", warning_value),
            acute_injury=safety_raw.get("acute_injury") if isinstance(safety_raw.get("acute_injury"), bool) else None,
            recent_surgery=safety_raw.get("recent_surgery") if isinstance(safety_raw.get("recent_surgery"), bool) else None,
            technique_screen_confirmed=safety_raw.get("technique_screen_confirmed") if isinstance(safety_raw.get("technique_screen_confirmed"), bool) else None,
            source="firestore.users.workout_profile" if profile_present else "NOT_LOADED",
        )

        def nullable_int(name: str) -> int | None:
            raw_value = raw.get(name)
            field_status(name, raw_value)
            return raw_value if isinstance(raw_value, int) and raw_value > 0 else None

        def nullable_text(name: str) -> str | None:
            raw_value = raw.get(name)
            field_status(name, raw_value)
            return str(raw_value).strip() if isinstance(raw_value, str) and raw_value.strip() else None

        def nullable_strings(name: str) -> tuple[str, ...]:
            raw_value = raw.get(name)
            field_status(name, raw_value)
            return _tuple_strings(raw_value)

        profile = ExerciseProfile(
            goal=normalized_goal,
            goal_status=goal_status,
            training_experience=experience,
            experience_source=ExperienceSource.PROFILE if experience_status == StateStatus.KNOWN else ExperienceSource.UNKNOWN,
            local_history_available=bool(source.get("exercise_history_loaded")),
            available_days_per_week=nullable_int("available_days_per_week"),
            preferred_training_days=nullable_strings("preferred_training_days"),
            default_session_duration_minutes=nullable_int("default_session_duration_minutes"),
            training_location=nullable_text("training_location"),
            available_equipment=nullable_strings("available_equipment"),
            preferred_exercises=nullable_strings("preferred_exercises"),
            disliked_exercises=nullable_strings("disliked_exercises"),
            exercise_exclusions=nullable_strings("exercise_exclusions"),
            self_reported_limitations=nullable_strings("self_reported_limitations"),
            current_pain_status=pain_status,
            exercise_safety_profile=safety,
            profile_status=StateStatus.KNOWN if profile_present else StateStatus.NOT_LOADED,
        )
        missing = tuple(sorted(key for key, value in statuses.items() if value != StateStatus.KNOWN.value))
        return ProfileAdapterResult(profile, statuses, missing)


class TrainingStateAdapter:
    """Merge limited legacy rows with modern persisted E4 workout results."""

    def __init__(self) -> None:
        self._catalog = load_canonical_exercise_catalog()
        self._by_id = {item["exercise_id"]: item for item in self._catalog}

    @staticmethod
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
            source="E4_1_TRAINING_STATE_ADAPTER",
            observation_window=window,
            computed_at=computed_at,
            status=status,
            provenance=f"{INTEGRATION_VERSION}:{provenance}",
            coverage=coverage,
        )

    def adapt(
        self,
        legacy_records: Iterable[dict[str, Any]] | None,
        *,
        legacy_status: StateStatus,
        modern_results: Iterable[Mapping[str, Any]],
        modern_available: bool,
        active_plan_status: str | None,
        computed_at: datetime | None = None,
    ) -> TrainingState:
        now = computed_at or _now()
        legacy_rows = [dict(item) for item in legacy_records or []]
        if legacy_records is None and not modern_available:
            return normalize_training_history(None, computed_at=now, source_status=legacy_status)

        legacy = normalize_training_history(
            legacy_rows if legacy_records is not None else None,
            computed_at=now,
            source_status=legacy_status,
        )
        modern = [_as_mapping(item) for item in modern_results]
        if not modern:
            if active_plan_status is None:
                return legacy
            active = self._observation(
                active_plan_status, computed_at=now, window="CURRENT", status=StateStatus.KNOWN,
                coverage=HistoryCoverage.AUTHORITATIVE_AVAILABLE,
                provenance="POSTGRES_WORKOUT_PLAN_STATUS",
            )
            return replace(legacy, active_workout_plan_status=active)

        known_legacy = legacy_records is not None and legacy_status == StateStatus.KNOWN
        coverage = HistoryCoverage.DERIVABLE if known_legacy else HistoryCoverage.PARTIAL
        merged_status = StateStatus.KNOWN if modern_available else StateStatus.CONFLICT
        reason_codes = list(legacy.history_reason_codes)
        reason_codes.append("MODERN_WORKOUT_RESULTS_AVAILABLE")
        if not known_legacy:
            reason_codes.append("LEGACY_HISTORY_PARTIAL_OR_UNAVAILABLE")

        def in_window(row: Mapping[str, Any], days: int) -> bool:
            return _parse_datetime(row.get("performed_at"), now) >= now.replace(hour=0, minute=0, second=0, microsecond=0) - __import__("datetime").timedelta(days=days)

        modern7 = [item for item in modern if in_window(item, 7)]
        modern28 = [item for item in modern if in_window(item, 28)]
        legacy7 = int(legacy.sessions_last_7d.value or 0) if known_legacy else 0
        legacy28 = int(legacy.sessions_last_28d.value or 0) if known_legacy else 0
        legacy_resistance7 = int(legacy.resistance_sessions_last_7d.value or 0) if known_legacy else 0
        legacy_aerobic7 = int(legacy.aerobic_minutes_last_7d.value or 0) if known_legacy else 0

        def is_aerobic(item: Mapping[str, Any]) -> bool:
            return str(item.get("goal") or "").upper() == "AEROBIC_ENDURANCE"

        performance: list[ExercisePerformance] = []
        muscle7: Counter[str] = Counter()
        muscle28: Counter[str] = Counter()
        movement7: Counter[str] = Counter()
        movement28: Counter[str] = Counter()
        substitutions: list[str] = []
        pain_events = 0
        for result in modern:
            performed_at = _parse_datetime(result.get("performed_at"), now)
            within7 = result in modern7
            within28 = result in modern28
            pain = str(result.get("pain_discomfort_status") or "UNKNOWN").upper()
            if within28 and pain == "YES":
                pain_events += 1
            for raw_exercise in _as_list(result.get("exercise_results")):
                exercise = _as_mapping(raw_exercise)
                canonical_id = exercise.get("canonical_exercise_id")
                catalog = self._by_id.get(str(canonical_id))
                if catalog is None:
                    continue
                if within7:
                    muscle7.update(
                        item.get("name_en") or item.get("name") or str(item.get("id"))
                        for item in catalog.get("primary_muscles") or []
                    )
                    movement = _as_mapping(catalog.get("movement_pattern")).get("value")
                    if movement and movement != "UNKNOWN":
                        movement7[str(movement)] += 1
                if within28:
                    muscle28.update(
                        item.get("name_en") or item.get("name") or str(item.get("id"))
                        for item in catalog.get("primary_muscles") or []
                    )
                    movement = _as_mapping(catalog.get("movement_pattern")).get("value")
                    if movement and movement != "UNKNOWN":
                        movement28[str(movement)] += 1
                raw_sets = [_as_mapping(item) for item in _as_list(exercise.get("sets"))]
                completed_sets = sum(item.get("completed") is True for item in raw_sets) if raw_sets else None
                reps = tuple(int(item["actual_reps"]) for item in raw_sets if isinstance(item.get("actual_reps"), int))
                last_load = next((float(item["load_kg"]) for item in reversed(raw_sets) if isinstance(item.get("load_kg"), (int, float))), None)
                last_rpe = next((float(item["rpe"]) for item in reversed(raw_sets) if isinstance(item.get("rpe"), (int, float))), None)
                last_rir = next((float(item["rir"]) for item in reversed(raw_sets) if isinstance(item.get("rir"), (int, float))), None)
                performance.append(ExercisePerformance(
                    canonical_exercise_id=str(canonical_id),
                    source_exercise_id=catalog.get("source_exercise_id"),
                    observed_at=performed_at,
                    completed_sets=completed_sets,
                    prescribed_sets=exercise.get("prescribed_sets") if isinstance(exercise.get("prescribed_sets"), int) else None,
                    reps=reps,
                    load_kg=last_load,
                    rpe=last_rpe,
                    rir=last_rir,
                    completed=exercise.get("exercise_completion_status") == "COMPLETED",
                    pain_reported=True if pain == "YES" else False if pain == "NO" else None,
                    technique_stable=exercise.get("technique_stable") if isinstance(exercise.get("technique_stable"), bool) else None,
                    consecutive_successes=int(exercise.get("consecutive_successes") or 0),
                    consecutive_misses=int(exercise.get("consecutive_misses") or 0),
                    source="POSTGRES_WORKOUT_RESULTS_E4",
                ))
                if isinstance(exercise.get("substituted_from"), str):
                    substitutions.append(exercise["substituted_from"])

        performance.sort(key=lambda item: item.observed_at)
        latest = performance[-1] if performance else None
        legacy_performance = tuple(legacy.exercise_performance_history.value or ()) if legacy.exercise_performance_history.status == StateStatus.KNOWN else ()
        all_performance = tuple(sorted((*legacy_performance, *performance), key=lambda item: item.observed_at))
        session_statuses = [str(item.get("session_completion_status") or "").upper() for item in modern28]
        completed_count = sum(value == "COMPLETED" for value in session_statuses)
        denominator = len(session_statuses) + (legacy28 if known_legacy else 0)
        legacy_completed_estimate = round(float(legacy.completion_rate.value or 0) * legacy28) if known_legacy and legacy.completion_rate.status == StateStatus.KNOWN else 0
        last_session_candidates = [
            _parse_datetime(item.get("performed_at"), now) for item in modern
        ]
        if legacy.last_session_at.value is not None:
            last_session_candidates.append(legacy.last_session_at.value)

        def observation(value: Any, window: str, provenance: str, field_coverage: HistoryCoverage = coverage) -> StateObservation:
            return self._observation(value, computed_at=now, window=window, status=merged_status, coverage=field_coverage, provenance=provenance)

        active_observation = (
            self._observation(active_plan_status, computed_at=now, window="CURRENT", status=StateStatus.KNOWN,
                              coverage=HistoryCoverage.AUTHORITATIVE_AVAILABLE, provenance="POSTGRES_WORKOUT_PLAN_STATUS")
            if active_plan_status is not None
            else legacy.active_workout_plan_status
        )
        return TrainingState(
            status=merged_status,
            history_reason_codes=tuple(dict.fromkeys(reason_codes)),
            sessions_last_7d=observation(legacy7 + len(modern7), "7D", "LEGACY_PLUS_MODERN_SESSION_COUNT"),
            sessions_last_28d=observation(legacy28 + len(modern28), "28D", "LEGACY_PLUS_MODERN_SESSION_COUNT"),
            resistance_sessions_last_7d=observation(legacy_resistance7 + sum(not is_aerobic(item) for item in modern7), "7D", "LEGACY_PLUS_MODERN_RESISTANCE_COUNT"),
            aerobic_minutes_last_7d=observation(legacy_aerobic7 + sum(float(item.get("duration_minutes") or 0) for item in modern7 if is_aerobic(item)), "7D", "LEGACY_PLUS_MODERN_AEROBIC_MINUTES"),
            last_session_at=observation(max(last_session_candidates) if last_session_candidates else None, "ALL_AVAILABLE", "MERGED_LAST_SESSION"),
            last_exercise_performed_at=observation(tuple((item.canonical_exercise_id, item.observed_at) for item in all_performance), "ALL_AVAILABLE", "MODERN_PERFORMANCE_PLUS_LEGACY", HistoryCoverage.PARTIAL),
            muscle_exposure_7d=observation(tuple(sorted(muscle7.items())), "7D", "MODERN_CATALOG_JOIN", HistoryCoverage.PARTIAL),
            muscle_exposure_28d=observation(tuple(sorted(muscle28.items())), "28D", "MODERN_CATALOG_JOIN", HistoryCoverage.PARTIAL),
            movement_exposure_7d=observation(tuple(sorted(movement7.items())), "7D", "MODERN_CATALOG_JOIN", HistoryCoverage.PARTIAL),
            movement_exposure_28d=observation(tuple(sorted(movement28.items())), "28D", "MODERN_CATALOG_JOIN", HistoryCoverage.PARTIAL),
            exercise_performance_history=observation(all_performance, "ALL_AVAILABLE", "OBSERVED_MODERN_PERFORMANCE", HistoryCoverage.PARTIAL if legacy_performance else HistoryCoverage.AUTHORITATIVE_AVAILABLE),
            recent_sets=observation(latest.completed_sets if latest else None, "MOST_RECENT_PERFORMANCE", "OBSERVED_ONLY", HistoryCoverage.PARTIAL),
            recent_reps=observation(latest.reps if latest and latest.reps else None, "MOST_RECENT_PERFORMANCE", "OBSERVED_ONLY", HistoryCoverage.PARTIAL),
            recent_load_kg=observation(latest.load_kg if latest else None, "MOST_RECENT_PERFORMANCE", "OBSERVED_ONLY", HistoryCoverage.PARTIAL),
            recent_rpe=observation(latest.rpe if latest else None, "MOST_RECENT_PERFORMANCE", "OBSERVED_ONLY", HistoryCoverage.PARTIAL),
            recent_rir=observation(latest.rir if latest else None, "MOST_RECENT_PERFORMANCE", "OBSERVED_ONLY", HistoryCoverage.PARTIAL),
            completion_rate=observation(round((completed_count + legacy_completed_estimate) / denominator, 4) if denominator else None, "28D", "OBSERVED_SESSION_COMPLETION", coverage),
            missed_sessions=legacy.missed_sessions,
            reported_pain_events=observation(pain_events, "28D", "SELF_REPORTED_MODERN_PAIN", HistoryCoverage.PARTIAL),
            recent_substitutions=observation(tuple(substitutions), "28D", "MODERN_SUBSTITUTION_HISTORY", HistoryCoverage.PARTIAL),
            active_workout_plan_status=active_observation,
        )


class WorkoutRepository:
    """PostgreSQL repository; all write statements are individually atomic."""

    def __init__(self, db_session: Any | None) -> None:
        self._db = db_session

    def _require_db(self) -> Any:
        if self._db is None:
            raise RuntimeError("WORKOUT_PERSISTENCE_UNAVAILABLE")
        return self._db

    @staticmethod
    def _mapping(row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        mapping = getattr(row, "_mapping", None)
        return dict(mapping) if mapping is not None else dict(row)

    async def load_modern_results(self, user_id: str) -> list[dict[str, Any]]:
        db = self._require_db()
        result = await db.execute(text("""
            SELECT r.performed_at, r.session_completion_status, r.exercise_results,
                   r.pain_discomfort_status, r.duration_minutes, p.goal
            FROM workout_results_e4 r
            JOIN workout_plans_e4 p ON p.id = r.workout_plan_id
            WHERE p.user_id = :user_id
            ORDER BY r.performed_at ASC, r.id ASC
        """), {"user_id": user_id})
        return [self._mapping(row) for row in result.fetchall()]

    async def load_active_plan_status(self, user_id: str) -> str | None:
        db = self._require_db()
        result = await db.execute(text("""
            SELECT status FROM workout_plans_e4
            WHERE user_id = :user_id AND status IN ('SAVED', 'ACTIVE')
            ORDER BY saved_at DESC LIMIT 1
        """), {"user_id": user_id})
        row = result.first()
        return str(row[0]) if row is not None else None

    async def put_preview(self, user_id: str, plan_id: str, presentation: Mapping[str, Any]) -> None:
        db = self._require_db()
        await db.execute(
            text(
                """
                INSERT INTO workout_plan_previews_e4 (owner_user_id, plan_id, presentation)
                VALUES (:owner, CAST(:plan_id AS uuid), CAST(:presentation AS jsonb))
                ON CONFLICT (owner_user_id, plan_id)
                DO UPDATE SET presentation = EXCLUDED.presentation,
                              created_at = NOW(),
                              expires_at = NOW() + INTERVAL '30 days'
                """
            ),
            {"owner": user_id, "plan_id": plan_id, "presentation": _json(presentation)},
        )

    async def load_preview(self, user_id: str, plan_id: str) -> dict[str, Any] | None:
        db = self._require_db()
        result = await db.execute(
            text(
                """
                SELECT presentation
                FROM workout_plan_previews_e4
                WHERE owner_user_id = :owner
                  AND plan_id = CAST(:plan_id AS uuid)
                  AND expires_at > NOW()
                """
            ),
            {"owner": user_id, "plan_id": plan_id},
        )
        row = result.first()
        if row is None:
            return None
        value = self._mapping(row).get("presentation")
        return dict(value) if isinstance(value, Mapping) else None

    async def save_plan(self, cached: CachedWorkoutPlan, request_id: str, *, activate: bool) -> dict[str, Any]:
        plan = cached.plan
        presentation = WorkoutPlanPresenter.present(plan, plan_id=cached.plan_id)
        return await self.save_presentation(
            cached.user_id,
            cached.plan_id,
            presentation,
            request_id,
            activate=activate,
        )

    async def save_presentation(
        self,
        user_id: str,
        plan_id: str,
        presentation: Mapping[str, Any],
        request_id: str,
        *,
        activate: bool,
    ) -> dict[str, Any]:
        db = self._require_db()
        if (
            presentation.get("type") != "personalized_workout"
            or presentation.get("status") != "READY"
            or str(presentation.get("plan_id")) != plan_id
        ):
            raise RuntimeError("WORKOUT_PREVIEW_INVALID")
        status = "ACTIVE" if activate else "SAVED"
        payload = {
            "plan_id": plan_id, "user_id": user_id, "request_id": request_id,
            "status": status,
            "planner_version": presentation["planner_version"],
            "catalog_version": presentation["catalog_version"],
            "policy_version": presentation["exercise_policy_version"],
            "generated_at": datetime.fromisoformat(str(presentation["generated_at"]).replace("Z", "+00:00")),
            "goal": presentation.get("goal"),
            "duration_budget": presentation.get("duration_budget_minutes"),
            "estimated_duration": presentation["estimated_duration_minutes"],
            "exercises": _json(presentation["exercises"]),
            "reason_metadata": _json({
                "selection": presentation.get("selection_reason_codes") or [],
                "history": presentation.get("history_reason_codes") or [],
                "policy": presentation.get("policy_reason_codes") or [],
                "filtering": presentation.get("catalog_filtering") or [],
            }),
            "energy": _json(presentation["energy_estimate"]),
        }
        result = await db.execute(text("""
            WITH inserted AS (
                INSERT INTO workout_plans_e4 (
                    id, user_id, idempotency_key, status, planner_version, catalog_version,
                    exercise_policy_version, generated_at, activated_at, goal,
                    duration_budget_minutes, estimated_duration_minutes, exercises,
                    reason_metadata, estimated_energy_expenditure
                ) VALUES (
                    CAST(:plan_id AS UUID), :user_id, :request_id, :status, :planner_version,
                    :catalog_version, :policy_version, :generated_at,
                    CASE WHEN :status = 'ACTIVE' THEN NOW() ELSE NULL END, :goal,
                    :duration_budget, :estimated_duration, CAST(:exercises AS jsonb),
                    CAST(:reason_metadata AS jsonb), CAST(:energy AS jsonb)
                ) ON CONFLICT (user_id, idempotency_key) DO NOTHING
                RETURNING id::text AS id, status, planner_version, catalog_version,
                          exercise_policy_version, exercises, reason_metadata,
                          estimated_energy_expenditure
            )
            SELECT * FROM inserted
            UNION ALL
            SELECT id::text AS id, status, planner_version, catalog_version,
                   exercise_policy_version, exercises, reason_metadata,
                   estimated_energy_expenditure
            FROM workout_plans_e4
            WHERE user_id = :user_id AND idempotency_key = :request_id
              AND NOT EXISTS (SELECT 1 FROM inserted)
        """), payload)
        row = self._mapping(result.first())
        if not row:
            raise RuntimeError("WORKOUT_PLAN_READBACK_FAILED")
        if str(row["id"]) != plan_id or str(row["planner_version"]) != str(presentation["planner_version"]):
            raise RuntimeError("WORKOUT_PLAN_READBACK_MISMATCH")
        return row

    async def log_result(self, user_id: str, plan_id: str, request_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        db = self._require_db()
        status = str(payload.get("session_completion_status") or "").upper()
        if status not in _COMPLETION_STATUSES:
            raise ValueError("INVALID_WORKOUT_RESULT_STATUS")
        pain = str(payload.get("pain_discomfort_status") or "UNKNOWN").upper()
        if pain not in _PAIN_STATUSES:
            raise ValueError("INVALID_PAIN_STATUS")
        record = {
            "user_id": user_id, "plan_id": plan_id, "request_id": request_id,
            "result_id": str(uuid4()), "performed_at": payload.get("performed_at") or _now(),
            "status": status, "exercise_results": _json(_as_list(payload.get("exercise_results"))),
            "session_rpe": payload.get("session_rpe"), "pain": pain, "note": payload.get("note"),
            "duration": payload.get("duration_minutes"), "device_energy": payload.get("reported_device_energy_kcal"),
            "user_energy": payload.get("user_reported_energy_kcal"),
        }
        result = await db.execute(text("""
            WITH target_plan AS (
                SELECT id FROM workout_plans_e4
                WHERE id = CAST(:plan_id AS UUID) AND user_id = :user_id
            ), inserted AS (
                INSERT INTO workout_results_e4 (
                    id, workout_plan_id, idempotency_key, performed_at,
                    session_completion_status, exercise_results, session_rpe,
                    pain_discomfort_status, note, duration_minutes,
                    reported_device_energy_kcal, user_reported_energy_kcal
                ) SELECT CAST(:result_id AS UUID), id, :request_id, :performed_at,
                    :status, CAST(:exercise_results AS jsonb), :session_rpe,
                    :pain, :note, :duration, :device_energy, :user_energy
                FROM target_plan
                ON CONFLICT (workout_plan_id, idempotency_key) DO NOTHING
                RETURNING id::text AS id, workout_plan_id, performed_at,
                          session_completion_status, exercise_results, session_rpe,
                          pain_discomfort_status, note, duration_minutes,
                          reported_device_energy_kcal, user_reported_energy_kcal
            ), chosen AS (
                SELECT * FROM inserted
                UNION ALL
                SELECT r.id::text AS id, r.workout_plan_id, r.performed_at,
                       r.session_completion_status, r.exercise_results, r.session_rpe,
                       r.pain_discomfort_status, r.note, r.duration_minutes,
                       r.reported_device_energy_kcal, r.user_reported_energy_kcal
                FROM workout_results_e4 r
                JOIN target_plan target ON target.id = r.workout_plan_id
                WHERE r.idempotency_key = :request_id
                  AND NOT EXISTS (SELECT 1 FROM inserted)
            ), updated_plan AS (
                UPDATE workout_plans_e4 p
                SET status = :status,
                    completed_at = CASE WHEN :status IN ('COMPLETED', 'PARTIALLY_COMPLETED', 'SKIPPED') THEN NOW() ELSE completed_at END
                WHERE p.id = CAST(:plan_id AS UUID) AND p.user_id = :user_id
                  AND EXISTS (SELECT 1 FROM chosen)
                RETURNING p.status AS plan_status
            )
            SELECT chosen.id, chosen.performed_at, chosen.session_completion_status,
                   chosen.exercise_results, chosen.session_rpe,
                   chosen.pain_discomfort_status, chosen.note, chosen.duration_minutes,
                   chosen.reported_device_energy_kcal, chosen.user_reported_energy_kcal,
                   updated_plan.plan_status
            FROM chosen CROSS JOIN updated_plan
        """), record)
        row = self._mapping(result.first())
        if not row:
            raise RuntimeError("WORKOUT_RESULT_READBACK_FAILED")
        if _json(row.get("exercise_results")) != _json(_as_list(payload.get("exercise_results"))):
            raise RuntimeError("WORKOUT_RESULT_READBACK_MISMATCH")
        return row


class WorkoutPlanCache:
    """Process-local, expiring generated-plan references; it is not persistence."""

    def __init__(self) -> None:
        self._plans: dict[str, CachedWorkoutPlan] = {}
        self._lock = Lock()

    def put(self, item: CachedWorkoutPlan) -> None:
        with self._lock:
            self._plans[item.plan_id] = item

    def get(self, plan_id: str, user_id: str) -> CachedWorkoutPlan | None:
        with self._lock:
            item = self._plans.get(plan_id)
            if item is None or item.user_id != user_id:
                return None
            return item


GLOBAL_WORKOUT_PLAN_CACHE = WorkoutPlanCache()


class WorkoutIntegrationService:
    """The only E4.1 authoritative planning/write path."""

    def __init__(self, db_session: Any | None = None, *, cache: WorkoutPlanCache | None = None) -> None:
        self._repository = WorkoutRepository(db_session)
        self._profiles = ExerciseProfileAdapter()
        self._states = TrainingStateAdapter()
        self._cache = cache or GLOBAL_WORKOUT_PLAN_CACHE

    @staticmethod
    def _legacy_history(context: Mapping[str, Any]) -> tuple[list[dict[str, Any]] | None, StateStatus]:
        raw = context.get("exercise_history")
        status = _state(context.get("exercise_history_status"), StateStatus.NOT_LOADED)
        if status != StateStatus.KNOWN:
            return None, status
        if isinstance(raw, list):
            return [dict(item) for item in raw if isinstance(item, Mapping)], StateStatus.KNOWN
        return None, StateStatus.MISSING

    async def build(
        self,
        runtime: WorkoutRuntimeContext,
        *,
        goal_override: str | None = None,
        requested_duration_minutes: int | None = None,
        requested_location: str | None = None,
        available_equipment_override: Iterable[str] | None = None,
        requested_body_area: str | None = None,
        exercise_include: Iterable[str] = (),
        exercise_exclude: Iterable[str] = (),
        temporary_preferences: Iterable[str] = (),
        session_type: str = "RESISTANCE",
        goal_context: str | None = None,
    ) -> IntegrationOutcome:
        started = time.perf_counter()
        context = _as_mapping(runtime.user_context)
        user_id = runtime.user_id or context.get("user_id")
        if not isinstance(user_id, str) or not user_id or user_id == "anonymous":
            return IntegrationOutcome("CLARIFICATION_REQUIRED", None, None, None, {}, {}, {}, {"total": round((time.perf_counter() - started) * 1000, 3)}, "AUTHORITATIVE_USER_CONTEXT_REQUIRED")
        profile_started = time.perf_counter()
        normalized_goal = normalize_workout_goal(goal_override, context=context)
        adapted = self._profiles.adapt(context, goal_override=normalized_goal)
        profile = adapted.profile
        profile_ms = (time.perf_counter() - profile_started) * 1000
        if adapted.field_statuses.get("intake_confirmation_status") == _PENDING_INTAKE_CONFIRMATION:
            return IntegrationOutcome(
                "PROFILE_CONFIRMATION_REQUIRED",
                None,
                None,
                None,
                {},
                adapted.field_statuses,
                {},
                {
                    "profile": round(profile_ms, 3),
                    "total": round((time.perf_counter() - started) * 1000, 3),
                },
                "WORKOUT_PROFILE_RECAP_REQUIRED",
            )

        state_started = time.perf_counter()
        legacy_rows, legacy_status = self._legacy_history(context)
        modern_available = False
        modern_rows: list[dict[str, Any]] = []
        active_status: str | None = None
        try:
            modern_rows = await self._repository.load_modern_results(user_id)
            active_status = await self._repository.load_active_plan_status(user_id)
            modern_available = True
        except Exception:
            # A current authoritative legacy snapshot may still be enough for
            # a read-only recommendation; its provenance stays explicit.
            modern_available = False
        state = self._states.adapt(
            legacy_rows, legacy_status=legacy_status, modern_results=modern_rows,
            modern_available=modern_available, active_plan_status=active_status,
        )
        # A positive pain/discomfort result is an explicit observation, not a
        # diagnosis.  Until the person clarifies it, route conservatively
        # through the frozen E3 safety gate rather than substituting/continuing
        # an ordinary session automatically.
        if (
            state.reported_pain_events.status == StateStatus.KNOWN
            and isinstance(state.reported_pain_events.value, (int, float))
            and state.reported_pain_events.value > 0
        ):
            profile = replace(
                profile, current_pain_status=PainStatus.SIGNIFICANT_CURRENT_PAIN
            )
            adapted.field_statuses["current_pain_status"] = "KNOWN_REPORTED_DURING_WORKOUT"
        state_ms = (time.perf_counter() - state_started) * 1000

        request = WorkoutRequest(
            goal_override=normalized_goal,
            requested_duration_minutes=requested_duration_minutes,
            requested_location=requested_location,
            available_equipment_override=tuple(available_equipment_override) if available_equipment_override is not None else None,
            requested_body_area=requested_body_area,
            exercise_include=tuple(exercise_include),
            exercise_exclude=tuple(exercise_exclude),
            temporary_preferences=tuple(temporary_preferences),
            session_type=session_type,
            goal_context=goal_context,
            write_intent=False,
        )
        weight = context.get("weight") or context.get("weight_kg")
        energy_weight = float(weight) if isinstance(weight, (int, float)) and 30 <= float(weight) <= 300 else None
        planner_started = time.perf_counter()
        try:
            planner = PersonalizedWorkoutPlanner()
            plan = planner.plan(profile, state, request, energy_weight_kg=energy_weight)
        except ExercisePrescriptionPolicyError as exc:
            return IntegrationOutcome("CLARIFICATION_REQUIRED", None, None, None, {}, adapted.field_statuses, self._coverage(state), {"profile": round(profile_ms, 3), "training_state": round(state_ms, 3), "total": round((time.perf_counter() - started) * 1000, 3)}, str(exc))
        except Exception:
            return IntegrationOutcome("PLANNER_UNAVAILABLE", None, None, None, {}, adapted.field_statuses, self._coverage(state), {"profile": round(profile_ms, 3), "training_state": round(state_ms, 3), "total": round((time.perf_counter() - started) * 1000, 3)}, "PLANNER_EXCEPTION")
        planner_ms = (time.perf_counter() - planner_started) * 1000
        validator_started = time.perf_counter()
        validator = WorkoutPlanValidator(planner._catalog).validate(plan, profile, state, request)  # noqa: SLF001 - same authoritative frozen catalog
        validator_ms = (time.perf_counter() - validator_started) * 1000
        validation_payload = validator.to_dict()
        latency = {
            "profile": round(profile_ms, 3), "training_state": round(state_ms, 3),
            "planner": round(planner_ms, 3), "validator": round(validator_ms, 3),
            "total": round((time.perf_counter() - started) * 1000, 3),
        }
        if plan.safety_status == ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE:
            return IntegrationOutcome("REQUIRES_PROFESSIONAL_GUIDANCE", None, plan, None, validation_payload, adapted.field_statuses, self._coverage(state), latency)
        if plan.safety_status != ApplicabilityStatus.SUPPORTED or plan.time_budget_status.value == "CLARIFICATION_REQUIRED":
            return IntegrationOutcome("CLARIFICATION_REQUIRED", None, plan, None, validation_payload, adapted.field_statuses, self._coverage(state), latency)
        if validator.hard_violation_count:
            return IntegrationOutcome("VALIDATION_FAILED", None, plan, None, validation_payload, adapted.field_statuses, self._coverage(state), latency)
        if plan.readiness != "READY" or not plan.exercises:
            return IntegrationOutcome("INSUFFICIENT_ELIGIBLE_EXERCISES", None, plan, None, validation_payload, adapted.field_statuses, self._coverage(state), latency)
        plan_id = str(uuid4())
        presentation = WorkoutPlanPresenter.present(plan, plan_id=plan_id)
        response_validation = WorkoutResponseValidator.validate(plan, presentation)
        if not response_validation.valid:
            return IntegrationOutcome("VALIDATION_FAILED", None, plan, None, {**validation_payload, "response": response_validation.to_dict()}, adapted.field_statuses, self._coverage(state), latency, "STRUCTURED_RESPONSE_MISMATCH")
        self._cache.put(CachedWorkoutPlan(plan_id, user_id, plan, profile, state, _now()))
        try:
            await self._repository.put_preview(user_id, plan_id, presentation)
        except Exception:
            # Recommendation rendering stays available if preview persistence
            # is temporarily unavailable; explicit save reports a real error.
            pass
        return IntegrationOutcome("READY", plan_id, plan, presentation, {**validation_payload, "response": response_validation.to_dict()}, adapted.field_statuses, self._coverage(state), latency)

    @staticmethod
    def _coverage(state: TrainingState) -> dict[str, str]:
        return {
            "sessions_last_7d": state.sessions_last_7d.coverage.value,
            "muscle_exposure_7d": state.muscle_exposure_7d.coverage.value,
            "performance": state.exercise_performance_history.coverage.value,
            "recent_load_kg": state.recent_load_kg.coverage.value,
            "pain": state.reported_pain_events.coverage.value,
        }

    async def save_plan(self, runtime: WorkoutRuntimeContext, plan_id: str, request_id: str, *, activate: bool = False) -> dict[str, Any]:
        if not settings.workout_write_explicit_enabled:
            return {"status": "WORKOUT_WRITE_DISABLED", "write_status": "REJECTED"}
        user_id = runtime.user_id
        cached = self._cache.get(plan_id, user_id or "") if user_id else None
        started = time.perf_counter()
        try:
            if cached is not None:
                row = await self._repository.save_plan(cached, request_id, activate=activate)
            elif user_id:
                preview = await self._repository.load_preview(user_id, plan_id)
                if preview is None:
                    return {"status": "PLAN_NOT_FOUND", "write_status": "REJECTED"}
                row = await self._repository.save_presentation(
                    user_id, plan_id, preview, request_id, activate=activate
                )
            else:
                return {"status": "PLAN_NOT_FOUND", "write_status": "REJECTED"}
        except Exception as exc:
            return {"status": "PERSISTENCE_ERROR", "write_status": "ERROR", "error_code": str(exc)}
        return {
            "status": str(row["status"]), "write_status": "PERSISTED", "workout_plan_id": str(row["id"]),
            "read_back_verified": True, "persistence_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }

    async def get_substitutions(
        self,
        runtime: WorkoutRuntimeContext,
        *,
        plan_id: str,
        canonical_exercise_id: str,
        equipment_override: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """Return only E4-validated substitutions for a generated plan.

        A temporary equipment override reruns the frozen E4 eligibility and
        substitution rules.  It never turns a temporary rejection into a
        permanent profile preference and never persists a replacement.
        """
        user_id = runtime.user_id
        cached = self._cache.get(plan_id, user_id or "") if user_id else None
        if cached is None:
            return {"status": "PLAN_NOT_FOUND", "candidate_exercises": []}
        source = next(
            (item for item in cached.plan.exercises if item.canonical_exercise_id == canonical_exercise_id),
            None,
        )
        if source is None:
            return {"status": "EXERCISE_NOT_IN_PLAN", "candidate_exercises": []}
        planner = PersonalizedWorkoutPlanner()
        by_id = {item["exercise_id"]: item for item in planner._catalog}  # noqa: SLF001 - frozen E4 catalog identity
        source_record = by_id.get(canonical_exercise_id)
        if source_record is None:
            return {"status": "SUBSTITUTION_UNAVAILABLE", "candidate_exercises": []}
        request = WorkoutRequest(
            goal_override=cached.plan.goal,
            requested_duration_minutes=cached.plan.duration_budget,
            available_equipment_override=(
                tuple(equipment_override) if equipment_override is not None else None
            ),
            exercise_exclude=(canonical_exercise_id,),
        )
        safety = evaluate_safety(cached.profile)
        requirement = build_session_requirement(cached.profile, cached.state, request, safety)
        if safety.status != ApplicabilityStatus.SUPPORTED or requirement.status != ApplicabilityStatus.SUPPORTED:
            return {
                "status": "CLARIFICATION_REQUIRED" if requirement.status != ApplicabilityStatus.REQUIRES_PROFESSIONAL_GUIDANCE else "REQUIRES_PROFESSIONAL_GUIDANCE",
                "candidate_exercises": [],
                "reason_codes": list((*safety.reason_codes, *requirement.selection_reason_codes)),
            }
        eligible, filtering = planner._hard_filter(cached.profile, request, requirement, safety)  # noqa: SLF001 - the E4 hard filter is authoritative
        decision = planner._substitutions(  # noqa: SLF001 - E4 substitution policy implementation
            source_record,
            eligible,
            requirement.required_equipment_constraints,
            cached.profile.training_experience,
        )
        candidates = [
            {
                "canonical_exercise_id": identifier,
                "source_exercise_id": by_id[identifier]["source_exercise_id"],
                "display_name": by_id[identifier].get("name_vi") or by_id[identifier].get("name_en"),
            }
            for identifier in decision.candidate_exercise_ids
            if identifier in by_id
        ]
        return {
            "status": decision.status,
            "plan_id": plan_id,
            "canonical_exercise_id": canonical_exercise_id,
            "candidate_exercises": candidates,
            "reason_codes": list(decision.reason_codes),
            "policy_rule_ids": list(decision.policy_rule_ids),
            "catalog_filtering": [item.to_dict() for item in filtering],
            "persisted": False,
        }

    async def log_result(self, runtime: WorkoutRuntimeContext, plan_id: str, request_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not settings.workout_write_explicit_enabled:
            return {"status": "WORKOUT_WRITE_DISABLED", "write_status": "REJECTED"}
        user_id = runtime.user_id
        if not user_id:
            return {"status": "AUTHORITATIVE_USER_CONTEXT_REQUIRED", "write_status": "REJECTED"}
        started = time.perf_counter()
        try:
            row = await self._repository.log_result(user_id, plan_id, request_id, payload)
        except ValueError as exc:
            return {"status": str(exc), "write_status": "REJECTED"}
        except Exception as exc:
            return {"status": "PERSISTENCE_ERROR", "write_status": "ERROR", "error_code": str(exc)}
        return {
            "status": str(row["plan_status"]), "write_status": "PERSISTED", "workout_result_id": str(row["id"]),
            "read_back_verified": True, "persistence_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        }


__all__ = [
    "INTEGRATION_VERSION", "CachedWorkoutPlan", "ExerciseProfileAdapter", "GLOBAL_WORKOUT_PLAN_CACHE",
    "IntegrationOutcome", "ProfileAdapterResult", "TrainingStateAdapter", "WorkoutIntegrationService",
    "WorkoutPlanCache", "WorkoutRepository", "WorkoutRuntimeContext",
]
