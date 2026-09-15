"""Provider-neutral, policy-gated recipe discovery for N3."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Protocol, Sequence

from modules.nutrition.catalog import load_dish_catalog

from .contracts import CandidateSource, RawIngredient
from .engine import AdaptiveRecipeError, load_adaptive_source_registry


class DiscoveryReason(str, Enum):
    NO_LOCAL_CANDIDATE = "NO_LOCAL_CANDIDATE"
    INSUFFICIENT_LOCAL_CANDIDATES = "INSUFFICIENT_LOCAL_CANDIDATES"
    REPEATED_RECENT_RECOMMENDATION = "REPEATED_RECENT_RECOMMENDATION"
    UNKNOWN_REQUESTED_DISH = "UNKNOWN_REQUESTED_DISH"
    INSUFFICIENT_CUISINE_COVERAGE = "INSUFFICIENT_CUISINE_COVERAGE"
    UNKNOWN_DISH = "UNKNOWN_DISH"
    POOR_LOCAL_COVERAGE = "POOR_LOCAL_COVERAGE"
    LOW_DIVERSITY = "LOW_DIVERSITY"
    CONSTRAINT_GAP = "CONSTRAINT_GAP"


@dataclass(frozen=True)
class RecipeDiscoveryRequest:
    query: str
    reason: DiscoveryReason
    local_viable_count: int
    diversity_score: float
    meal_type: str | None = None
    cuisine: str | None = None
    ingredient_constraints: tuple[str, ...] = ()
    dietary_constraints: tuple[str, ...] = ()
    language_region: str | None = None


@dataclass(frozen=True)
class DiscoveredRecipe:
    title: str
    aliases: tuple[str, ...]
    source: CandidateSource
    ingredients: tuple[RawIngredient, ...]
    raw_source_text: str
    source_reported_nutrition: object | None = None


class RecipeDiscoveryProvider(Protocol):
    source_id: str

    def discover(self, request: RecipeDiscoveryRequest) -> Sequence[DiscoveredRecipe]:
        """Return untrusted recipe candidates; no provider writes a catalog."""


def should_trigger_external_discovery(request: RecipeDiscoveryRequest) -> bool:
    if not request.query.strip():
        return False
    if request.reason in {
        DiscoveryReason.UNKNOWN_DISH,
        DiscoveryReason.UNKNOWN_REQUESTED_DISH,
        DiscoveryReason.NO_LOCAL_CANDIDATE,
        DiscoveryReason.INSUFFICIENT_CUISINE_COVERAGE,
        DiscoveryReason.REPEATED_RECENT_RECOMMENDATION,
    }:
        return True
    if request.reason in {
        DiscoveryReason.POOR_LOCAL_COVERAGE,
        DiscoveryReason.INSUFFICIENT_LOCAL_CANDIDATES,
    }:
        return request.local_viable_count < 2
    if request.reason == DiscoveryReason.LOW_DIVERSITY:
        return request.diversity_score < 0.35
    return request.reason == DiscoveryReason.CONSTRAINT_GAP and request.local_viable_count == 0


class LocalCatalogProvider:
    """Read-only adapter over existing canonical dish records."""

    source_id = "LOCAL_CANONICAL_CATALOG"

    def discover(self, request: RecipeDiscoveryRequest) -> Sequence[DiscoveredRecipe]:
        query = request.query.casefold().strip()
        if not query:
            return ()
        results: list[DiscoveredRecipe] = []
        for dish in load_dish_catalog():
            title = str(dish.get("name") or "")
            if query not in title.casefold():
                continue
            ingredients = tuple(
                RawIngredient(
                    raw_text=str(item.get("name") or ""),
                    amount=float(item.get("grams") or 0),
                    unit="g",
                    declared_state=str(item.get("food_state") or "UNKNOWN"),
                )
                for item in dish.get("ingredients") or ()
                if item.get("name") and item.get("grams")
            )
            results.append(
                DiscoveredRecipe(
                    title=title,
                    aliases=(),
                    source=CandidateSource(
                        source_type="LOCAL_CATALOG",
                        source_id=self.source_id,
                    ),
                    ingredients=ingredients,
                    raw_source_text="",
                )
            )
        return tuple(results)


class PersonalRecipeProvider:
    """Returns only recipes supplied by the requesting owner."""

    source_id = "USER_CONFIRMED_PERSONAL_RECIPE"

    def __init__(self, recipes_for_owner: Callable[[str], Iterable[DiscoveredRecipe]]) -> None:
        self._recipes_for_owner = recipes_for_owner

    def discover_for_owner(
        self, owner_user_id: str, request: RecipeDiscoveryRequest
    ) -> Sequence[DiscoveredRecipe]:
        if not owner_user_id.strip():
            raise AdaptiveRecipeError("PERSONAL_DISCOVERY_REQUIRES_OWNER")
        query = request.query.casefold().strip()
        return tuple(
            item
            for item in self._recipes_for_owner(owner_user_id)
            if query in item.title.casefold()
        )

    def discover(self, request: RecipeDiscoveryRequest) -> Sequence[DiscoveredRecipe]:
        raise AdaptiveRecipeError("PERSONAL_DISCOVERY_REQUIRES_OWNER")


class ApprovedExternalRecipeProvider:
    """Adapter boundary for an explicitly approved external source.

    It has no network implementation. A host injects a policy-compliant fetcher
    after source review; arbitrary web search is blocked by the registry.
    """

    def __init__(
        self,
        *,
        source_id: str,
        fetcher: Callable[[RecipeDiscoveryRequest], Iterable[DiscoveredRecipe]],
    ) -> None:
        policy = load_adaptive_source_registry().get(source_id)
        if policy is None or policy["access_status"] != "APPROVED":
            raise AdaptiveRecipeError("EXTERNAL_DISCOVERY_SOURCE_NOT_APPROVED")
        if policy["source_type"] not in {"CURATED_EXTERNAL", "WEB_SEARCH"}:
            raise AdaptiveRecipeError("INVALID_EXTERNAL_DISCOVERY_SOURCE_TYPE")
        self.source_id = source_id
        self._source_type = str(policy["source_type"])
        self._fetcher = fetcher

    def discover(self, request: RecipeDiscoveryRequest) -> Sequence[DiscoveredRecipe]:
        if not should_trigger_external_discovery(request):
            return ()
        try:
            results = tuple(self._fetcher(request))
        except (OSError, TimeoutError) as exc:
            # Discovery failure is contained at this boundary.  It must not
            # create a partial candidate, relax constraints, or fall back to
            # arbitrary web content.
            raise AdaptiveRecipeError("EXTERNAL_DISCOVERY_UNAVAILABLE") from exc
        for recipe in results:
            if recipe.source.source_id != self.source_id or recipe.source.source_type != self._source_type:
                raise AdaptiveRecipeError("EXTERNAL_DISCOVERY_SOURCE_SPOOFING")
        return results


__all__ = [
    "ApprovedExternalRecipeProvider",
    "DiscoveredRecipe",
    "DiscoveryReason",
    "LocalCatalogProvider",
    "PersonalRecipeProvider",
    "RecipeDiscoveryProvider",
    "RecipeDiscoveryRequest",
    "should_trigger_external_discovery",
]
