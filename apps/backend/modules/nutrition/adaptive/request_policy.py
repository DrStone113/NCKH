"""Deterministic current-turn semantics; no LLM or inferred historic intent."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from .contracts import RecipeCandidate
from .eligibility import CandidateEligibilityGate


class RequestOrigin(str, Enum):
    CURRENT_EXPLICIT = 'CURRENT_EXPLICIT'
    CONFIRMED_CURRENT_CONTEXT = 'CONFIRMED_CURRENT_CONTEXT'
    LEARNED_PREFERENCE = 'LEARNED_PREFERENCE'
    HISTORICAL_OBSERVATION = 'HISTORICAL_OBSERVATION'


def normalize(value: str) -> str:
    text = unicodedata.normalize('NFKD', value.casefold().replace('đ', 'd'))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in text if not unicodedata.combining(c))).split())


# Lexical aliases only. Ingredient authority supplies names; no embedding or
# fabricated semantic similarity. Unknown terms require literal dish matching.
FOOD_ALIASES = {
    'chicken': ('chicken', 'ga'), 'beef': ('beef', 'bo'),
    'pork': ('pork', 'heo', 'lon'), 'fish': ('fish', 'ca'),
    'shrimp': ('shrimp', 'tom'), 'tofu': ('tofu', 'dau hu', 'dau phu'),
}


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase and f' {phrase} ' in f' {text} ')


@dataclass(frozen=True)
class CurrentRequest:
    origin: RequestOrigin = RequestOrigin.CURRENT_EXPLICIT
    requested_dish: str | None = None
    requested_foods: tuple[str, ...] = ()
    avoid_foods: tuple[str, ...] = ()
    avoided_candidate_ids: frozenset[str] = frozenset()
    cuisine: str | None = None
    meal_slot: str | None = None
    local_day: str | None = None
    preparation: str | None = None
    budget_band: str | None = None
    available_ingredient_ids: frozenset[str] | None = None
    portion_grams: float | None = None

    @property
    def has_constraints(self) -> bool:
        return any((self.requested_dish, self.requested_foods, self.avoid_foods,
                    self.avoided_candidate_ids, self.cuisine, self.meal_slot,
                    self.local_day, self.preparation, self.budget_band,
                    self.available_ingredient_ids is not None, self.portion_grams is not None))


def request_from_current_text(text: str | None) -> CurrentRequest:
    """Normalize a current-turn field, never preference/history text.

    This intentionally supports a bounded grammar. Unrecognized requests stay
    literal and fail closed for clarification instead of dropping constraints.
    """
    value = normalize(text or '')
    if not value or value in {'goi y mon toi nay', 'goi y mon an', 'suggest dinner', 'suggest a meal'}:
        return CurrentRequest()
    avoiding = any(contains_phrase(value, marker) for marker in ('khong an', 'khong muon an', 'tranh', 'avoid'))
    for phrase in ('hom nay', 'toi nay', 'today', 'please'):
        value = normalize(re.sub(r'\b' + re.escape(phrase) + r'\b', '', value))
    for prefix in ('hom nay toi muon an', 'toi khong muon an', 'toi khong an', 'toi muon an lai', 'toi muon an', 'cho toi an', 'cho toi', 'i want to eat', 'i want', 'khong muon an', 'khong an', 'an lai', 'an', 'avoid', 'tranh'):
        if value == prefix or value.startswith(prefix + ' '):
            value = value[len(prefix):].strip()
            break
    food = next((key for key, aliases in FOOD_ALIASES.items() if value in aliases or value in tuple('thit ' + item for item in aliases)), None)
    if avoiding:
        return CurrentRequest(avoid_foods=(food or value,))
    if food:
        return CurrentRequest(requested_foods=(food,))
    return CurrentRequest(requested_dish=value)


def request_matches(candidate: RecipeCandidate, request: CurrentRequest,
                    gate: CandidateEligibilityGate, *, local_day: str | None = None) -> bool:
    names = tuple(normalize(name) for name in gate.ingredient_names(candidate))
    ids = {mapping.canonical_food_id for mapping in candidate.mappings}
    def food_matches(value: str) -> bool:
        if value in ids:
            return True
        word = normalize(value)
        aliases = FOOD_ALIASES.get(word, (word,))
        return any(contains_phrase(name, alias) for name in names for alias in aliases)
    dish_names = tuple(normalize(value) for value in (candidate.title,) + candidate.aliases)
    if request.requested_dish and not any(contains_phrase(name, normalize(request.requested_dish)) for name in dish_names):
        return False
    if any(not food_matches(value) for value in request.requested_foods):
        return False
    if any(food_matches(value) or any(contains_phrase(name, normalize(value)) for name in dish_names) for value in request.avoid_foods):
        return False
    if candidate.candidate_id in request.avoided_candidate_ids:
        return False
    tags = set(candidate.dietary_tags)
    for field, prefix in ((request.cuisine, 'cuisine:'), (request.preparation, 'preparation:'), (request.budget_band, 'budget:')):
        if field and not any(tag.startswith(prefix) and normalize(tag[len(prefix):]) == normalize(field) for tag in tags):
            return False
    record = gate.metadata(candidate)
    slots = set(record.get('meal_types') or ()) | {tag.split(':', 1)[1] for tag in tags if tag.startswith('meal_type:')}
    if request.meal_slot and request.meal_slot not in slots:
        return False
    if request.local_day and request.local_day != local_day:
        return False
    if request.available_ingredient_ids is not None and not ids.issubset(request.available_ingredient_ids):
        return False
    if request.portion_grams is not None and abs(sum(m.grams or 0 for m in candidate.mappings) - request.portion_grams) > .01:
        return False
    return True
