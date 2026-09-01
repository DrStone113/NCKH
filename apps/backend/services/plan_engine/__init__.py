"""P1 versioned plan engine.

The package is deliberately separate from legacy ``plans``/``plan_items`` so
shadow evaluation cannot alter historical plan records or observation data.
"""

from .contracts import (
    ContextState,
    PlanDomain,
    PlanItem,
    PlanLifecycleStatus,
    PlanPatch,
    PlanPatchOperation,
    PlanRequest,
    PlanRevision,
)
from .engine import GLOBAL_PLAN_REPOSITORY, MemoryPlanRepository, PlanContextResolver, PlanEngine, PlanValidator
from .comparator import ComparatorVerdict, PlanV2Comparator
from .nutrition_horizon import NutritionPlanningHorizonState
from .persistence import PlanSqlRepository
from .weekly_scheduler import PlanningHorizonState, WeeklyWorkoutScheduler

__all__ = [
    "ContextState",
    "GLOBAL_PLAN_REPOSITORY",
    "MemoryPlanRepository",
    "PlanContextResolver",
    "PlanDomain",
    "PlanEngine",
    "PlanItem",
    "PlanLifecycleStatus",
    "PlanPatch",
    "PlanPatchOperation",
    "PlanRequest",
    "PlanSqlRepository",
    "PlanV2Comparator",
    "PlanRevision",
    "PlanValidator",
    "PlanningHorizonState",
    "NutritionPlanningHorizonState",
    "ComparatorVerdict",
    "WeeklyWorkoutScheduler",
]
