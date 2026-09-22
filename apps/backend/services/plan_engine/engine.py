"""Deterministic, versioned Plan Engine used by the P1 tool surface.

The engine is intentionally a coordinator: canonical nutrition calculation and
the E4 workout planner remain authoritative in their respective modules.  It
never writes an observation (meal consumption or workout completion).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import date
from threading import RLock
from typing import Any, Iterable
from unicodedata import normalize as unicode_normalize
from uuid import NAMESPACE_URL, uuid5

from models.schemas import UserProfile
from services.nutrition.registry import POLICY_VERSION

from .contracts import (
    ContextState,
    ContextValue,
    PlanDomain,
    PlanItem,
    PlanItemStatus,
    PlanItemType,
    PlanLifecycleStatus,
    PlanPatch,
    PlanPatchOperation,
    PlanRequest,
    PlanRevision,
    PlanValidationIssue,
    PlanValidationResult,
    PlanValidationStatus,
    content_hash,
    new_plan_id,
    new_revision_id,
)
from .lifecycle import transition_allowed
from .nutrition_horizon import NutritionPlanningHorizonState, variety_score
from .request_normalization import partition_nutrition_exclusions


_MEAL_SPLIT: tuple[tuple[str, float], ...] = (
    ("breakfast", 0.28),
    ("lunch", 0.38),
    ("dinner", 0.34),
)
_ALLERGY_TO_RESTRICTION = {
    "CRUSTACEAN": "no_crustacean", "MOLLUSC": "no_mollusc", "FISH": "no_fish",
    "EGG": "no_egg", "MILK": "no_milk", "PEANUT": "no_peanut",
    "TREE_NUT": "no_tree_nut", "SOY": "no_soy", "WHEAT_GLUTEN": "no_wheat_gluten",
    "SESAME": "no_sesame",
}
_RESTRICTION_ALLERGEN = {value: key for key, value in _ALLERGY_TO_RESTRICTION.items()}


@dataclass(frozen=True, slots=True)
class PlanContext:
    owner_user_id: str
    profile: ContextValue
    nutrition_state: ContextValue
    training_state: ContextValue
    consumed_meals: ContextValue
    active_nutrition_plan: ContextValue
    active_workout_plan: ContextValue
    dietary_constraints: ContextValue
    catalog_versions: dict[str, str]
    raw_context: dict[str, Any]


class PlanContextResolver:
    """Normalise only authoritative caller context and preserve availability."""

    @staticmethod
    def resolve(owner_user_id: str | None, raw: Any) -> PlanContext:
        context = dict(raw) if isinstance(raw, dict) else {}
        owner = str(owner_user_id or context.get("user_id") or context.get("id") or "anonymous")
        profile_payload = _profile_payload(context, owner)
        profile = (
            ContextValue.known(profile_payload, source="AUTHENTICATED_PROFILE_CONTEXT")
            if profile_payload is not None
            else ContextValue.unavailable(ContextState.MISSING, source="AUTHENTICATED_PROFILE_CONTEXT")
        )
        nutrition_profile = context.get("nutrition_profile") if isinstance(context.get("nutrition_profile"), dict) else {}
        raw_restrictions = (
            context.get("dietary_restrictions")
            or nutrition_profile.get("dietary_restrictions")
        )
        restrictions = _tuple_of_strings(raw_restrictions)
        raw_allergies = context.get("food_allergies") or nutrition_profile.get("food_allergies")
        allergies = _tuple_of_strings(raw_allergies)
        if allergies is not None:
            restrictions = tuple(dict.fromkeys((*(restrictions or ()), *(
                _ALLERGY_TO_RESTRICTION.get(item.upper(), item.lower()) for item in allergies
            ))))
        dietary = (
            ContextValue.known(restrictions, source="CONFIRMED_DIETARY_CONSTRAINTS")
            if restrictions is not None
            else ContextValue.unavailable(ContextState.MISSING, source="CONFIRMED_DIETARY_CONSTRAINTS")
        )
        return PlanContext(
            owner_user_id=owner,
            profile=profile,
            nutrition_state=ContextValue.unavailable(ContextState.NOT_LOADED, source="CANONICAL_NUTRITION"),
            training_state=ContextValue.unavailable(ContextState.NOT_LOADED, source="TRAINING_STATE"),
            consumed_meals=_stateful_value(context.get("today_meals"), "CONSUMED_MEAL_LOG"),
            active_nutrition_plan=_stateful_value(context.get("active_nutrition_plan"), "ACTIVE_NUTRITION_PLAN"),
            active_workout_plan=_stateful_value(context.get("active_workout_plan"), "ACTIVE_WORKOUT_PLAN"),
            dietary_constraints=dietary,
            catalog_versions={
                "food_catalog": "canonical-food-catalog-v1",
                "dish_catalog": "verified-dish-catalog-v1",
                "exercise_catalog": "canonical-exercise-catalog-v1",
            },
            raw_context=context,
        )


class PlanValidator:
    """P1 hard/soft checks.  It does not reinterpret domain-policy numbers."""

    def validate(self, revision: PlanRevision) -> PlanValidationResult:
        issues: list[PlanValidationIssue] = []
        if revision.domain not in {PlanDomain.NUTRITION, PlanDomain.WORKOUT, PlanDomain.COMBINED_HEALTH}:
            issues.append(PlanValidationIssue("UNKNOWN_PLAN_DOMAIN", "HARD"))
        if revision.lifecycle_status is PlanLifecycleStatus.ACTIVE and not revision.validation.ready:
            issues.append(PlanValidationIssue("INVALID_ACTIVE_TRANSITION", "HARD"))
        seen: set[str] = set()
        repeat_counter: dict[str, int] = defaultdict(int)
        for item in revision.items:
            if item.plan_item_id in seen:
                issues.append(PlanValidationIssue("DUPLICATE_PLAN_ITEM_ID", "HARD", item.plan_item_id))
            seen.add(item.plan_item_id)
            if not (revision.request.period_start <= item.scheduled_date <= revision.request.period_end):
                issues.append(PlanValidationIssue("ITEM_OUTSIDE_EFFECTIVE_PERIOD", "HARD", item.plan_item_id))
            if item.status is not PlanItemStatus.PLANNED and item.status is not PlanItemStatus.CANCELLED:
                issues.append(PlanValidationIssue("INVALID_PLAN_ITEM_STATUS", "HARD", item.plan_item_id))
            if item.item_type is PlanItemType.MEAL:
                if not isinstance(item.canonical_refs.get("dish_id"), str):
                    issues.append(PlanValidationIssue("MISSING_CANONICAL_DISH_REFERENCE", "HARD", item.plan_item_id))
                food_ids = item.canonical_refs.get("food_ids")
                if (
                    not isinstance(food_ids, list)
                    or not food_ids
                    or any(not isinstance(food_id, str) or not food_id for food_id in food_ids)
                ):
                    issues.append(PlanValidationIssue("MISSING_CANONICAL_FOOD_REFERENCE", "HARD", item.plan_item_id))
                repeat_counter[str(item.canonical_refs.get("dish_id"))] += 1
                for restriction in revision.constraint_snapshot.get("dietary_restrictions", []):
                    if _meal_violates_restriction(item, str(restriction)):
                        issues.append(PlanValidationIssue("HARD_DIETARY_CONSTRAINT_VIOLATION", "HARD", item.plan_item_id))
                for exclusion in revision.constraint_snapshot.get("ingredient_exclusions", []):
                    if _meal_violates_ingredient_exclusion(item, str(exclusion)):
                        issues.append(PlanValidationIssue("HARD_INGREDIENT_EXCLUSION_VIOLATION", "HARD", item.plan_item_id))
            if item.item_type is PlanItemType.WORKOUT_SESSION:
                ids = item.canonical_refs.get("exercise_ids")
                if not isinstance(ids, list) or not ids:
                    issues.append(PlanValidationIssue("MISSING_CANONICAL_EXERCISE_REFERENCE", "HARD", item.plan_item_id))
                presentation = item.content.get("e4_presentation")
                if not isinstance(presentation, dict) or not isinstance(presentation.get("exercises"), list):
                    issues.append(PlanValidationIssue("E4_SESSION_OUTPUT_REQUIRED", "HARD", item.plan_item_id))
                elif "E4_AUTHORITATIVE_PLAN" not in item.reason_codes:
                    issues.append(PlanValidationIssue("E4_DELEGATION_PROVENANCE_MISSING", "HARD", item.plan_item_id))
                planned_duration = item.content.get("planned_duration_minutes")
                if planned_duration is not None and (
                    not isinstance(planned_duration, (int, float)) or planned_duration <= 0
                ):
                    issues.append(PlanValidationIssue("INVALID_WORKOUT_DURATION", "HARD", item.plan_item_id))
            # Planned records must never carry observational completion values,
            # including values nested inside a delegated presentation payload.
            if _contains_observational_key(item.content):
                issues.append(PlanValidationIssue("PLANNED_TO_ACTUAL_LEAKAGE", "HARD", item.plan_item_id))
        if any(count > 3 for count in repeat_counter.values()):
            issues.append(PlanValidationIssue("LOW_VARIETY_REPETITION", "SOFT"))
        hard = any(issue.severity == "HARD" for issue in issues)
        return PlanValidationResult(
            PlanValidationStatus.INVALID if hard else PlanValidationStatus.READY,
            tuple(issues),
        )


class MemoryPlanRepository:
    """Thread-local development repository with revision/idempotency semantics.

    Shadow mode deliberately uses this repository, so it cannot alter legacy
    PostgreSQL plans or observations.  The same content hash and optimistic
    checks are used by the SQL repository migration when enforcement is enabled.
    """

    def __init__(self) -> None:
        self._revisions: dict[str, PlanRevision] = {}
        self._by_plan: dict[str, list[str]] = defaultdict(list)
        self._idempotency: dict[tuple[str, str], str] = {}
        self._lock = RLock()

    def put(self, revision: PlanRevision) -> PlanRevision:
        with self._lock:
            self._revisions[revision.revision_id] = revision
            if revision.revision_id not in self._by_plan[revision.plan_id]:
                self._by_plan[revision.plan_id].append(revision.revision_id)
        return revision

    def get(self, owner_user_id: str, plan_id: str, revision_id: str | None = None) -> PlanRevision | None:
        with self._lock:
            target = self._revisions.get(revision_id) if revision_id else None
            if target is None and revision_id is None:
                candidates = [self._revisions[key] for key in self._by_plan.get(plan_id, ())]
                target = max(candidates, key=lambda item: item.revision_number, default=None)
            if target is None or target.owner_user_id != owner_user_id or target.plan_id != plan_id:
                return None
            return target

    def get_active(
        self, owner_user_id: str, domain: PlanDomain, *, local_date: date | None = None
    ) -> PlanRevision | None:
        """Read the authoritative active revision without regenerating it."""

        with self._lock:
            active = [
                revision
                for revision in self._revisions.values()
                if revision.owner_user_id == owner_user_id
                and revision.domain is domain
                and revision.lifecycle_status is PlanLifecycleStatus.ACTIVE
                and (local_date is None or revision.request.period_start <= local_date <= revision.request.period_end)
            ]
            return max(active, key=lambda item: (item.request.period_start, item.revision_number), default=None)

    def save(
        self,
        *,
        owner_user_id: str,
        plan_id: str,
        revision_id: str,
        expected_content_hash: str,
        request_id: str,
        activate: bool,
    ) -> PlanRevision:
        with self._lock:
            cached = self._idempotency.get((owner_user_id, request_id))
            if cached is not None:
                result = self._revisions[cached]
                if result.revision_id != revision_id:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
                return result
            revision = self.get(owner_user_id, plan_id, revision_id)
            if revision is None:
                raise ValueError("PLAN_NOT_FOUND")
            if revision.revision_content_hash != expected_content_hash:
                raise ValueError("PLAN_CONTENT_HASH_MISMATCH")
            if not revision.validation.ready:
                raise ValueError("PLAN_NOT_READY")
            if revision.lifecycle_status not in {PlanLifecycleStatus.DRAFT, PlanLifecycleStatus.PENDING_CONFIRMATION}:
                raise ValueError("INVALID_PLAN_SAVE_TRANSITION")
            lifecycle = PlanLifecycleStatus.ACTIVE if activate else PlanLifecycleStatus.SAVED
            saved = replace(revision, lifecycle_status=lifecycle)
            if activate:
                for existing in tuple(self._revisions.values()):
                    if (
                        existing.owner_user_id == owner_user_id
                        and existing.domain is saved.domain
                        and existing.lifecycle_status is PlanLifecycleStatus.ACTIVE
                        and existing.revision_id != saved.revision_id
                        and _periods_overlap(existing.request, saved.request)
                    ):
                        self._revisions[existing.revision_id] = replace(
                            existing, lifecycle_status=PlanLifecycleStatus.SUPERSEDED
                        )
            self.put(saved)
            self._idempotency[(owner_user_id, request_id)] = saved.revision_id
            return saved

    def set_status(
        self,
        *,
        owner_user_id: str,
        plan_id: str,
        revision_id: str,
        expected_revision_number: int,
        status: PlanLifecycleStatus,
        request_id: str,
    ) -> PlanRevision:
        """Apply an explicit lifecycle command to the exact current revision."""

        with self._lock:
            cached = self._idempotency.get((owner_user_id, request_id))
            if cached is not None:
                result = self._revisions[cached]
                if result.revision_id != revision_id:
                    raise ValueError("IDEMPOTENCY_KEY_REUSED_FOR_DIFFERENT_REVISION")
                return result
            revision = self.get(owner_user_id, plan_id, revision_id)
            if revision is None:
                raise ValueError("PLAN_NOT_FOUND")
            if revision.revision_number != expected_revision_number:
                raise ValueError("PLAN_REVISION_CONFLICT")
            if not transition_allowed(revision.lifecycle_status, status):
                raise ValueError("INVALID_PLAN_LIFECYCLE_TRANSITION")
            if status is PlanLifecycleStatus.ACTIVE and not revision.validation.ready:
                raise ValueError("PLAN_NOT_READY")
            updated = replace(revision, lifecycle_status=status)
            if status is PlanLifecycleStatus.ACTIVE:
                for existing in tuple(self._revisions.values()):
                    if (
                        existing.owner_user_id == owner_user_id
                        and existing.domain is updated.domain
                        and existing.lifecycle_status is PlanLifecycleStatus.ACTIVE
                        and existing.revision_id != updated.revision_id
                        and _periods_overlap(existing.request, updated.request)
                    ):
                        self._revisions[existing.revision_id] = replace(existing, lifecycle_status=PlanLifecycleStatus.SUPERSEDED)
            self.put(updated)
            self._idempotency[(owner_user_id, request_id)] = updated.revision_id
            return updated


GLOBAL_PLAN_REPOSITORY = MemoryPlanRepository()


class PlanEngine:
    def __init__(self, repository: MemoryPlanRepository | None = None) -> None:
        self.repository = repository or GLOBAL_PLAN_REPOSITORY
        self.validator = PlanValidator()

    def build_nutrition_plan(self, context: PlanContext, request: PlanRequest) -> PlanRevision:
        if request.domain is not PlanDomain.NUTRITION:
            raise ValueError("PLAN_DOMAIN_MISMATCH")
        # Deferred imports avoid a package-initialisation cycle: the tool
        # catalog imports Plan V2 descriptors, while the engine delegates only
        # at execution time to the existing canonical nutrition adapters.
        from services.agent.tools.dish import suggest_dish
        from services.agent.tools.tdee import calculate_tdee
        if context.profile.state is not ContextState.KNOWN or not isinstance(context.profile.value, dict):
            return self._clarification_revision(context, request, "NUTRITION_PROFILE_MISSING")
        profile_data = dict(context.profile.value)
        if request.goal_override is not None:
            profile_data["health_goal"] = request.goal_override
        try:
            canonical = calculate_tdee(UserProfile.model_validate(profile_data))
        except Exception:
            return self._clarification_revision(context, request, "CANONICAL_NUTRITION_INPUT_UNAVAILABLE")
        if canonical.get("status") != "READY" or not isinstance(canonical.get("daily_kcal"), (int, float)):
            return self._specialist_or_clarification_revision(context, request, canonical)
        confirmed_constraints = tuple(context.dietary_constraints.value or ()) if context.dietary_constraints.state is ContextState.KNOWN else ()
        restrictions, ingredient_exclusions = partition_nutrition_exclusions(
            (*confirmed_constraints, *request.temporary_exclusions)
        )
        items: list[PlanItem] = []
        recent_dishes: deque[int] = deque(maxlen=12)
        for offset in range(request.duration_days):
            plan_date = request.period_start.fromordinal(request.period_start.toordinal() + offset)
            for meal_type, ratio in _MEAL_SPLIT:
                dish = suggest_dish(
                    meal_type=meal_type,
                    target_kcal=float(canonical["daily_kcal"]) * ratio,
                    dietary_restrictions=restrictions,
                    ingredient_exclusions=ingredient_exclusions,
                    recent_dish_ids=tuple(recent_dishes),
                )
                dish_id = int(dish["id"])
                recent_dishes.append(dish_id)
                item_id = str(uuid5(NAMESPACE_URL, f"p1:{context.owner_user_id}:{request.period_start}:{offset}:{meal_type}:{dish_id}"))
                items.append(
                    PlanItem(
                        plan_item_id=item_id,
                        scheduled_date=plan_date,
                        schedule_slot=meal_type,
                        item_type=PlanItemType.MEAL,
                        canonical_refs={"dish_id": str(dish_id), "food_ids": [str(c.get("food_id") or "") for c in dish.get("components", [])]},
                        reason_codes=("NUTRITION_GOAL_MATCH", "DIETARY_CONSTRAINT_MATCH", "VARIETY_TARGET"),
                        policy_provenance=(POLICY_VERSION, *tuple(canonical.get("formula_ids") or ())),
                        content={
                            "dish_name": dish["name"],
                            "components": dish["components"],
                            "total_calories": dish["total_calories"],
                            "total_protein": dish["total_protein"],
                            "total_carbs": dish["total_carbs"],
                            "total_fat": dish["total_fat"],
                            "allergen_ids": dish.get("allergen_ids", []),
                            "dietary_tags": dish.get("dietary_tags", {}),
                        },
                    )
                )
        nutrition_horizon = NutritionPlanningHorizonState.empty(context.consumed_meals)
        for item in items:
            nutrition_horizon = nutrition_horizon.add_planned_meal(item)
        revision = PlanRevision(
            plan_id=new_plan_id(), domain=PlanDomain.NUTRITION, revision_id=new_revision_id(), revision_number=1,
            parent_revision_id=None, owner_user_id=context.owner_user_id, request=request,
            lifecycle_status=PlanLifecycleStatus.DRAFT,
            validation=PlanValidationResult(PlanValidationStatus.READY),
            policy_versions={"nutrition": POLICY_VERSION}, catalog_versions={key: value for key, value in context.catalog_versions.items() if key != "exercise_catalog"},
            goal_snapshot={"health_goal": profile_data.get("health_goal"), "canonical_daily_kcal": canonical.get("daily_kcal"), "canonical_daily_protein": canonical.get("daily_protein")},
            constraint_snapshot={"dietary_restrictions": list(restrictions), "ingredient_exclusions": list(ingredient_exclusions)}, items=tuple(items),
            summary={**_nutrition_summary(items), "variety": variety_score(items)},
            explanation_metadata={"reason_codes": ["NUTRITION_GOAL_MATCH", "DIETARY_CONSTRAINT_MATCH", "INGREDIENT_EXCLUSION_MATCH", "VARIETY_TARGET", "SOFT_PLANNING_TARGET"]},
            provenance={
                "generator": "P2_NUTRITION_DELEGATE", "canonical_nutrition_status": canonical.get("status"),
                "planning_horizon": nutrition_horizon.to_dict(), "planned_not_consumed": True,
            },
        )
        validated = replace(revision, validation=self.validator.validate(revision))
        self.repository.put(validated)
        return validated

    def build_workout_revision(
        self,
        context: PlanContext,
        request: PlanRequest,
        *,
        e4_payload: dict[str, Any] | None = None,
        schedule_dates: tuple[date, ...] = (),
        e4_sessions: tuple[tuple[date, dict[str, Any], tuple[str, ...]], ...] = (),
    ) -> PlanRevision:
        """Wrap one E4 result per scheduled session without prescribing it.

        P2 accepts a separately generated E4 payload for every slot.  It is
        intentionally not a second prescription engine: the only cross-day
        decision retained here is calendar provenance from the scheduler.
        """

        if request.domain is not PlanDomain.WORKOUT:
            raise ValueError("PLAN_DOMAIN_MISMATCH")
        sessions = e4_sessions or tuple(
            (scheduled, e4_payload or {}, ("E4_PER_SESSION_DELEGATION_REQUIRED",))
            for scheduled in schedule_dates
        )
        if not sessions:
            return self._clarification_revision(context, request, "E4_WEEKLY_SCHEDULE_CAPABILITY_REQUIRED")
        items: list[PlanItem] = []
        policy_versions: set[str] = set()
        catalog_versions: set[str] = set()
        e4_provenance: list[dict[str, Any]] = []
        for scheduled, payload, schedule_provenance in sessions:
            presentation = payload.get("presentation") if isinstance(payload, dict) else None
            e4_plan_id = payload.get("plan_id") if isinstance(payload, dict) else None
            if not isinstance(payload, dict) or payload.get("status") != "READY":
                return self._clarification_revision(
                    context, request, str(payload.get("status") if isinstance(payload, dict) else "E4_PLAN_UNAVAILABLE")
                )
            if not isinstance(presentation, dict) or not isinstance(e4_plan_id, str):
                return self._clarification_revision(
                    context, request, str(payload.get("status") if isinstance(payload, dict) else "E4_PLAN_UNAVAILABLE")
                )
            exercises = presentation.get("exercises")
            if not isinstance(exercises, list) or not exercises:
                return self._clarification_revision(context, request, "E4_CANONICAL_EXERCISES_MISSING")
            exercise_ids = [
                str(item.get("canonical_exercise_id"))
                for item in exercises
                if isinstance(item, dict) and isinstance(item.get("canonical_exercise_id"), str)
            ]
            if not exercise_ids:
                return self._clarification_revision(context, request, "E4_CANONICAL_EXERCISES_MISSING")
            duration = presentation.get("estimated_duration_minutes")
            policy = presentation.get("exercise_policy_version")
            catalog = presentation.get("catalog_version")
            if isinstance(policy, str):
                policy_versions.add(policy)
            if isinstance(catalog, str):
                catalog_versions.add(catalog)
            items.append(
                PlanItem(
                    plan_item_id=str(uuid5(NAMESPACE_URL, f"p2-workout:{context.owner_user_id}:{e4_plan_id}:{scheduled}")),
                    scheduled_date=scheduled, schedule_slot="workout", item_type=PlanItemType.WORKOUT_SESSION,
                    canonical_refs={"e4_workout_plan_id": e4_plan_id, "exercise_ids": exercise_ids},
                    reason_codes=("WORKOUT_GOAL_MATCH", "TIME_BUDGET", "E4_AUTHORITATIVE_PLAN", *schedule_provenance),
                    policy_provenance=tuple(
                        str(value)
                        for value in (payload.get("integration_version"), policy, catalog)
                        if isinstance(value, str)
                    ),
                    content={
                        "e4_presentation": presentation,
                        "planned_duration_minutes": duration if isinstance(duration, (int, float)) else None,
                        "schedule_provenance": list(schedule_provenance),
                    },
                )
            )
            e4_provenance.append({
                "plan_id": e4_plan_id, "status": payload.get("status"),
                "validation": payload.get("validation"), "scheduled_date": scheduled.isoformat(),
            })
        revision = PlanRevision(
            plan_id=new_plan_id(), domain=PlanDomain.WORKOUT, revision_id=new_revision_id(), revision_number=1,
            parent_revision_id=None, owner_user_id=context.owner_user_id, request=request,
            lifecycle_status=PlanLifecycleStatus.DRAFT, validation=PlanValidationResult(PlanValidationStatus.READY),
            policy_versions={"exercise": ",".join(sorted(policy_versions)) or "unknown"},
            catalog_versions={"exercise_catalog": ",".join(sorted(catalog_versions)) or context.catalog_versions["exercise_catalog"]},
            goal_snapshot={"goal": request.goal_override, "e4_session_count": len(items)},
            constraint_snapshot={"schedule_dates": [item.scheduled_date.isoformat() for item in items]},
            items=tuple(items), summary={"session_count": len(items), "planned_not_completed": True},
            explanation_metadata={"reason_codes": ["WORKOUT_GOAL_MATCH", "TIME_BUDGET", "E4_AUTHORITATIVE_PLAN"]},
            provenance={
                "generator": "P2_WEEKLY_E4_WORKOUT_DELEGATE", "e4_sessions": e4_provenance,
                "planned_not_completed": True, "planned_not_actual": True,
            },
        )
        validated = replace(revision, validation=self.validator.validate(revision))
        self.repository.put(validated)
        return validated

    def build_combined_container(
        self, context: PlanContext, request: PlanRequest, child_revisions: tuple[PlanRevision, ...]
    ) -> PlanRevision:
        """Create one canonical combined revision from domain components.

        Older callers still pass child revisions, but the returned revision now
        owns the actual meal/workout item snapshots.  The child references are
        retained only as provenance, never as a second mutable source.
        """

        if request.domain is not PlanDomain.COMBINED_HEALTH:
            raise ValueError("PLAN_DOMAIN_MISMATCH")
        if not child_revisions or any(item.domain is PlanDomain.COMBINED_HEALTH for item in child_revisions):
            return self._clarification_revision(context, request, "COMBINED_CHILD_PLAN_MISSING")
        items = tuple(item for child in child_revisions for item in child.items)
        if not items:
            return self._clarification_revision(context, request, "COMBINED_ITEMS_MISSING")
        policy_versions = {
            key: value
            for child in child_revisions
            for key, value in child.policy_versions.items()
        }
        catalog_versions = {
            key: value
            for child in child_revisions
            for key, value in child.catalog_versions.items()
        }
        revision = PlanRevision(
            plan_id=new_plan_id(), domain=PlanDomain.COMBINED_HEALTH, revision_id=new_revision_id(), revision_number=1,
            parent_revision_id=None, owner_user_id=context.owner_user_id, request=request,
            lifecycle_status=PlanLifecycleStatus.DRAFT, validation=PlanValidationResult(PlanValidationStatus.READY),
            policy_versions=policy_versions, catalog_versions=catalog_versions,
            goal_snapshot={"goal": request.goal_override},
            constraint_snapshot={"domains": [child.domain.value for child in child_revisions]},
            items=items,
            summary={
                "child_plan_count": len(child_revisions),
                "meal_item_count": sum(item.item_type is PlanItemType.MEAL for item in items),
                "workout_item_count": sum(item.item_type is PlanItemType.WORKOUT_SESSION for item in items),
                "planned_not_consumed_or_completed": True,
            },
            explanation_metadata={"reason_codes": ["COMBINED_PLAN_CANONICAL_ITEMS"]},
            provenance={
                "generator": "P2_COMBINED_PLAN_ORCHESTRATOR",
                "child_revisions": [
                    {"domain": child.domain.value, "plan_id": child.plan_id, "revision_id": child.revision_id, "content_hash": child.revision_content_hash}
                    for child in child_revisions
                ],
                "canonical_item_owner": "COMBINED_REVISION",
                "no_cross_domain_energy_compensation": True,
            },
        )
        validated = replace(revision, validation=self.validator.validate(revision))
        self.repository.put(validated)
        return validated

    def revise(self, context: PlanContext, patch: PlanPatch) -> PlanRevision:
        current = self.repository.get(context.owner_user_id, patch.target_plan_id, patch.target_revision_id)
        if current is None:
            raise ValueError("PLAN_NOT_FOUND")
        latest = self.repository.get(context.owner_user_id, patch.target_plan_id)
        if latest is None or latest.revision_id != current.revision_id:
            raise ValueError("PLAN_REVISION_CONFLICT")
        if current.revision_number != patch.expected_revision_number:
            raise ValueError("PLAN_REVISION_CONFLICT")
        if current.lifecycle_status not in {PlanLifecycleStatus.DRAFT, PlanLifecycleStatus.SAVED, PlanLifecycleStatus.ACTIVE, PlanLifecycleStatus.PAUSED}:
            raise ValueError("PLAN_NOT_REVISIONABLE")
        items = list(current.items)
        index = next((i for i, item in enumerate(items) if item.plan_item_id == patch.target_item_id), None)
        request = current.request
        goal_snapshot = current.goal_snapshot
        constraint_snapshot = current.constraint_snapshot
        if patch.operation is PlanPatchOperation.ADD_ITEM:
            added = _patch_item_from_payload(patch.requested_change.get("item"))
            if any(item.plan_item_id == added.plan_item_id for item in items):
                raise ValueError("PLAN_ITEM_ID_CONFLICT")
            if not (current.request.period_start <= added.scheduled_date <= current.request.period_end):
                raise ValueError("INVALID_PLAN_PATCH")
            items.append(added)
        elif patch.operation is PlanPatchOperation.REMOVE_ITEM:
            if index is None:
                raise ValueError("PLAN_ITEM_NOT_FOUND")
            items[index] = replace(items[index], status=PlanItemStatus.CANCELLED)
        elif patch.operation is PlanPatchOperation.REPLACE_ITEM:
            if index is None:
                raise ValueError("PLAN_ITEM_NOT_FOUND")
            replacement = _patch_item_from_payload(
                patch.requested_change.get("item"), expected_item_id=items[index].plan_item_id
            )
            if not (current.request.period_start <= replacement.scheduled_date <= current.request.period_end):
                raise ValueError("INVALID_PLAN_PATCH")
            items[index] = replacement
        elif patch.operation is PlanPatchOperation.CHANGE_TIME:
            if index is None or not isinstance(patch.requested_change.get("schedule_slot"), str):
                raise ValueError("INVALID_PLAN_PATCH")
            items[index] = replace(items[index], schedule_slot=str(patch.requested_change["schedule_slot"]))
        elif patch.operation is PlanPatchOperation.MOVE_ITEM:
            scheduled = patch.requested_change.get("scheduled_date")
            try:
                moved_date = date.fromisoformat(str(scheduled))
            except ValueError as exc:
                raise ValueError("INVALID_PLAN_PATCH") from exc
            if index is None or not (current.request.period_start <= moved_date <= current.request.period_end):
                raise ValueError("INVALID_PLAN_PATCH")
            items[index] = replace(items[index], scheduled_date=moved_date)
        elif patch.operation is PlanPatchOperation.CHANGE_DURATION:
            if index is None or not isinstance(patch.requested_change.get("duration_minutes"), int):
                raise ValueError("INVALID_PLAN_PATCH")
            content = {**items[index].content, "planned_duration_minutes": patch.requested_change["duration_minutes"]}
            items[index] = replace(items[index], content=content)
        elif patch.operation is PlanPatchOperation.CHANGE_GOAL:
            goal = patch.requested_change.get("goal_override")
            if goal is not None and (not isinstance(goal, str) or not goal.strip()):
                raise ValueError("INVALID_PLAN_PATCH")
            request = replace(current.request, goal_override=goal.strip() if isinstance(goal, str) else None)
            goal_snapshot = {**current.goal_snapshot, "user_requested_goal": request.goal_override}
        elif patch.operation is PlanPatchOperation.CHANGE_CONSTRAINT:
            def _strings(name: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
                value = patch.requested_change.get(name, fallback)
                if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) and item.strip() for item in value):
                    raise ValueError("INVALID_PLAN_PATCH")
                return tuple(dict.fromkeys(item.strip() for item in value))

            request = replace(
                current.request,
                schedule_constraints=_strings("schedule_constraints", current.request.schedule_constraints),
                temporary_preferences=_strings("temporary_preferences", current.request.temporary_preferences),
                temporary_exclusions=_strings("temporary_exclusions", current.request.temporary_exclusions),
            )
            constraint_snapshot = {
                **current.constraint_snapshot,
                "schedule_constraints": list(request.schedule_constraints),
                "temporary_preferences": list(request.temporary_preferences),
                "temporary_exclusions": list(request.temporary_exclusions),
            }
        else:
            # Replacing an item must be supplied by a domain resolver/UI using
            # canonical refs; plain prose never becomes an executable item.
            raise ValueError("PLAN_PATCH_OPERATION_REQUIRES_DOMAIN_RESOLUTION")
        draft = replace(
            current,
            revision_id=new_revision_id(), revision_number=current.revision_number + 1,
            parent_revision_id=current.revision_id, lifecycle_status=PlanLifecycleStatus.DRAFT,
            request=request, goal_snapshot=goal_snapshot, constraint_snapshot=constraint_snapshot,
            items=tuple(items),
            provenance={**current.provenance, "patch": {"operation": patch.operation.value, "reason": patch.reason, "source": patch.request_source}},
        )
        draft = replace(draft, validation=self.validator.validate(draft))
        self.repository.put(draft)
        return draft

    def mark_pending_confirmation(self, revision: PlanRevision) -> PlanRevision:
        if revision.lifecycle_status is not PlanLifecycleStatus.DRAFT:
            raise ValueError("INVALID_PENDING_TRANSITION")
        pending = replace(revision, lifecycle_status=PlanLifecycleStatus.PENDING_CONFIRMATION)
        self.repository.put(pending)
        return pending

    def save_exact_revision(
        self, context: PlanContext, *, plan_id: str, revision_id: str, content_hash_value: str, request_id: str, activate: bool = True
    ) -> PlanRevision:
        return self.repository.save(
            owner_user_id=context.owner_user_id, plan_id=plan_id, revision_id=revision_id,
            expected_content_hash=content_hash_value, request_id=request_id, activate=activate,
        )

    def _clarification_revision(self, context: PlanContext, request: PlanRequest, reason: str) -> PlanRevision:
        revision = PlanRevision(
            plan_id=new_plan_id(), domain=request.domain, revision_id=new_revision_id(), revision_number=1, parent_revision_id=None,
            owner_user_id=context.owner_user_id, request=request, lifecycle_status=PlanLifecycleStatus.DRAFT,
            validation=PlanValidationResult(PlanValidationStatus.CLARIFICATION_REQUIRED, (PlanValidationIssue(reason, "HARD"),)),
            policy_versions={"nutrition": POLICY_VERSION}, catalog_versions=context.catalog_versions, goal_snapshot={}, constraint_snapshot={}, items=(), summary={},
            explanation_metadata={"reason_codes": [reason]}, provenance={"generator": "P1_PLAN_ENGINE", "planned_not_consumed": True},
        )
        self.repository.put(revision)
        return revision

    def _specialist_or_clarification_revision(self, context: PlanContext, request: PlanRequest, canonical: dict[str, Any]) -> PlanRevision:
        status = PlanValidationStatus.REQUIRES_SPECIALIST_GUIDANCE if canonical.get("status") in {"UNSUPPORTED", "REQUIRES_SPECIALIST_GUIDANCE"} else PlanValidationStatus.CLARIFICATION_REQUIRED
        revision = self._clarification_revision(context, request, str(canonical.get("status") or "CANONICAL_NUTRITION_UNAVAILABLE"))
        revision = replace(revision, validation=PlanValidationResult(status, revision.validation.issues))
        self.repository.put(revision)
        return revision


def _patch_item_from_payload(value: Any, *, expected_item_id: str | None = None) -> PlanItem:
    """Accept only a fully typed, canonical PlanItem supplied by a domain UI.

    The application service never turns arbitrary assistant prose into a plan
    item.  Replacement keeps the logical item identity stable.
    """
    if not isinstance(value, dict):
        raise ValueError("INVALID_PLAN_PATCH")
    item_id = expected_item_id or value.get("plan_item_id")
    try:
        scheduled_date = date.fromisoformat(str(value["scheduled_date"]))
        item_type = PlanItemType(str(value["item_type"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("INVALID_PLAN_PATCH") from exc
    if not isinstance(item_id, str) or not item_id.strip():
        raise ValueError("INVALID_PLAN_PATCH")
    slot = value.get("schedule_slot")
    canonical_refs = value.get("canonical_refs")
    if not isinstance(slot, str) or not slot.strip() or not isinstance(canonical_refs, dict) or not canonical_refs:
        raise ValueError("INVALID_PLAN_PATCH")
    status = value.get("status", PlanItemStatus.PLANNED.value)
    try:
        return PlanItem(
            plan_item_id=item_id.strip(), scheduled_date=scheduled_date,
            schedule_slot=slot.strip(), item_type=item_type,
            canonical_refs=dict(canonical_refs), status=PlanItemStatus(str(status)),
            reason_codes=tuple(str(code) for code in value.get("reason_codes", ()) if str(code).strip()),
            policy_provenance=tuple(str(code) for code in value.get("policy_provenance", ()) if str(code).strip()),
            content=dict(value.get("content") or {}),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_PLAN_PATCH") from exc


def _stateful_value(value: Any, source: str) -> ContextValue:
    return ContextValue.known(value, source=source) if value is not None else ContextValue.unavailable(ContextState.NOT_LOADED, source=source)


def _tuple_of_strings(value: Any) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)):
        return None
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())


def _profile_payload(context: dict[str, Any], owner_user_id: str) -> dict[str, Any] | None:
    general = context.get("general_profile") if isinstance(context.get("general_profile"), dict) else {}
    nutrition = context.get("nutrition_profile") if isinstance(context.get("nutrition_profile"), dict) else {}
    # Intake V2 stores general/body values and nutrition values separately,
    # while historical clients still send a flat payload.  Merge only known
    # values; no missing field is substituted.
    source = {**context, **general, **nutrition}
    health_goal = source.get("health_goal", source.get("nutrition_goal"))
    if isinstance(health_goal, str):
        health_goal = {
            "LOSE_WEIGHT": "lose_weight", "MAINTAIN": "maintain", "GAIN_MUSCLE": "gain_muscle",
        }.get(health_goal.upper(), health_goal)
    activity = source.get("activity_level", source.get("activityLevel"))
    if isinstance(activity, str):
        activity = activity.lower()
    fields = {
        "user_id": owner_user_id,
        "age": source.get("age"),
        "equation_sex": source.get("equation_sex"),
        "height_cm": source.get("height_cm", source.get("height")),
        "weight_kg": source.get("weight_kg", source.get("weight")),
        "activity_level": activity,
        "health_goal": health_goal,
        "dietary_restrictions": source.get("dietary_restrictions", []),
        "nutrition_safety_profile": source.get("nutrition_safety_profile", {}),
    }
    required = ("age", "equation_sex", "height_cm", "weight_kg", "activity_level", "health_goal")
    return fields if all(fields[key] is not None for key in required) else None


def _meal_violates_restriction(item: PlanItem, restriction: str) -> bool:
    """Verify catalog facts retained by the nutrition delegate, not prose."""

    normalized = restriction.strip().lower()
    allergen_ids = {str(value).upper() for value in item.content.get("allergen_ids", [])}
    dietary_tags = item.content.get("dietary_tags")
    objective_tags = {
        str(value).lower()
        for value in (dietary_tags.get("objective", []) if isinstance(dietary_tags, dict) else [])
    }
    allergen = _RESTRICTION_ALLERGEN.get(normalized)
    if allergen is not None:
        return allergen in allergen_ids
    if normalized == "no_pork":
        return "contains_pork" in objective_tags
    if normalized == "no_beef":
        return "contains_beef" in objective_tags
    if normalized == "no_seafood":
        return bool({"contains_fish", "contains_crustacean", "contains_mollusc"} & objective_tags)
    if normalized == "vegetarian":
        return bool({"contains_pork", "contains_beef", "contains_fish", "contains_crustacean", "contains_mollusc"} & objective_tags)
    if normalized == "vegan":
        return bool({"contains_pork", "contains_beef", "contains_fish", "contains_crustacean", "contains_mollusc", "contains_egg", "contains_milk"} & objective_tags)
    # The canonical selector owns quantitative tags such as low_carb and
    # high_protein; it has already filtered before this immutable item exists.
    return False


def _meal_violates_ingredient_exclusion(item: PlanItem, exclusion: str) -> bool:
    """Verify a literal food exclusion against immutable dish component facts.

    Literal exclusions deliberately stay separate from policy-level dietary
    restrictions.  Comparing them here preserves the same accent-insensitive
    match rule used by the canonical dish selector without treating a food name
    as an unrelated policy enum.
    """

    needle = _normalized_food_text(exclusion)
    if not needle:
        return False
    values: list[Any] = [item.content.get("dish_name")]
    components = item.content.get("components")
    if isinstance(components, list):
        values.extend(component.get("name") for component in components if isinstance(component, dict))
    return any(needle in _normalized_food_text(value) for value in values if isinstance(value, str))


def _normalized_food_text(value: str) -> str:
    return " ".join(
        "".join(char for char in unicode_normalize("NFD", value).casefold() if char.isascii() and char.isalnum() or char == " ").split()
    )


def _contains_observational_key(value: Any) -> bool:
    """Reject actual-event fields at any depth of a planned revision."""

    observational = {
        "actual_reps", "actual_sets", "actual_load", "actual_rpe", "actual_rir",
        "consumed_at", "logged_at", "performed_at", "completed_at", "recovery_score",
        "fatigue_score", "actual_completion", "session_completion_status",
    }
    if isinstance(value, dict):
        return any(str(key).casefold() in observational or _contains_observational_key(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_observational_key(item) for item in value)
    return False


def _nutrition_summary(items: Iterable[PlanItem]) -> dict[str, Any]:
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0})
    for item in items:
        content = item.content
        bucket = by_day[item.scheduled_date.isoformat()]
        for key, output_key in (("total_calories", "calories"), ("total_protein", "protein"), ("total_carbs", "carbs"), ("total_fat", "fat")):
            value = content.get(key)
            if isinstance(value, (int, float)):
                bucket[output_key] += float(value)
    return {"daily": {day: {key: round(value, 2) for key, value in totals.items()} for day, totals in sorted(by_day.items())}, "planned_not_consumed": True}


def _periods_overlap(left: PlanRequest, right: PlanRequest) -> bool:
    return left.period_start <= right.period_end and right.period_start <= left.period_end


__all__ = ["GLOBAL_PLAN_REPOSITORY", "MemoryPlanRepository", "PlanContext", "PlanContextResolver", "PlanEngine", "PlanValidator"]
