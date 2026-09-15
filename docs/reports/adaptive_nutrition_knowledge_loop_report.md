# ADAPTIVE NUTRITION KNOWLEDGE LOOP REPORT

## Current Codespace Audit

N3 is additive: its code lives under `apps/backend/modules/nutrition/adaptive`,
its source policy is a separate registry, and persistence is migration 014.
The P2.1R implementation-freeze manifest was re-hashed: all 9 protected
sources matched. The focused nutrition, catalog, research-corpus, migration,
and N3 suite passed 92 tests.

## Existing Canonical Nutrition Authority

`modules/nutrition/canonical_foods.py` remains the authority for food IDs,
allergens, objective tags, raw/cooked state, and nutrient values. N3 reads it
through an exact mapper. Source-reported recipe nutrition is evidence only;
canonical ingredient arithmetic supplies every candidate total.

## Learning Domains

The typed domains are personal memory, personal recipes, runtime external
candidates, staging recipes, canonical production recipes, and frozen research
recipes. Candidate construction and the N3 repository reject canonical and
frozen-research write domains.

## Personal Recipe Learning

Personal aliases, owner-scoped recipes, feedback, and preference scores are
implemented with explicit provenance. A personal recipe requires an owner and
the `USER_CONFIRMED_PERSONAL_RECIPE` source policy; it cannot become a global
catalog record through this subsystem.

## External Recipe Discovery

Discovery is provider-neutral and trigger-gated for unknown dishes, low local
coverage, low diversity, or a constraint gap. Only an explicitly approved
registry source can supply a provider; provider output is checked again for
source-ID and source-type spoofing. No network fetcher is enabled in this
codespace, so discovery remains a controlled integration boundary.

## Source Registry

`adaptive_recipe_source_registry_v1.json` declares local canonical catalog
data as approved, user-confirmed recipes as personal-only, a curated NIN
reference as metadata-only, and untrusted web content as blocked. The default
external-discovery policy remains disabled until an approved host adapter is
configured. Each policy also declares licence status, raw-source-text storage,
and snapshot-cache treatment.

## Ingredient Extraction

N3 accepts typed `RawIngredient` values (raw text, amount, unit, declared
state). It does not allow free-form LLM output to write a recipe or nutrition
record; an extraction adapter must construct this contract and then pass the
same deterministic gates.

## Canonical Ingredient Mapping

Mapping is exact name/alias resolution only. Units are normalized only for
g/kg/mg; unknown units, unknown ingredients, and raw/cooked state conflicts
are quarantined. There is no silent food substitution.

## Alias / Variant Model

Recipe candidates retain source aliases, while personal aliases are separate,
owner-scoped records with provenance. A candidate carries a new identity and
evidence hash, so a same-name/different-recipe source cannot overwrite an
existing recipe.

## Nutrition Recalculation

`calculate_canonical_nutrition` sums canonical composition values per mapped
ingredient and serving grams. Source nutrition can be compared for conflict,
but it never replaces calculated energy, protein, carbohydrate, or fat.

## RecipePortionFitter

The deterministic fitter performs bounded coordinate search with ingredient
classes for anchors, scalable ingredients, limited-scalable ingredients,
flavour-bounded ingredients, optional ingredients, and fixed ingredients. It
recalculates nutrition after every candidate adjustment and returns
`NO_FEASIBLE_RECIPE_ADAPTATION` instead of relaxing a hard bound.

## Optimization Semantics

The objective combines relative energy error, protein error, and a small
portion-distortion term. Targets are accepted only within the explicit 10%
tolerance and only after every hard safety/constraint gate has passed.

## Constraint Validation

Allergen exclusions and normalized food restrictions (`no_pork`, `no_beef`,
`no_seafood`, vegetarian, vegan, standard allergen restrictions, low-carb,
and high-protein) are evaluated from canonical tags and totals. An unknown
restriction fails closed as `DIETARY_RESTRICTION_UNVERIFIABLE`.

## Evidence Bundle

Each candidate retains typed source provenance, raw source text, raw
ingredients, canonical mappings, calculated and source-reported nutrition,
allergens, validation codes, calculation version, and a SHA-256 evidence hash.

## Candidate Quality Gate

Hard gates reject incomplete mapping, invalid units, state conflict, absent or
impossible nutrition, failed energy/macro sanity, allergy or dietary
violations, and untrusted instruction/script content. Source nutrition
disagreement is retained as evidence and cannot become authoritative.

## Staging Catalog

Migration 014 adds N3-only personal-memory, personal-recipe, candidate,
candidate-version, feedback, acquisition-queue, and promotion-decision tables.
Candidates move through an immutable lifecycle history into staging and then
shadow eligibility; no migration writes the JSON-backed canonical catalog.

## Automated Review

The register uses `review_source=AUTOMATED`, run ID, model, rubric hash,
verdict, reason, consensus, and automated adjudication. It contains no fake
human-review field. The supplied repository supports multiple isolated passes
and records `same_model_multi_pass` when appropriate; no semantic judge model
is configured or invoked by default.

## Promotion Policy

Promotion evaluates hard gates and automated-review evidence, but always emits
`canonical_write_authorized=false`. `authorize_canonical_write` raises an
error. A clean shadow candidate therefore remains `REQUIRES_REVIEW`.

## Versioning / Rollback

Candidate states are immutable values, with in-process version history and a
database candidate-version table. The lifecycle includes discovered, extracted,
mapped, calculated, validated/quarantined, staging, and shadow eligible. The
production catalog is outside this version path.

## Feedback Learning

Shown/opened, saved/rejected, substitutions, likes/dislikes, actual consumption,
and repeats are explicit typed events. Feedback is owner-scoped and rejected
for revoked or rejected candidates.

## Preference Model

Preference is a bounded, 90-day time-decayed soft score. Exposure and opens
have zero weight, while explicit positive/negative feedback has stronger
weight. It is never consulted for allergy, restriction, nutrition, or other
hard decisions.

## Personal Portion Learning

The schema reserves `PERSONAL_PORTION_PRIOR`, but estimation of an individual
portion prior from logged meals is intentionally not enabled yet. It requires a
separate consent, retention, and calibration design.

## Diversity / Exploration

Shadow ranking includes a small deterministic novelty adjustment for recently
shown candidate IDs. It does not use random exploration or a bandit policy.

## Active Learning Queue

The repository can enqueue aggregate-only acquisition requests for unknown
dishes, coverage/diversity gaps, ambiguous mappings, and frequent personal
recipes. It is a request queue, not an automatic scraping or promotion path.

## Privacy

Personal recipes and aliases require owner scope. Global aggregation rejects
user ID, owner ID, health fields, weight, goals, conversations, and chat text;
only whitelisted aggregate recipe structure fields may be returned.

## Poisoning Defense

Recipe text is untrusted. Prompt-injection markers, scripts/JavaScript URLs,
unmapped or malicious ingredient names, source-type spoofing, and fake
nutrition claims are contained by typed contracts and deterministic gates. The
repository quarantines duplicate title-and-ingredient/evidence submissions
within the same visible scope while retaining same-name recipe variants. It
also has a configurable per-source ingestion ceiling; a production rollout
still needs persistence-backed, time-windowed rate limiting.

## Recommendation Integration

`AdaptiveRecommendationPipeline` is shadow-only and ranks only hard-gate
passing `STAGING_RECIPE` candidates marked `SHADOW_ELIGIBLE`. It deliberately
does not alter the established `suggest_dish` production path.

## Public Trace

Shadow results expose Vietnamese user-facing progress messages: the system
labels a library recipe, a recalculated recipe, or a new externally sourced
recipe; it then reports that ingredients were checked, nutrition was
recalculated, and the recipe is in trial mode. Internal prompts, raw web text,
review internals, and personal data are not exposed.

## Development Evaluation

`tests/test_adaptive_nutrition_n3.py` contains 16 engineering cases covering
authoritative recalculation,
source conflict, unmapped and raw/cooked conflict, allergies, dietary
restrictions, prompt injection, feasible/infeasible portion fitting,
owner-scoped feedback, automated consensus, source blocking/spoofing, duplicate
poisoning, revocation, shadow ranking, migration separation, and disabled
canonical writes. The focused regression run completed with `96 passed`.

## Research Invariance

N3 does not modify `offline-v1-636`, the research manifest, research A/B/C,
research benchmark data, or the frozen Plan V2 implementation. Research corpus
tests passed, and the P2.1R manifest verified all 9 protected source hashes.

## Remaining Issues

- No approved live external fetcher, rate limiter, or persisted repository
  adapter is wired into the running service yet.
- Semantic judge execution and its isolated-pass orchestration must be supplied
  by an approved host integration; the provenance/register contract is ready.
- Personal portion-prior calibration, alias disambiguation UX, duplicate-rate
  controls, revocation workflow, and a shadow-results dashboard remain rollout
  work.
- Canonical auto-promotion is deliberately unavailable.

PERSONAL_RECIPE_LEARNING_READY = YES
EXTERNAL_RECIPE_DISCOVERY_READY = NO
RECIPE_PORTION_FITTER_READY = YES
STAGING_CATALOG_READY = YES
AUTOMATED_PROMOTION_GATE_READY = YES
CANONICAL_AUTO_PROMOTION_READY = NO
