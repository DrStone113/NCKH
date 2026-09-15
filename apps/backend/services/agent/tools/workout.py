"""``suggest_workout`` server-side tool.

Selects 2-8 wger exercises matching a muscle group, available equipment,
target difficulty ``level``, and training ``goal``. The selected list satisfies
``sum(ex.duration_minutes) ≤ duration_min``. When ``user_state.fatigue_level``
is ``"high"`` or ``"very_high"``, the requested ``level`` is automatically
downgraded one notch (``advanced → intermediate → beginner``) so a tired user
gets easier exercises. When ``equipment == "none"`` the tool returns only
confirmed bodyweight exercises. Calorie estimates use the caller's body weight
when available and remain explicitly marked as estimates.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §6.2 (ExercisePlanPayload shape), §9.5 (formal contract).
- Requirements 4.2, 4.5, 4.6, 7.8 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract
--------
``suggest_workout(muscle_group, duration_min, equipment, level, user_state=None, goal="general_fitness") -> dict``

Returns a JSON-serialisable workout payload matching
:class:`models.schemas.ExercisePlanPayload`::

    {
        "workout_title": str,
        "exercises": [
            {
                "name": str,
                "category": str,
                "duration_minutes": int,        # > 0
                "sets": int,                    # >= 0
                "reps": str,
                "calories_burned": float,       # >= 0
            }, ...                              # 2 <= len <= 8
        ],
        "total_duration_minutes": int,          # <= duration_min
        "total_calories_burned": float,
    }

Raises ``ValueError`` with one of:

- ``"INVALID_MUSCLE_GROUP"``
- ``"INVALID_DURATION"`` (also when duration is too small to fit ≥2 exercises)
- ``"INVALID_EQUIPMENT"``
- ``"INVALID_LEVEL"``
- ``"INVALID_USER_STATE"``
- ``"NO_EXERCISES_FOUND"`` (filter combo yields fewer than 2 candidates)

The tool is idempotent: identical arguments deterministically produce the same
plan. Selection ties are broken by ascending exercise id.

Note
----
This module only *defines* :data:`TOOL_DESCRIPTOR`. Registration into the
shared :class:`ToolRegistry` happens centrally in task 12.1
(``register_server_tools``). The data file is loaded exactly once at module
import time per Requirement 7.8.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from config import settings
from modules.wger.canonical_exercises import load_canonical_exercise_catalog
from services.agent.tool_registry import ToolDescriptor
from services.workout_planner.integration import (
    WorkoutIntegrationService,
    WorkoutRuntimeContext,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants — design.md §4.6 / §9.5 / requirements 4.2, 4.5, 4.6
# ---------------------------------------------------------------------------

#: Per-exercise time budget. Uniform 5 minutes keeps the tool feasible for any
#: ``duration_min ∈ [10, 120]`` (the property-test domain) since ``2 * 5 = 10``
#: minutes always fits the lower bound and ``8 * 5 = 40`` minutes never busts
#: the upper bound. The user-facing prompt notes that 5-8 minutes per
#: exercise is acceptable; we pick the lower bound for determinism.
_PER_EXERCISE_MINUTES: int = 5

#: Minimum / maximum exercise count required by §9.5 / Requirement 4.2.
_MIN_EXERCISES: int = 2
_MAX_EXERCISES: int = 8

#: Reference weight used when the caller has not supplied a user profile.
#: Calories remain an estimate and the payload explicitly marks them as such.
_REFERENCE_WEIGHT_KG: float = 70.0
_MIN_WEIGHT_KG: float = 30.0
_MAX_WEIGHT_KG: float = 300.0

#: Allowed values for ``muscle_group`` (design.md §9.5 preconditions).
_VALID_MUSCLE_GROUPS: frozenset[str] = frozenset(
    {
        "full_body",
        "chest",
        "back",
        "legs",
        "shoulders",
        "arms",
        "abs",
        "cardio",
        "mobility",
    }
)

#: Mapping from ``muscle_group`` to the set of wger ``category.name`` values
#: that should be considered. ``full_body`` maps to every available category.
_MUSCLE_TO_CATEGORIES: dict[str, frozenset[str]] = {
    "chest": frozenset({"Chest"}),
    "back": frozenset({"Back"}),
    "legs": frozenset({"Legs", "Calves"}),
    "shoulders": frozenset({"Shoulders"}),
    "arms": frozenset({"Arms"}),
    "abs": frozenset({"Abs"}),
    "cardio": frozenset({"Cardio"}),
    "mobility": frozenset(
        {"Abs", "Arms", "Back", "Calves", "Cardio", "Chest", "Legs", "Shoulders"}
    ),
    "full_body": frozenset(
        {"Abs", "Arms", "Back", "Calves", "Cardio", "Chest", "Legs", "Shoulders"}
    ),
}

#: Normalised equipment tags accepted on the wire. ``"any"`` skips equipment
#: filtering; ``"none"`` selects only bodyweight exercises (Requirement 4.5).
_VALID_EQUIPMENT: frozenset[str] = frozenset(
    {
        "any",
        "none",
        "dumbbell",
        "barbell",
        "kettlebell",
        "bench",
        "incline bench",
        "pull-up bar",
        "resistance band",
        "gym mat",
        "cable",
        "machine",
        "stationary bike",
        "jump rope",
        "box",
        "punching bag",
        "suspension trainer",
        "swiss ball",
        "sz-bar",
    }
)

#: wger uses ``"none (bodyweight exercise)"`` as a sentinel equipment entry on
#: a handful of exercises; we treat it as "no equipment required".
_BODYWEIGHT_SENTINEL: str = "none (bodyweight exercise)"

#: Per-equipment difficulty grading used to derive an exercise's effective
#: ``level``. The grading is conservative — barbell-style work is the most
#: technical, dumbbell/kettlebell are intermediate, bodyweight is beginner.
_LEVEL_BY_EQUIPMENT: dict[str, str] = {
    "barbell": "advanced",
    "sz-bar": "advanced",
    "bench": "advanced",
    "incline bench": "advanced",
    "dumbbell": "intermediate",
    "kettlebell": "intermediate",
    "pull-up bar": "intermediate",
    "resistance band": "intermediate",
    "swiss ball": "intermediate",
    "gym mat": "beginner",
    "cable": "intermediate",
    "machine": "intermediate",
    "stationary bike": "beginner",
    "jump rope": "beginner",
    "box": "intermediate",
    "punching bag": "intermediate",
    "suspension trainer": "intermediate",
}

# Some wger rows have an empty equipment array even though the English name
# explicitly names a cable or machine.  Empty metadata must not silently turn
# "Biceps Curl With Cable" into a bodyweight exercise.
_NAME_EQUIPMENT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("barbell", ("barbell",)),
    ("dumbbell", ("dumbbell",)),
    ("kettlebell", ("kettlebell",)),
    ("resistance band", ("resistance band", "elastic band", "with band")),
    ("pull-up bar", ("pull-up", "pull up", "chin-up", "chin up")),
    ("cable", ("cable", "lat pull down", "lat pulldown")),
    ("stationary bike", ("cycling", "stationary bike", "bicicleta estática")),
    ("jump rope", ("jump rope", "skipping rope")),
    ("box", ("box jump",)),
    ("punching bag", ("bag training", "heavy bag")),
    ("suspension trainer", ("suspended", "suspension trainer", "trx")),
    (
        "machine",
        (
            "machine",
            "elliptical",
            "leg press",
            "rowing machine",
            "stair master",
            "treadmill",
            "hack squat",
            "pec deck",
            "hip adduction",
            "hip abduction",
        ),
    ),
    ("bench", ("bench press", "on bench", "using bench")),
    ("gym mat", ("on mat", "gym mat")),
    ("swiss ball", ("swiss ball", "exercise ball", "ball crunch")),
)

_BODYWEIGHT_NAME_HINTS: tuple[str, ...] = (
    "bodyweight",
    "push-up",
    "push up",
    "plank",
    "crunch",
    "sit-up",
    "sit up",
    "bear walk",
    "burpee",
    "jumping jack",
    "mountain climber",
    "air squat",
    "walking",
    "running",
    "jog in place",
    "high knees",
    "high knee skips",
    "butt kicks",
    "talons fesses",
)

_EXCLUDED_EXERCISE_NAME_HINTS: tuple[str, ...] = (
    "meditation",
    "meditación",
)

_ADVANCED_MOVEMENT_HINTS: tuple[str, ...] = (
    "clean and jerk",
    "clean & jerk",
    "snatch",
    "muscle-up",
    "muscle up",
    "pistol squat",
    "handstand",
    "front lever",
    "back lever",
)

_RECOVERY_MOVEMENT_HINTS: tuple[str, ...] = (
    "stretch",
    "mobility",
    "rotation",
    "breathing",
    "walking",
    "march in place",
    "cow-cat",
    "prayer",
)

_RECOVERY_EXCLUSION_HINTS: tuple[str, ...] = (
    "push-up",
    "push up",
    "deadlift",
    "jump",
    "sprint",
)

#: Inclusive level pool. ``"intermediate"`` admits beginner exercises so the
#: candidate pool is non-empty when only easy options exist; ``"advanced"``
#: admits everything. After a fatigue downgrade the pool narrows.
_LEVEL_POOL: dict[str, frozenset[str]] = {
    "beginner": frozenset({"beginner"}),
    "intermediate": frozenset({"beginner", "intermediate"}),
    "advanced": frozenset({"beginner", "intermediate", "advanced"}),
}

#: Ordered downgrade chain used when ``user_state.fatigue_level`` is high.
_LEVEL_DOWNGRADE: dict[str, str] = {
    "advanced": "intermediate",
    "intermediate": "beginner",
    "beginner": "beginner",  # cannot downgrade further
}

_VALID_LEVELS: frozenset[str] = frozenset({"beginner", "intermediate", "advanced"})
_FATIGUE_DOWNGRADE_TRIGGERS: frozenset[str] = frozenset({"high", "very_high"})
_VALID_GOALS: frozenset[str] = frozenset(
    {
        "general_fitness",
        "strength",
        "muscle_gain",
        "endurance",
        "weight_loss",
        "recovery",
    }
)
_WARNING_SYMPTOMS: frozenset[str] = frozenset(
    {
        "chest_pain",
        "severe_shortness_of_breath",
        "dizziness",
        "fainting",
        "irregular_heartbeat",
    }
)

#: wger English translation language id. The translations array has one entry
#: per language; we extract the English name (id=2) as the canonical exercise
#: name for the LLM and the Flutter UI.
_ENGLISH_LANGUAGE_ID: int = 2

#: Categories considered "cardio" for kcal-rate purposes.
_CARDIO_CATEGORIES: frozenset[str] = frozenset({"Cardio"})


# ---------------------------------------------------------------------------
# JSON Schema — passed to the LLM via ToolRegistry.schemas()
# ---------------------------------------------------------------------------

_SUGGEST_WORKOUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "muscle_group": {
            "type": "string",
            "enum": sorted(_VALID_MUSCLE_GROUPS),
            "description": "Nhóm cơ mục tiêu cho buổi tập.",
        },
        "duration_min": {
            "type": "integer",
            "minimum": 10,
            "maximum": 120,
            "description": (
                "Tổng thời lượng buổi tập (phút). Tool sẽ chọn 2-8 bài tập "
                "sao cho tổng duration_minutes không vượt quá giá trị này."
            ),
        },
        "equipment": {
            "type": "string",
            "enum": sorted(_VALID_EQUIPMENT),
            "description": (
                "Dụng cụ sẵn có. 'none' giới hạn ở bài tập tay không, "
                "'any' bỏ qua bộ lọc dụng cụ."
            ),
        },
        "level": {
            "type": "string",
            "enum": sorted(_VALID_LEVELS),
            "description": "Mức độ khó của người tập.",
        },
        "goal": {
            "type": "string",
            "enum": sorted(_VALID_GOALS),
            "default": "general_fitness",
            "description": "Mục tiêu để cá nhân hóa số hiệp, số lần và thời gian nghỉ.",
        },
        "user_state": {
            "type": ["object", "null"],
            "description": (
                "Trạng thái user (tuỳ chọn). Nếu fatigue_level ∈ "
                "{high, very_high} thì level được hạ một nấc trước khi lọc."
            ),
            "properties": {
                "fatigue_level": {
                    "type": "string",
                    "enum": ["low", "moderate", "high", "very_high"],
                },
                "weight_kg": {
                    "type": "number",
                    "minimum": _MIN_WEIGHT_KG,
                    "maximum": _MAX_WEIGHT_KG,
                    "description": "Cân nặng hiện tại để cá nhân hóa ước tính kcal.",
                },
                "warning_symptoms": {
                    "type": "array",
                    "items": {"type": "string", "enum": sorted(_WARNING_SYMPTOMS)},
                    "uniqueItems": True,
                    "description": (
                        "Triệu chứng cảnh báo hiện tại. Nếu có, tool từ chối "
                        "kê buổi tập và trả UNSAFE_TO_RECOMMEND_WORKOUT."
                    ),
                },
            },
            "additionalProperties": True,
        },
    },
    "required": ["muscle_group", "duration_min", "equipment", "level"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Data loading (once at import time per Requirement 7.8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _ExerciseRecord:
    """A pre-resolved wger exercise ready for filtering and selection."""

    id: int
    name: str
    category: str
    equipment: tuple[str, ...]       # normalised equipment tags, lowercased
    is_bodyweight: bool
    derived_level: str               # one of beginner/intermediate/advanced


# Computed at module import; treated as immutable thereafter.
_EXERCISES: tuple[_ExerciseRecord, ...] = ()


def _data_dir() -> Path:
    # backend/services/agent/tools/workout.py → backend/data
    return Path(__file__).resolve().parent.parent.parent.parent / "data"


def _normalise_equipment_name(raw: str) -> str:
    """Map a wger equipment ``name`` to its canonical lowercase tag.

    The wger sentinel ``"none (bodyweight exercise)"`` is collapsed to
    ``"none"`` so the rest of the pipeline only has to recognise one form.
    """
    text = (raw or "").strip().lower()
    if text == _BODYWEIGHT_SENTINEL.lower():
        return "none"
    return text


def _english_name(translations: list[dict[str, Any]] | None) -> str | None:
    """Pick the English (``language=2``) name from a translations array."""
    if not translations:
        return None
    for tr in translations:
        if not isinstance(tr, dict):
            continue
        if tr.get("language") == _ENGLISH_LANGUAGE_ID:
            name = tr.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    # Fallback: first translation with a non-empty name.
    for tr in translations:
        if isinstance(tr, dict):
            name = tr.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _infer_equipment_from_name(name: str) -> tuple[str, ...]:
    """Recover explicit equipment named in a row with incomplete metadata."""

    lowered = name.casefold()
    return tuple(
        tag
        for tag, hints in _NAME_EQUIPMENT_HINTS
        if any(hint in lowered for hint in hints)
    )


def _looks_bodyweight(name: str) -> bool:
    lowered = name.casefold()
    return any(hint in lowered for hint in _BODYWEIGHT_NAME_HINTS)


def _derive_level(equipment_tags: tuple[str, ...], name: str = "") -> str:
    """Infer a conservative difficulty from equipment and movement complexity.

    Equipment is only a proxy because wger does not publish a canonical
    difficulty field. Technical movement names take precedence, then the
    highest-priority equipment grade wins.
    """
    lowered = name.casefold()
    if any(hint in lowered for hint in _ADVANCED_MOVEMENT_HINTS):
        return "advanced"

    has_advanced = False
    has_intermediate = False
    for tag in equipment_tags:
        grade = _LEVEL_BY_EQUIPMENT.get(tag)
        if grade == "advanced":
            has_advanced = True
        elif grade == "intermediate":
            has_intermediate = True
    if has_advanced:
        return "advanced"
    if has_intermediate:
        return "intermediate"
    return "beginner"


def _build_exercise_record(entry: dict[str, Any]) -> _ExerciseRecord | None:
    """Resolve one raw wger entry into an :class:`_ExerciseRecord`, or skip."""
    try:
        ex_id = int(entry["id"])
    except (KeyError, TypeError, ValueError):
        return None

    cat = entry.get("category") or {}
    category = cat.get("name") if isinstance(cat, dict) else None
    if not isinstance(category, str) or not category:
        return None

    name = _english_name(entry.get("translations"))
    if not name:
        return None
    if any(hint in name.casefold() for hint in _EXCLUDED_EXERCISE_NAME_HINTS):
        return None

    raw_equipment = entry.get("equipment") or []
    equipment_tags: list[str] = []
    is_bodyweight = False
    if raw_equipment:
        for item in raw_equipment:
            if not isinstance(item, dict):
                continue
            tag = _normalise_equipment_name(item.get("name", ""))
            if not tag:
                continue
            if tag == "none":
                is_bodyweight = True
                continue
            equipment_tags.append(tag)
    # wger contains rows whose empty equipment metadata contradicts names such
    # as "... With Cable" or "... Leg Press Machine". Recover those explicit
    # hints and never assume that an empty list means bodyweight.
    inferred_tags = _infer_equipment_from_name(name)
    equipment_tags.extend(tag for tag in inferred_tags if tag not in equipment_tags)
    if not equipment_tags and not is_bodyweight:
        is_bodyweight = _looks_bodyweight(name)

    equipment_tuple = tuple(equipment_tags)
    derived_level = _derive_level(equipment_tuple, name)
    return _ExerciseRecord(
        id=ex_id,
        name=name,
        category=category,
        equipment=equipment_tuple,
        is_bodyweight=is_bodyweight,
        derived_level=derived_level,
    )


def _load_exercises() -> tuple[_ExerciseRecord, ...]:
    path = _data_dir() / "wger_exercises_raw.json"
    try:
        with path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        logger.error("wger_exercises_raw.json not found at %s", path)
        return ()

    if not isinstance(raw, list):
        logger.error("wger_exercises_raw.json is not a list")
        return ()

    records: list[_ExerciseRecord] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        rec = _build_exercise_record(entry)
        if rec is not None:
            records.append(rec)

    # Stable order: by id ascending. Selection ties also use id ascending so
    # the same arguments always pick the same exercises.
    records.sort(key=lambda r: r.id)
    logger.info(
        "suggest_workout: loaded %d exercises from %s", len(records), path.name
    )
    return tuple(records)


# Eagerly load at import time. ``_EXERCISES`` is treated as immutable.
_EXERCISES = _load_exercises()


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def _equipment_matches(
    exercise: _ExerciseRecord, requested: str
) -> bool:
    """Return True if ``exercise`` is compatible with the requested equipment.

    Rules (Requirement 4.5):
      - ``"any"``: always matches.
      - ``"none"``: only bodyweight exercises (empty equipment list, or list
        containing only the wger bodyweight sentinel).
      - any other tag: exercise must include that exact tag in its
        equipment list.
    """
    if requested == "any":
        return True
    if requested == "none":
        return exercise.is_bodyweight and not exercise.equipment
    return requested in exercise.equipment


def _filter_candidates(
    muscle_group: str,
    equipment: str,
    allowed_levels: frozenset[str],
    goal: str,
) -> list[_ExerciseRecord]:
    """Return all exercises matching ``muscle_group`` × ``equipment`` × levels."""
    categories = _MUSCLE_TO_CATEGORIES[muscle_group]
    return [
        ex
        for ex in _EXERCISES
        if ex.category in categories
        and _equipment_matches(ex, equipment)
        and ex.derived_level in allowed_levels
        and (goal != "recovery" or _is_recovery_exercise(ex))
    ]


def _is_recovery_exercise(exercise: _ExerciseRecord) -> bool:
    name = exercise.name.casefold()
    return any(hint in name for hint in _RECOVERY_MOVEMENT_HINTS) and not any(
        hint in name for hint in _RECOVERY_EXCLUSION_HINTS
    )


# ---------------------------------------------------------------------------
# Selection and payload assembly
# ---------------------------------------------------------------------------


def _user_state_value(user_state: object | None, key: str) -> object | None:
    """Read a field from a mapping/model and reject primitive state values."""

    if user_state is None:
        return None
    if isinstance(user_state, (str, bytes, int, float, bool)):
        raise ValueError("INVALID_USER_STATE")
    if isinstance(user_state, Mapping):
        return user_state.get(key)
    return getattr(user_state, key, None)


def _resolve_user_state_fatigue(user_state: object | None) -> str | None:
    """Read ``fatigue_level`` from a Pydantic model, dataclass, or mapping.

    Returns the fatigue string if present, else ``None``. Raises
    ``ValueError("INVALID_USER_STATE")`` only when ``user_state`` is a
    primitive that clearly cannot carry the field (string, bytes, number).
    Unknown ``fatigue_level`` values are treated as "no downgrade".
    """
    value = _user_state_value(user_state, "fatigue_level")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("INVALID_USER_STATE")
    return value


def _resolve_weight_kg(user_state: object | None) -> float:
    value = _user_state_value(user_state, "weight_kg")
    if value is None:
        return _REFERENCE_WEIGHT_KG
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("INVALID_USER_STATE")
    weight = float(value)
    if not _MIN_WEIGHT_KG <= weight <= _MAX_WEIGHT_KG:
        raise ValueError("INVALID_USER_STATE")
    return weight


def _resolve_warning_symptoms(user_state: object | None) -> frozenset[str]:
    value = _user_state_value(user_state, "warning_symptoms")
    if value is None:
        return frozenset()
    if not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("INVALID_USER_STATE")
    symptoms = frozenset(value)
    if any(not isinstance(item, str) for item in symptoms):
        raise ValueError("INVALID_USER_STATE")
    if not symptoms.issubset(_WARNING_SYMPTOMS):
        raise ValueError("INVALID_USER_STATE")
    return symptoms


def _estimate_met(exercise: _ExerciseRecord) -> float:
    """Estimate exercise intensity without assigning one value to a category."""
    name = exercise.name.lower()

    if any(term in name for term in ("breathing", "stretch", "mobility")):
        return 2.3
    if any(term in name for term in ("walking", "march in place", "cow-cat")):
        return 3.5
    if any(term in name for term in ("sprint", "hiit", "tabata", "burpee")):
        return 11.5
    if any(term in name for term in ("jump rope", "skipping", "box jump")):
        return 10.0
    if any(term in name for term in ("running", "jogging", "treadmill")):
        return 8.5
    if any(term in name for term in ("rowing", "swimming")):
        return 7.5
    if any(term in name for term in ("cycling", "spinning", "elliptical")):
        return 6.5
    if any(term in name for term in ("deadlift", "squat", "clean", "snatch")):
        return 6.5
    if any(
        term in name
        for term in (
            "bench press",
            "pull up",
            "pull-up",
            "push up",
            "push-up",
            "overhead press",
            "barbell row",
        )
    ):
        return 6.0
    if any(term in name for term in ("plank", "crunch", "sit up", "core")):
        return 4.2
    if any(
        term in name
        for term in (
            "curl",
            "extension",
            "raise",
            "fly",
            "adduction",
            "abduction",
        )
    ):
        return 3.8

    # Stable variation prevents otherwise-unrecognised exercises from all
    # displaying the exact same energy while keeping the tool idempotent.
    checksum = sum((index + 1) * ord(char) for index, char in enumerate(name))
    variation = ((checksum % 7) - 3) * 0.1
    base = 7.0 if exercise.category in _CARDIO_CATEGORIES else 4.5
    return round(max(3.0, min(11.0, base + variation)), 1)


def _calories_for(
    exercise: _ExerciseRecord,
    weight_kg: float,
    *,
    met: float | None = None,
) -> float:
    """Estimate gross energy with the standard-MET oxygen-cost equation."""

    resolved_met = _estimate_met(exercise) if met is None else met
    return round(
        resolved_met * 3.5 * weight_kg / 200.0 * _PER_EXERCISE_MINUTES,
        2,
    )


def _resistance_prescription(level: str, goal: str) -> tuple[int, str, int]:
    """Return sets, repetitions, and rest seconds for one resistance movement."""

    level_sets = {
        "beginner": 1,
        "intermediate": 2,
        "advanced": 3,
    }
    if goal == "recovery":
        return 1, "30-45 seconds controlled", 15
    sets = level_sets[level]
    if goal in {"strength", "muscle_gain"}:
        # Strength-oriented work starts with at least two working sets. Across
        # three full-body days, muscle-gain plans then progress toward the
        # roughly ten weekly sets per muscle group highlighted by ACSM.
        sets = max(2, sets)
    prescriptions = {
        "general_fitness": ("8-12", 60),
        "strength": ("5-8", 120),
        "muscle_gain": ("8-12", 90),
        "endurance": ("12-15", 45),
        "weight_loss": ("10-15", 45),
    }
    reps, rest_seconds = prescriptions[goal]
    return sets, reps, rest_seconds


def _exercise_payload(
    exercise: _ExerciseRecord,
    *,
    level: str,
    goal: str,
    weight_kg: float,
) -> dict[str, Any]:
    is_cardio = exercise.category in _CARDIO_CATEGORIES
    if is_cardio:
        sets, reps, rest_seconds = 1, "continuous", 0
    else:
        sets, reps, rest_seconds = _resistance_prescription(level, goal)
    met = _estimate_met(exercise)
    if goal == "recovery":
        met = min(met, 3.5)
    return {
        "wger_id": exercise.id,
        "name": exercise.name,
        "category": exercise.category,
        "duration_minutes": _PER_EXERCISE_MINUTES,
        "sets": sets,
        "reps": reps,
        "rest_seconds": rest_seconds,
        "met": met,
        "calories_burned": _calories_for(exercise, weight_kg, met=met),
        "calories_estimated": True,
    }


def _select_diverse(
    candidates: list[_ExerciseRecord], count: int
) -> list[_ExerciseRecord]:
    """Select deterministically while spreading full-body plans across groups."""
    buckets: dict[str, list[_ExerciseRecord]] = {}
    for exercise in candidates:
        buckets.setdefault(exercise.category, []).append(exercise)

    selected: list[_ExerciseRecord] = []
    offsets = {category: 0 for category in buckets}
    categories = sorted(buckets)
    while len(selected) < count:
        added = False
        for category in categories:
            offset = offsets[category]
            bucket = buckets[category]
            if offset >= len(bucket):
                continue
            selected.append(bucket[offset])
            offsets[category] = offset + 1
            added = True
            if len(selected) == count:
                break
        if not added:
            break
    return selected


def _workout_title(muscle_group: str, level: str) -> str:
    pretty_group = muscle_group.replace("_", " ").title()
    return f"{pretty_group} workout ({level})"


def suggest_workout(
    muscle_group: str,
    duration_min: int,
    equipment: str,
    level: str,
    user_state: object | None = None,
    goal: str = "general_fitness",
) -> dict[str, Any]:
    """Build a 2-8 exercise plan honouring the time and equipment budget.

    Parameters
    ----------
    muscle_group:
        One of ``"full_body"``, ``"chest"``, ``"back"``, ``"legs"``,
        ``"shoulders"``, ``"arms"``, ``"abs"``, ``"cardio"``.
    duration_min:
        Total session length in minutes, ``∈ [10, 120]``. The returned plan
        satisfies ``sum(ex.duration_minutes) ≤ duration_min``.
    equipment:
        One of :data:`_VALID_EQUIPMENT`. ``"none"`` restricts the result to
        bodyweight exercises; ``"any"`` skips equipment filtering.
    level:
        Difficulty pool: ``"beginner"`` (only beginner exercises),
        ``"intermediate"`` (beginner + intermediate), ``"advanced"`` (all).
    user_state:
        Optional state object/mapping with ``fatigue_level``, ``weight_kg``,
        and ``warning_symptoms`` fields. When
        ``fatigue_level ∈ {"high", "very_high"}`` the requested ``level`` is
        downgraded one notch (advanced → intermediate → beginner) before
        filtering. Warning symptoms make the tool refuse a workout.
    goal:
        One of ``general_fitness``, ``strength``, ``muscle_gain``,
        ``endurance``, ``weight_loss``, or ``recovery``. Controls sets,
        repetitions, and rest.

    Returns
    -------
    dict
        See the module docstring for the payload shape.

    Raises
    ------
    ValueError
        ``"INVALID_MUSCLE_GROUP"``, ``"INVALID_DURATION"``,
        ``"INVALID_EQUIPMENT"``, ``"INVALID_LEVEL"``,
        ``"INVALID_USER_STATE"``, ``"INVALID_GOAL"``,
        ``"UNSAFE_TO_RECOMMEND_WORKOUT"``, or ``"NO_EXERCISES_FOUND"``.
    """
    # ---- input validation --------------------------------------------------
    if muscle_group not in _VALID_MUSCLE_GROUPS:
        raise ValueError("INVALID_MUSCLE_GROUP")

    if isinstance(duration_min, bool) or not isinstance(duration_min, int):
        # ``bool`` is a subclass of ``int``; reject it explicitly.
        raise ValueError("INVALID_DURATION")
    if duration_min < _MIN_EXERCISES * _PER_EXERCISE_MINUTES or duration_min > 120:
        # Need to fit at least two ``_PER_EXERCISE_MINUTES``-blocks.
        raise ValueError("INVALID_DURATION")

    if equipment not in _VALID_EQUIPMENT:
        raise ValueError("INVALID_EQUIPMENT")

    if level not in _VALID_LEVELS:
        raise ValueError("INVALID_LEVEL")

    if goal not in _VALID_GOALS:
        raise ValueError("INVALID_GOAL")

    fatigue = _resolve_user_state_fatigue(user_state)
    weight_kg = _resolve_weight_kg(user_state)
    warning_symptoms = _resolve_warning_symptoms(user_state)
    if warning_symptoms:
        raise ValueError("UNSAFE_TO_RECOMMEND_WORKOUT")

    # ---- fatigue downgrade (Requirement 4.6) ------------------------------
    effective_level = level
    if fatigue in _FATIGUE_DOWNGRADE_TRIGGERS:
        effective_level = _LEVEL_DOWNGRADE[level]
    if goal == "recovery":
        effective_level = "beginner"

    allowed_levels = _LEVEL_POOL[effective_level]

    # ---- filter and select -------------------------------------------------
    candidates = _filter_candidates(
        muscle_group,
        equipment,
        allowed_levels,
        goal,
    )
    if len(candidates) < _MIN_EXERCISES:
        raise ValueError("NO_EXERCISES_FOUND")

    # Maximum exercises that fit ``duration_min``. Guarded by the validation
    # above so ``max_by_duration ≥ 2``.
    max_by_duration = duration_min // _PER_EXERCISE_MINUTES
    k = min(_MAX_EXERCISES, max_by_duration, len(candidates))
    if k < _MIN_EXERCISES:
        # Defensive — should be unreachable given the prior validation, but
        # keep the contract explicit.
        raise ValueError("INVALID_DURATION")

    selected = _select_diverse(candidates, k)

    # ---- assemble payload -------------------------------------------------
    exercises_out = [
        _exercise_payload(
            ex,
            level=effective_level,
            goal=goal,
            weight_kg=weight_kg,
        )
        for ex in selected
    ]
    total_minutes = sum(ex["duration_minutes"] for ex in exercises_out)
    total_calories = round(
        sum(ex["calories_burned"] for ex in exercises_out), 2
    )

    return {
        "workout_title": _workout_title(muscle_group, effective_level),
        "exercises": exercises_out,
        "total_duration_minutes": total_minutes,
        "total_calories_burned": total_calories,
        "effective_level": effective_level,
        "goal": goal,
        "calorie_estimate": {
            "estimated": True,
            "weight_kg": weight_kg,
            "method": "standard_MET_x_3.5_x_kg_div_200_x_minutes",
            "note": "Ước tính quần thể, không phải phép đo tiêu hao cá nhân.",
        },
        "guidance": {
            "progression": (
                "Tăng dần thời lượng và tần suất trước khi tăng cường độ; "
                "ưu tiên kỹ thuật và khả năng duy trì đều đặn."
            ),
            "weekly_target": (
                "Người lớn nên hướng tới ít nhất 150 phút aerobic cường độ "
                "vừa mỗi tuần và tăng cơ từ 2 ngày, tùy khả năng."
            ),
            "safety": (
                "Dừng tập và tìm đánh giá y tế nếu có đau ngực, khó thở bất thường, "
                "chóng mặt, ngất hoặc nhịp tim nhanh/không đều."
            ),
        },
        "evidence_sources": [
            "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html",
            "https://acsm.org/resistance-training-guidelines-update-2026/",
            "https://pacompendium.com/adult-compendium/",
        ],
    }


@lru_cache(maxsize=1)
def _search_exercise_records() -> tuple[dict[str, Any], ...]:
    """Keep the complete canonical catalog immutable for read-only search."""

    return tuple(load_canonical_exercise_catalog())


def _normalize_catalog_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.replace("đ", "d").split())


def _named_values(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            name = item.get("name")
        else:
            name = item
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


def _exercise_catalog_page(
    page: int, page_size: int, *, include_details: bool
) -> tuple[int, int]:
    if (
        isinstance(page, bool)
        or isinstance(page_size, bool)
        or not isinstance(page, int)
        or not isinstance(page_size, int)
        or page < 1
        or page_size < 1
        or page_size > 20
    ):
        raise ValueError("INVALID_CATALOG_PAGE")
    if include_details and page_size > 5:
        raise ValueError("DETAIL_PAGE_TOO_LARGE")
    start = (page - 1) * page_size
    return start, start + page_size


def _exercise_search_rank(record: Mapping[str, Any], query: str) -> int | None:
    if not query:
        return 4
    name_en = _normalize_catalog_text(record.get("name_en"))
    name_vi = _normalize_catalog_text(record.get("name_vi"))
    if query in {name_en, name_vi}:
        return 0
    if name_en.startswith(query) or name_vi.startswith(query):
        return 1
    if query in name_en or query in name_vi:
        return 2
    instructions = record.get("instructions")
    instruction_text = (
        instructions.get("text", "") if isinstance(instructions, Mapping) else ""
    )
    aliases = (
        instructions.get("aliases", [])
        if isinstance(instructions, Mapping)
        else []
    )
    searchable = _normalize_catalog_text(
        " ".join(
            [
                name_en,
                name_vi,
                str(instruction_text),
                *[str(item) for item in aliases if isinstance(item, str)],
                *_named_values(record.get("primary_muscles")),
                *_named_values(record.get("secondary_muscles")),
                *_named_values(record.get("equipment")),
            ]
        )
    )
    if all(token in searchable for token in query.split()):
        return 3
    return None


def _catalog_exercise_payload(
    record: Mapping[str, Any],
    recommendation: _ExerciseRecord | None,
    *,
    include_details: bool,
) -> dict[str, Any]:
    category = record.get("category")
    category_name = category.get("name") if isinstance(category, Mapping) else None
    payload: dict[str, Any] = {
        "exercise_id": int(record["source_exercise_id"]),
        "name": record.get("name_vi") or record.get("name_en"),
        "name_en": record.get("name_en"),
        "name_vi": record.get("name_vi"),
        "category": category_name,
        "equipment": _named_values(record.get("equipment")),
        "primary_muscles": _named_values(record.get("primary_muscles")),
        "secondary_muscles": _named_values(record.get("secondary_muscles")),
        "derived_level": recommendation.derived_level if recommendation else None,
        "recommendation_eligible": recommendation is not None,
        "review_status": record.get("review_status"),
        "has_instructions": bool(
            isinstance(record.get("instructions"), Mapping)
            and record["instructions"].get("text")
        ),
    }
    if include_details:
        payload.update(
            {
                "instructions": deepcopy(record.get("instructions")),
                "media": deepcopy(record.get("media")),
                "difficulty": deepcopy(record.get("difficulty")),
                "movement_pattern": deepcopy(record.get("movement_pattern")),
                "laterality": deepcopy(record.get("laterality")),
                "quality_flags": list(record.get("quality_flags") or []),
                "source": record.get("source"),
                "source_version": record.get("source_version"),
                "source_license_metadata": deepcopy(
                    record.get("source_license_metadata")
                ),
            }
        )
    return payload


def search_exercise_catalog(
    query: str = "",
    exercise_id: int | None = None,
    muscle_group: str | None = None,
    equipment: str | None = None,
    level: str | None = None,
    page: int = 1,
    page_size: int = 5,
    include_details: bool = False,
) -> dict[str, Any]:
    """Search all canonical exercise rows before applying pagination."""

    if not isinstance(query, str) or len(query) > 160:
        raise ValueError("INVALID_CATALOG_QUERY")
    if exercise_id is not None and (
        isinstance(exercise_id, bool)
        or not isinstance(exercise_id, int)
        or exercise_id < 1
    ):
        raise ValueError("INVALID_EXERCISE_ID")
    if muscle_group is not None and muscle_group not in _VALID_MUSCLE_GROUPS:
        raise ValueError("INVALID_MUSCLE_GROUP")
    if equipment is not None and equipment not in _VALID_EQUIPMENT:
        raise ValueError("INVALID_EQUIPMENT")
    if level is not None and level not in _VALID_LEVELS:
        raise ValueError("INVALID_LEVEL")
    start, end = _exercise_catalog_page(
        page, page_size, include_details=include_details
    )
    clean_query = _normalize_catalog_text(query)
    recommendation_by_id = {record.id: record for record in _EXERCISES}
    matches: list[tuple[int, int, Mapping[str, Any], _ExerciseRecord | None]] = []
    records = _search_exercise_records()
    for record in records:
        source_id = int(record["source_exercise_id"])
        recommendation = recommendation_by_id.get(source_id)
        category = record.get("category")
        category_name = category.get("name") if isinstance(category, Mapping) else None
        if exercise_id is not None and source_id != exercise_id:
            continue
        if (
            muscle_group is not None
            and category_name not in _MUSCLE_TO_CATEGORIES[muscle_group]
        ):
            continue
        if equipment is not None and equipment != "any":
            if recommendation is None or not _equipment_matches(
                recommendation, equipment
            ):
                continue
        if level is not None and (
            recommendation is None or recommendation.derived_level != level
        ):
            continue
        rank = _exercise_search_rank(record, clean_query)
        if rank is not None:
            matches.append((rank, source_id, record, recommendation))
    matches.sort(key=lambda item: (item[0], item[1]))
    return {
        "catalog": "CANONICAL_WGER_EXERCISE_CATALOG",
        "catalog_size": len(records),
        "recommendation_catalog_size": len(_EXERCISES),
        "scanned_count": len(records),
        "matched_count": len(matches),
        "page": page,
        "page_size": page_size,
        "has_more": end < len(matches),
        "next_page": page + 1 if end < len(matches) else None,
        "results": [
            _catalog_exercise_payload(
                record, recommendation, include_details=include_details
            )
            for _, _, record, recommendation in matches[start:end]
        ],
    }


_LEGACY_TO_E4_GOAL = {
    "general_fitness": "GENERAL_FITNESS",
    "weight_loss": "WEIGHT_MANAGEMENT",
    "muscle_gain": "HYPERTROPHY",
    "strength": "STRENGTH",
    "endurance": "MUSCULAR_ENDURANCE",
    "recovery": "MOBILITY",
}

_SEARCH_EXERCISE_CATALOG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "maxLength": 160,
            "default": "",
            "description": "Tên bài, cơ, dụng cụ hoặc nội dung hướng dẫn; để trống để duyệt toàn bộ catalog.",
        },
        "exercise_id": {
            "type": "integer",
            "minimum": 1,
            "description": "Wger source exercise ID chính xác.",
        },
        "muscle_group": {
            "type": "string",
            "enum": sorted(_VALID_MUSCLE_GROUPS),
        },
        "equipment": {
            "type": "string",
            "enum": sorted(_VALID_EQUIPMENT),
        },
        "level": {
            "type": "string",
            "enum": sorted(_VALID_LEVELS),
            "description": "Lọc theo mức khó suy ra của recommendation catalog.",
        },
        "page": {"type": "integer", "minimum": 1, "default": 1},
        "page_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 5,
        },
        "include_details": {
            "type": "boolean",
            "default": False,
            "description": "Trả hướng dẫn, media và provenance; tối đa 5 kết quả mỗi trang.",
        },
    },
    "additionalProperties": False,
}


async def suggest_workout_facade(
    muscle_group: str,
    duration_min: int,
    equipment: str,
    level: str,
    user_state: object | None = None,
    goal: str = "general_fitness",
    _runtime_context: WorkoutRuntimeContext | None = None,
) -> dict[str, Any]:
    """Keep the legacy surface while selecting its authority by rollout mode.

    ``off`` and ``shadow`` intentionally preserve the exact legacy response.
    In ``enforced`` this is only a compatibility entry point for the one E4
    prescription path; an E4 failure is returned as a typed result rather
    than falling back to the older generic algorithm.
    """
    # A newly captured chat-intake revision is intentionally not a usable
    # prescription profile until the user has heard and confirmed the recap.
    # Apply this guard to the compatibility route as well as the E4 route so a
    # future prompt/model change cannot sidestep the confirmation boundary.
    if isinstance(_runtime_context, WorkoutRuntimeContext):
        context = _runtime_context.user_context
        profile = context.get("workout_profile") if isinstance(context, Mapping) else None
        if (
            isinstance(profile, Mapping)
            and str(profile.get("intake_confirmation_status")).upper()
            == "PENDING_CONFIRMATION"
        ):
            return {
                "status": "PROFILE_CONFIRMATION_REQUIRED",
                "error_code": "WORKOUT_PROFILE_RECAP_REQUIRED",
            }
    if settings.workout_planner_mode in {"off", "shadow"}:
        legacy = suggest_workout(
            muscle_group, duration_min, equipment, level, user_state, goal
        )
        if settings.workout_planner_shadow_enabled and isinstance(_runtime_context, WorkoutRuntimeContext):
            try:
                comparison = await WorkoutIntegrationService(_runtime_context.db_session).build(
                    _runtime_context,
                    goal_override=_LEGACY_TO_E4_GOAL.get(goal),
                    requested_duration_minutes=duration_min,
                    available_equipment_override=(equipment,),
                    requested_body_area=muscle_group,
                )
                logger.info(
                    "E4.1 shadow comparison status=%s planner=%s validation_hard=%s",
                    comparison.status,
                    comparison.plan.planner_version if comparison.plan is not None else None,
                    comparison.validation.get("hard_violation_count"),
                )
            except Exception:
                # Shadow observation must not alter a legacy caller's result.
                logger.exception("E4.1 shadow workout comparison failed")
        return legacy

    runtime = _runtime_context or WorkoutRuntimeContext(None, None, None, None)
    outcome = await WorkoutIntegrationService(runtime.db_session).build(
        runtime,
        goal_override=_LEGACY_TO_E4_GOAL.get(goal),
        requested_duration_minutes=duration_min,
        available_equipment_override=(equipment,),
        requested_body_area=muscle_group,
    )
    return outcome.to_tool_payload()


# ---------------------------------------------------------------------------
# Descriptor — consumed by ``register_server_tools`` (task 12.1)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="suggest_workout",
    description=(
        "Gợi ý 2-8 bài tập wger phù hợp với muscle_group, duration_min, "
        "equipment, level và goal. Tôn trọng ràng buộc "
        "sum(ex.duration_minutes) ≤ duration_min và tự hạ level một nấc "
        "khi mệt; dùng user_state.weight_kg để ước tính kcal và từ chối "
        "gợi ý khi có warning_symptoms."
    ),
    parameters_schema=_SUGGEST_WORKOUT_SCHEMA,
    side="server",
    fn=suggest_workout_facade,
    idempotent=True,
)

SEARCH_CATALOG_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="search_exercise_catalog",
    description=(
        "Quét toàn bộ catalog bài tập canonical trước khi lọc và phân trang. "
        "Tìm theo tên, nhóm cơ, dụng cụ, hướng dẫn hoặc Wger ID; dùng "
        "include_details=true với tối đa 5 kết quả để đọc hướng dẫn và nguồn. "
        "Kết quả tra cứu không tự động trở thành một khuyến nghị tập luyện."
    ),
    parameters_schema=_SEARCH_EXERCISE_CATALOG_SCHEMA,
    side="server",
    fn=search_exercise_catalog,
    idempotent=True,
)


__all__ = [
    "SEARCH_CATALOG_DESCRIPTOR",
    "TOOL_DESCRIPTOR",
    "search_exercise_catalog",
    "suggest_workout",
    "suggest_workout_facade",
]
