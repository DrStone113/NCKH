"""
Property-based tests for ``suggest_workout``.

Task 4.5 — **Property 9: Suggest_workout bounds**
**Validates: Requirements 4.2**

Requirement 4.2 (``backend/.kiro/specs/chatbot-redesign/requirements.md``):

    WHEN ``suggest_workout`` được gọi với ``duration_min ∈ [10, 120]``,
    THE Suggest_Workout_Tool SHALL trả ``WorkoutPlan`` có
    ``2 ≤ len(plan.exercises) ≤ 8`` và
    ``sum(ex.duration_minutes for ex in plan.exercises) ≤ duration_min``.

Strategy
--------
We sample ``duration_min`` uniformly from the spec window ``[10, 120]`` and
``muscle_group`` / ``equipment`` / ``level`` uniformly from the tool's own
declared valid sets (``_VALID_MUSCLE_GROUPS``, ``_VALID_EQUIPMENT``,
``_VALID_LEVELS``). Some combinations of muscle group, equipment, and level
have fewer than two candidate exercises in ``data/wger_exercises_raw.json``;
the tool raises ``ValueError("NO_EXERCISES_FOUND")`` for those, and we use
``hypothesis.assume(False)`` to skip them. All other ``ValueError`` codes
remain failures — only the documented "no candidates" case is skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Allow ``import services.agent.tools.workout`` when pytest is run from the
# ``backend/`` directory (matches the convention used by sibling tests).
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tools.workout import (  # noqa: E402
    _VALID_EQUIPMENT,
    _VALID_LEVELS,
    _VALID_MUSCLE_GROUPS,
    suggest_workout,
)


# ---------------------------------------------------------------------------
# Hypothesis strategies — constrained to the input space declared by the tool
# ---------------------------------------------------------------------------

_muscle_group_strategy = st.sampled_from(sorted(_VALID_MUSCLE_GROUPS))
_equipment_strategy = st.sampled_from(sorted(_VALID_EQUIPMENT))
_level_strategy = st.sampled_from(sorted(_VALID_LEVELS))
_duration_strategy = st.integers(min_value=10, max_value=120)


# ---------------------------------------------------------------------------
# Property 9 — bounds on the returned plan
# ---------------------------------------------------------------------------


@given(
    duration_min=_duration_strategy,
    muscle_group=_muscle_group_strategy,
    equipment=_equipment_strategy,
    level=_level_strategy,
)
@settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_suggest_workout_bounds(
    duration_min: int,
    muscle_group: str,
    equipment: str,
    level: str,
) -> None:
    """``suggest_workout`` always honours the count and duration budget.

    Validates Requirements 4.2: the returned ``WorkoutPlan`` must have
    ``2 ≤ len(plan.exercises) ≤ 8`` and
    ``sum(ex.duration_minutes) ≤ duration_min``.
    """
    try:
        plan: dict[str, Any] = suggest_workout(
            muscle_group=muscle_group,
            duration_min=duration_min,
            equipment=equipment,
            level=level,
        )
    except ValueError as exc:
        # Some muscle_group × equipment × level combinations legitimately have
        # fewer than two candidate exercises in the dataset. Skip those — any
        # other ValueError code (e.g. INVALID_DURATION) is a real failure.
        if str(exc) == "NO_EXERCISES_FOUND":
            assume(False)
        raise

    exercises = plan["exercises"]

    # Count bounds (Requirement 4.2).
    assert 2 <= len(exercises) <= 8, (
        f"expected 2..8 exercises, got {len(exercises)} "
        f"for ({muscle_group=}, {equipment=}, {level=}, {duration_min=})"
    )

    # Duration budget (Requirement 4.2).
    total = sum(int(ex["duration_minutes"]) for ex in exercises)
    assert total <= duration_min, (
        f"sum(duration_minutes)={total} exceeds duration_min={duration_min} "
        f"for ({muscle_group=}, {equipment=}, {level=})"
    )

    # Sanity: each exercise reports a positive duration so the sum is meaningful.
    for ex in exercises:
        assert int(ex["duration_minutes"]) > 0
