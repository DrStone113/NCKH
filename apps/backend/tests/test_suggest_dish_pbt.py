"""
Property-based tests for ``services.agent.tools.dish.suggest_dish``.

Task 4.3 — **Property 8: Suggest_dish bounds**
**Validates: Requirements 4.1**

Universal property exercised with ``hypothesis``:

- For every randomly drawn ``(meal_type, target_kcal, dietary_restrictions)``
  triple — with ``target_kcal ∈ [50, 5000]``, ``meal_type`` from
  ``{breakfast, lunch, dinner, snack}`` and ``dietary_restrictions`` a random
  subset of ``{vegetarian, vegan, low_carb, high_protein, no_seafood}`` —
  if ``suggest_dish`` returns a dish, then
  ``0.7 * target_kcal ≤ result.total_calories ≤ 1.5 * target_kcal`` and every
  ``component.serving_grams ≥ 1``.

Because the catalog is finite, some restriction combinations admit no dish
that fits the calorie window; in those cases ``suggest_dish`` raises
``ValueError("NO_DISH_FOUND")`` and we ``assume(False)`` so Hypothesis treats
the example as a "no candidate" filter rather than a failing assertion.
This encodes the contract from
``backend/.kiro/specs/chatbot-redesign/design.md`` §9.4 and Requirement 4.1
in ``requirements.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

# Allow ``import services.agent.tools.dish`` when pytest is run from the
# ``backend/`` directory (matches the convention used in other backend tests).
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tools.dish import suggest_dish  # noqa: E402


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
_RESTRICTIONS = (
    "vegetarian",
    "vegan",
    "low_carb",
    "high_protein",
    "no_seafood",
)

_meal_type_strategy = st.sampled_from(_MEAL_TYPES)

# ``target_kcal`` ∈ [50, 5000] per task spec; ``allow_nan/infinity=False``
# guards the floats so we never feed the tool a value it would have to reject
# on input-domain grounds (which is a separate property already tested in
# unit tests).
_target_kcal_strategy = st.floats(
    min_value=50.0,
    max_value=5000.0,
    allow_nan=False,
    allow_infinity=False,
)

# A random subset of the allowed dietary restriction tags. ``unique=True``
# keeps the list a true subset (no duplicates), and ``max_size`` matches the
# size of the universe so any subset is reachable.
_restrictions_strategy = st.lists(
    st.sampled_from(_RESTRICTIONS),
    unique=True,
    min_size=0,
    max_size=len(_RESTRICTIONS),
)


# ---------------------------------------------------------------------------
# Property 8 — suggest_dish bounds
# ---------------------------------------------------------------------------


@given(
    meal_type=_meal_type_strategy,
    target_kcal=_target_kcal_strategy,
    dietary_restrictions=_restrictions_strategy,
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_suggest_dish_respects_calorie_window_and_min_serving(
    meal_type: str,
    target_kcal: float,
    dietary_restrictions: list[str],
) -> None:
    """``suggest_dish`` always returns a dish whose totals fit the window.

    Specifically, whenever the tool produces a result it must satisfy:

    - ``0.7 * target_kcal ≤ result["total_calories"] ≤ 1.5 * target_kcal``
    - ``component["serving_grams"] >= 1`` for every component.

    When the catalog has no candidate for the drawn parameters the tool
    raises ``ValueError("NO_DISH_FOUND")``; we ``assume(False)`` so
    Hypothesis discards the example without counting it as a failure.
    """
    try:
        result = suggest_dish(
            meal_type=meal_type,
            target_kcal=target_kcal,
            dietary_restrictions=dietary_restrictions,
        )
    except ValueError as exc:
        # Only ``NO_DISH_FOUND`` is an acceptable filter outcome; any other
        # ``ValueError`` (e.g. INVALID_*) would mean the strategy generated
        # an out-of-domain input, which we want to surface, not hide.
        if str(exc) == "NO_DISH_FOUND":
            assume(False)
        raise

    lower = 0.7 * target_kcal
    upper = 1.5 * target_kcal

    total_calories = result["total_calories"]
    assert lower <= total_calories <= upper, (
        f"total_calories={total_calories} not in "
        f"[{lower}, {upper}] for target_kcal={target_kcal}, "
        f"meal_type={meal_type}, dietary_restrictions={dietary_restrictions}"
    )

    components = result["components"]
    assert components, "suggest_dish must return at least one component"
    for component in components:
        serving_grams = component["serving_grams"]
        assert isinstance(serving_grams, int), (
            f"serving_grams must be int, got {type(serving_grams).__name__}"
        )
        assert serving_grams >= 1, (
            f"component {component['name']!r} has serving_grams="
            f"{serving_grams} < 1"
        )
