"""``suggest_workout`` server-side tool.

Selects 2-8 wger exercises matching a muscle group, available equipment, and
target difficulty ``level``. The selected list satisfies
``sum(ex.duration_minutes) ≤ duration_min``. When ``user_state.fatigue_level``
is ``"high"`` or ``"very_high"``, the requested ``level`` is automatically
downgraded one notch (``advanced → intermediate → beginner``) so a tired user
gets easier exercises. When ``equipment == "none"`` the tool returns only
bodyweight exercises.

References
----------
- ``backend/.kiro/specs/chatbot-redesign/design.md`` §4.6 (Server-side tools),
  §5 (Tool catalog), §6.2 (ExercisePlanPayload shape), §9.5 (formal contract).
- Requirements 4.2, 4.5, 4.6, 7.8 in
  ``backend/.kiro/specs/chatbot-redesign/requirements.md``.

Contract
--------
``suggest_workout(muscle_group, duration_min, equipment, level, user_state=None) -> dict``

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from services.agent.tool_registry import ToolDescriptor

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
}

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


def _derive_level(equipment_tags: tuple[str, ...]) -> str:
    """Infer the difficulty level of an exercise from its equipment tags.

    Highest-priority equipment wins (``advanced > intermediate > beginner``).
    Bodyweight or no-equipment maps to ``beginner``.
    """
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

    raw_equipment = entry.get("equipment") or []
    equipment_tags: list[str] = []
    is_bodyweight = False
    if not raw_equipment:
        # No equipment listed → bodyweight by convention.
        is_bodyweight = True
    else:
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
        # If equipment array contained only the bodyweight sentinel, treat it
        # the same as an empty array.
        if not equipment_tags and is_bodyweight:
            pass
        elif not equipment_tags and not is_bodyweight:
            # Nothing usable was decoded → skip.
            return None

    derived_level = _derive_level(tuple(equipment_tags))
    return _ExerciseRecord(
        id=ex_id,
        name=name,
        category=category,
        equipment=tuple(equipment_tags),
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
    muscle_group: str, equipment: str, allowed_levels: frozenset[str]
) -> list[_ExerciseRecord]:
    """Return all exercises matching ``muscle_group`` × ``equipment`` × levels."""
    categories = _MUSCLE_TO_CATEGORIES[muscle_group]
    return [
        ex
        for ex in _EXERCISES
        if ex.category in categories
        and _equipment_matches(ex, equipment)
        and ex.derived_level in allowed_levels
    ]


# ---------------------------------------------------------------------------
# Selection and payload assembly
# ---------------------------------------------------------------------------


def _resolve_user_state_fatigue(
    user_state: object | None,
) -> str | None:
    """Read ``fatigue_level`` from a Pydantic model, dataclass, or mapping.

    Returns the fatigue string if present, else ``None``. Raises
    ``ValueError("INVALID_USER_STATE")`` only when ``user_state`` is a
    primitive that clearly cannot carry the field (string, bytes, number).
    Unknown ``fatigue_level`` values are treated as "no downgrade".
    """
    if user_state is None:
        return None
    if isinstance(user_state, (str, bytes, int, float, bool)):
        raise ValueError("INVALID_USER_STATE")
    if isinstance(user_state, Mapping):
        value = user_state.get("fatigue_level")
    else:
        value = getattr(user_state, "fatigue_level", None)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("INVALID_USER_STATE")
    return value


def _estimate_met(exercise: _ExerciseRecord) -> float:
    """Estimate exercise intensity without assigning one value to a category."""
    name = exercise.name.lower()

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


def _calories_for(exercise: _ExerciseRecord) -> float:
    met = _estimate_met(exercise)
    return round(
        met * _REFERENCE_WEIGHT_KG * (_PER_EXERCISE_MINUTES / 60.0),
        2,
    )


def _exercise_payload(exercise: _ExerciseRecord) -> dict[str, Any]:
    is_cardio = exercise.category in _CARDIO_CATEGORIES
    return {
        "wger_id": exercise.id,
        "name": exercise.name,
        "category": exercise.category,
        "duration_minutes": _PER_EXERCISE_MINUTES,
        "sets": 1 if is_cardio else 3,
        "reps": "continuous" if is_cardio else "10-12",
        "met": _estimate_met(exercise),
        "calories_burned": _calories_for(exercise),
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
        Optional state object/mapping with a ``fatigue_level`` field. When
        ``fatigue_level ∈ {"high", "very_high"}`` the requested ``level`` is
        downgraded one notch (advanced → intermediate → beginner) before
        filtering.

    Returns
    -------
    dict
        See the module docstring for the payload shape.

    Raises
    ------
    ValueError
        ``"INVALID_MUSCLE_GROUP"``, ``"INVALID_DURATION"``,
        ``"INVALID_EQUIPMENT"``, ``"INVALID_LEVEL"``,
        ``"INVALID_USER_STATE"``, or ``"NO_EXERCISES_FOUND"``.
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

    fatigue = _resolve_user_state_fatigue(user_state)

    # ---- fatigue downgrade (Requirement 4.6) ------------------------------
    effective_level = level
    if fatigue in _FATIGUE_DOWNGRADE_TRIGGERS:
        effective_level = _LEVEL_DOWNGRADE[level]

    allowed_levels = _LEVEL_POOL[effective_level]

    # ---- filter and select -------------------------------------------------
    candidates = _filter_candidates(muscle_group, equipment, allowed_levels)
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
    exercises_out = [_exercise_payload(ex) for ex in selected]
    total_minutes = sum(ex["duration_minutes"] for ex in exercises_out)
    total_calories = round(
        sum(ex["calories_burned"] for ex in exercises_out), 2
    )

    return {
        "workout_title": _workout_title(muscle_group, effective_level),
        "exercises": exercises_out,
        "total_duration_minutes": total_minutes,
        "total_calories_burned": total_calories,
    }


# ---------------------------------------------------------------------------
# Descriptor — consumed by ``register_server_tools`` (task 12.1)
# ---------------------------------------------------------------------------

TOOL_DESCRIPTOR: ToolDescriptor = ToolDescriptor(
    name="suggest_workout",
    description=(
        "Gợi ý 2-8 bài tập wger phù hợp với muscle_group, duration_min, "
        "equipment và level. Tôn trọng ràng buộc "
        "sum(ex.duration_minutes) ≤ duration_min và tự hạ level một nấc "
        "khi user_state.fatigue_level ∈ {high, very_high}."
    ),
    parameters_schema=_SUGGEST_WORKOUT_SCHEMA,
    side="server",
    fn=suggest_workout,
    idempotent=True,
)


__all__ = [
    "TOOL_DESCRIPTOR",
    "suggest_workout",
]
