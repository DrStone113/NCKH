# N3.1 Controlled External Discovery Report

## Existing N3 Audit

Before N3.1, N3 already had typed runtime/staging candidates, exact canonical
mapping, canonical nutrient arithmetic, bounded portion fitting, hard quality
gates, owner-scoped feedback, and a permanently disabled canonical promotion
method. The previous external provider was an injected placeholder: it had no
search provider, fetch transport, structured extractor, cache, source health,
or development/shadow orchestration.

N3.1 adds the following development/shadow-only data flow:

```text
local-first reason gate
  -> RecipeSearchProvider
  -> policy-selected RecipeFetcher
  -> typed structured extraction
  -> canonical mapping + coverage
  -> canonical nutrient calculation + hard gate
  -> STAGING_RECIPE
  -> optional separate adapted revision
  -> existing shadow and promotion-evidence paths
```

There is still no N3.1 production-chat wiring, canonical catalog writer, meal
log write, or frozen-corpus write.

## Source Audit

Browser audit used Playwright CLI with Microsoft Edge. No login, CAPTCHA
bypass, anti-bot bypass, credential storage, executable download, or source
rate-limit probing was used.

| Source | Browser observation | Classification |
| --- | --- | --- |
| [TheMealDB API](https://www.themealdb.com/api.php) | Official JSON endpoints returned complete named ingredient/measure fields for IDs `53013` and `52997`; API area filter returned Vietnamese-labelled results. API documentation and [terms](https://www.themealdb.com/terms_of_use.php) expressly require official endpoints rather than website scraping. | `APPROVED_API`, development/shadow only. |
| [Vicky Pham – gỏi cuốn](https://vickypham.com/blog/vietnamese-spring-rolls-goi-cuon/) and [phở bò](https://vickypham.com/blog/pho-bo-instant-pot/) | Each page exposed one `Recipe` JSON-LD block. The inspected pages contained respectively 6 and 21 ingredients, recipe yields of 5 and 8, duration fields, and recipe-step arrays. [`robots.txt`](https://vickypham.com/robots.txt) did not prohibit those pages, but no storage/reuse terms were found from site footer. | `USER_URL_ONLY`; explicit user URL may be read transiently, but no candidate cache/staging. |
| [Cookpad Vietnamese search](https://cookpad.com/eng/search/vietnamese) and [recipe](https://cookpad.com/eng/recipes/26236550) | JSON-LD recipe metadata and ingredient quantities were present; optional login UI was observed. [Terms](https://cookpad.com/us/terms) describe user recipes as user-created and not screened for accuracy/safety. | `BLOCKED`; no automatic fetch, cache, staging, or browser transport. |

## Approved Sources

`THEMEALDB_OFFICIAL_API` is the single real source enabled for N3.1
development/shadow acquisition. It uses `API_FETCH`, an HTTPS host allowlist,
20 local requests/minute, a ten-second timeout, one retry policy declaration,
and required attribution. Its free test key is explicitly limited to
development/educational use; public release requires a separately configured
approved production key/subscription.

## Limited / Blocked Sources

`VICKY_PHAM_USER_URL` is intentionally non-discoverable and non-stageable.
`COOKPAD_PUBLIC_RECIPES` and `UNTRUSTED_WEB_CONTENT` are blocked before any
transport call. `CONTROLLED_RECIPE_SEARCH` may return registered source URLs
only; it cannot fetch arbitrary search results.

## Browser Verification

The installed Playwright capability was verified with an actual Microsoft Edge
session. The implementation provides `PlaywrightCliEdgeTransport` and
`PlaywrightRecipeFetcher` for future approved JS-rendered sources. It starts an
isolated temporary session, uses only fixed agent-owned DOM retrieval code,
validates the final redirect host, limits DOM size, and closes the session.

Browser capability is never a trust signal. The current registry has no
approved JS-rendered source; browser extraction is therefore covered with
typed fake transport tests rather than a permanently live website test.

## Discovery Architecture

`RecipeSearchProvider`, `RecipeFetcher`, `RecipeExtractor`, and
`ExternalRecipeAcquisitionService` are independent protocols/services.
`TheMealDbSearchProvider` is only one adapter, not a recommender dependency.
Search output contains title/source URL/source recipe ID/confidence only and
does not calculate nutrition.

`ControlledSearchDiscoveryProvider` additionally filters any injected generic
search result to registered, fetchable source host policies before it can reach
a transport. It discards unknown, blocked, review-required, and host-mismatched
URLs.

## Search Gating

External discovery is deterministic and local-first. Supported reason codes
include `NO_LOCAL_CANDIDATE`, `INSUFFICIENT_LOCAL_CANDIDATES`, `LOW_DIVERSITY`,
`REPEATED_RECENT_RECOMMENDATION`, `UNKNOWN_REQUESTED_DISH`, and
`INSUFFICIENT_CUISINE_COVERAGE`. Query construction accepts meal, cuisine,
food, confirmed dietary restriction, region, and nutrition intent; it excludes
health records, body weight, owner IDs, and conversation text.

## Structured Extraction

Extraction priority is official API JSON, then JSON-LD `Recipe`, with an
explicit extractor registry. There is no LLM scraping fallback. JSON-LD
captures title, ingredients, yield, cuisine/category, durations, optional
instructions under storage policy, and reference nutrition. The raw page is
never cached.

## Ingredient Parsing

`RawIngredient` now preserves the original text plus nullable amount, parsed
unit, ingredient name, preparation state, optional marker, and uncertainty.
`a little oil`, `salt to taste`, and unsupported household/count units are not
silently converted to grams.

## Unit Normalization

Mass units (`g`, `kg`, `mg`) convert deterministically. `ml`, `l`, `tsp`,
`tbsp`, and count/piece units need an approved food-specific gram conversion;
otherwise the mapping retains `QUANTITY_NOT_RESOLVED` and cannot produce a
precise nutrient claim.

## Canonical Mapping

The mapper now preserves multiple exact alias matches as `AMBIGUOUS` with
candidate food IDs/reasons. It does not choose a close substitute. Exact food
mapping, raw/cooked state checks, allergens, and canonical food IDs continue to
come from the application catalog.

## Mapping Coverage

N3.1 reports ingredient-count and available mass coverage. A required
unmapped/unquantified ingredient produces `NUTRITION_NOT_VERIFIED`. An optional
unmapped garnish is represented as `NUTRITION_PARTIALLY_VERIFIED`, not a
precise verified nutrient value; strict N3 staging still requires a complete
canonical calculation.

## Nutrition Recalculation

External calories/macros remain `SOURCE_REPORTED_REFERENCE` evidence only.
Canonical energy/protein/carbohydrate/fat always come from mapped canonical
foods and quantities through the existing calculation version.

## Source Nutrition Conflict

The prior generic `SOURCE_NUTRITION_CONFLICT` is retained and now has granular
signals: `ENERGY_CONFLICT`, `PROTEIN_CONFLICT`, `CARB_CONFLICT`, and
`FAT_CONFLICT`. Values are never averaged or copied into canonical nutrition.

## Recipe Identity

Runtime identity hashes source ID, source recipe ID/URL, normalized canonical
ingredient structure, quantities, and state. A title alone cannot identify or
merge recipes.

## Duplicate / Variant Detection

`RecipeVariantClassifier` uses source identity, canonical ingredient overlap,
and aliases to classify `SAME_RECIPE`, `RECIPE_VARIANT`, `REGIONAL_VARIANT`,
`POSSIBLE_DUPLICATE`, or `DISTINCT_RECIPE`. Existing repository duplicate
quarantine remains the final staging guard. No embedding-only merge exists.

## Portion Fitter Integration

`RecipePortionFitter.create_adapted_variant` creates a new
`ADAPTED_RECIPE_VARIANT`, recalculates it from canonical ingredients, and never
changes the base source evidence. Public presentation must label this as
`Công thức đã được điều chỉnh khẩu phần`.

## Personal Learning

Existing explicit feedback remains soft, owner-scoped ranking evidence and
cannot override dietary/allergen hard gates. Repeated unknown dishes create an
owner-scoped `PERSONAL_RECIPE_ACQUISITION_CANDIDATE`, not a global recipe.

## Active Learning Queue

The aggregate-only priority queue supports requested-unknown dishes, frequent
personal dishes, search frequency, unmapped clusters, regional gaps, and user
correction clusters. It rejects user IDs and other private fields before they
can become global acquisition evidence.

## Staging Integration

The acquisition service saves a runtime candidate, stages it only when the
existing hard gate validates it, and leaves it in shadow-ready workflow. The
new migration stores policy-approved structured cache metadata, source health,
priority tasks, and promotion scorecards only. It stores no raw HTML/browser
state and makes no canonical insert.

## Shadow Recommendation

Existing `AdaptiveRecommendationPipeline` remains shadow-only. N3.1 adds no
production recommendation switch. Comparative local-only versus local+staging
metrics remain development operational data, not research outcomes.

## Promotion Scorecard

`PromotionEvidenceScorecard` exposes source policy, mapping/nutrition/allergen
validity, duplicate status, conflicts, runtime stability, shadow evidence,
usage, and corrections. `AUTO_PROMOTION_ELIGIBLE` is an evidence state only;
it is not a catalog write permission.

## Automated Semantic Review

Existing isolated automated reviews remain evidence only. Deterministic hard
gate failure wins over any semantic review result.

## Canonical Writer

`CanonicalRecipeWriter` validates matching evidence hash and hard gates then
rejects because its auto-promotion flag is false. It deliberately contains no
catalog/database write implementation, so an LLM cannot invoke an arbitrary
canonical `INSERT`/`UPDATE`.

## Auto-Promotion Flag

`CANONICAL_RECIPE_AUTO_PROMOTION` remains effectively off. Migration 015 also
uses `CHECK (canonical_write_authorized = FALSE)`.

## Source Health

Per-source rate limiter, timeout, circuit breaker, cache status, fetch result,
structured-extraction result, latency, blocked response, and a failure-based
runtime downgrade are implemented. A downgrade disables the worker only; it
cannot auto-upgrade a source or rewrite the registry.

## Poisoning Tests

N3.1 tests cover prompt-injection JSON-LD, fake source nutrition, blocked
source browser fetch, redirect host policy, unknown/household quantities,
ambiguous aliases, source review policy, duplicate identity, and canonical
writer rejection. Extracted typed values are the only page data passed into the
candidate boundary; HTML/scripts/hidden page controls never become prompts or
tool instructions.

## Development Evaluation

The test flow covers unknown/local-gap trigger → search → policy fetch → API
extraction → mapping → canonical calculation → staging, including a separate
portion-adapted staged revision. It proves no canonical write authorization.
Live browser auditing is intentionally separate from CI fixtures so transient
layout, cookie, or availability changes do not make regression flaky.

## Research Invariance

N3.1 does not modify research A/B/C, the frozen corpus manifest/data, or
`nutrition-policy-v1.0.1`. It does not write meals or the canonical dish/food
catalog.

## Remaining Issues

- TheMealDB's public development key must not be used for a public release;
  production activation requires a reviewed credential/subscription and an
  explicit configuration change.
- API measures frequently use household/count units. Recipes with unresolved
  primary quantities correctly remain unverified/quarantined rather than
  receiving inferred nutrition.
- No structured website is auto-fetched today. Vicky Pham is deliberately
  user-URL-only and Cookpad is blocked pending explicit source permission.
- The cache/health schema migration is supplied; production persistence wiring
  should be implemented only with the deployment database migration workflow.

```text
EXTERNAL_RECIPE_DISCOVERY_READY = YES (development/shadow API path)
STRUCTURED_WEB_EXTRACTION_READY = YES (parser/browser adapter; no auto-approved web source)
CANONICAL_NUTRITION_AUTHORITY_PRESERVED = YES
RECIPE_PORTION_ADAPTATION_E2E_READY = YES (development/shadow)
STAGING_EXTERNAL_RECIPE_READY = YES (development/shadow)
AUTO_PROMOTION_ELIGIBILITY_READY = YES
CANONICAL_AUTO_PROMOTION_READY = NO
```
