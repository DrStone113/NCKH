# N3.2 Adaptive Recommendation Intelligence Report

## Existing Ranking Audit

Before N3.2 there were two intentional recommendation paths:

```text
suggest_dish → canonical catalog filter/portion scaling → legacy deterministic pick
N3 shadow candidates → AdaptiveRecommendationPipeline → staging-only soft score
```

`suggest_dish` remains the authoritative production baseline. It is not
silently switched to adaptive ranking in this phase. The old N3 shadow score
has been replaced by a compatibility facade over `RecommendationRankerV2`, so
there is now one soft-ranking formula for N3/N3.2 shadow callers.

N3.2 dataflow is:

```text
request → minimal context → candidate sources → deterministic hard filter
→ policy applicability → canonical nutrition → feasible portion check
→ RecommendationRankerV2 → public reason codes → feedback/memory
→ owner-private profile, portion prior, and aggregate catalog gaps
```

## Learning Signal Taxonomy

The explicit event taxonomy is `SHOWN`, `OPENED`, `SAVED`, `REJECTED`,
`SUBSTITUTED`, `LIKED`, `DISLIKED`, `ACTUALLY_CONSUMED`,
`REPEATED_CONSUMPTION`, `PORTION_CORRECTED`, `INGREDIENT_CORRECTED`, and
`RECIPE_CORRECTED`. Legacy `REPEATED` remains readable only.

`SHOWN` is exposure only. `OPENED` has zero preference weight and zero bandit
reward. Explicit likes/dislikes outrank implicit signals; actual and repeated
consumption are behavioural evidence. Rejection reasons remain distinct:
`DO_NOT_LIKE`, `NOT_TODAY`, cost, effort, availability, repetition, portion
size, and `OTHER` affect their own soft components rather than becoming a
permanent dislike.

## Preference Model, Confidence, and Time Decay

`UserPreferenceProfile` is bounded to recipe facts: dish, ingredient, protein,
cuisine, preparation, meal pattern, explicitly provided spice/texture,
effort, and budget. Every entry records affinity, confidence, source, update
time and evidence count. No demographic stereotype is inferred.

`PREFERENCE_WEIGHT_POLICY_V1` uses a 90-day half-life for behavioural
evidence. Active explicit confirmed preferences win conflicts with inferred
behaviour and emit `PREFERENCE_CONFLICT`. Allergies, restrictions, safety
facts, and canonical servings are outside this learning model and do not
decay here.

## Context Features and Candidate Source Mixing

`RecommendationContext` keeps only meal/time bucket, nutrition targets,
recent recommendation and meal memory, active-plan ID, stated intent,
cooking effort, budget, equipment and portion-fit results. Its logged context
fingerprint is an allowlisted coarse hash; it contains no user identity or
health profile.

Source types are explicit: `LOCAL_CANONICAL`, `PERSONAL_RECIPE`,
`STAGING_EXTERNAL`, `RUNTIME_EXTERNAL`. Source quality is an interpretable
soft component. A runtime/staging item cannot pass a comparable local
canonical item solely because it is novel.

## RecommendationRankerV2 and Multi-Objective Ranking

`RecommendationRankerV2` is the N3.2 authoritative soft ranking contract.
Hard constraints are evaluated before it runs. Its versioned, documented
components are nutrition fit, preference fit, source quality, mapping quality,
portion-fit quality, repetition penalty/diversity, novelty, cooking effort and
budget. It returns component values and structured reason codes, not hidden
weights to users.

## Diversity and Exploration

Recent exact dish, primary protein, cuisine and preparation are tracked in
recommendation memory separately from meal logs. Exact dish has a stronger
soft penalty than protein; cuisine/preparation are lighter. An explicit same
dish request clears the diversity penalty.

`EXPLORATION_POLICY_V1` deterministically and occasionally promotes only a
near-baseline unseen candidate that already passed all hard checks. It is
labelled product heuristic and records policy/version/propensity in shadow.

## Shadow Bandit and Replay Evaluation

`ShadowBanditPolicy` is optional and shadow-only. It only chooses among the
already-hard-filtered candidates and only learns from `ACTUALLY_CONSUMED`,
`REPEATED_CONSUMPTION`, `LIKED`, `SAVED`, `REJECTED` and `DISLIKED`.
`SHOWN` and `OPENED` have no reward.

`RecommendationReplayEvaluator` compares baseline ordering, V2 and optional
shadow policy on hard violations, top-k overlap, diversity, novelty,
preference match, repeat reduction, nutrition fit, source quality, and valid
acceptance-related outcomes. Its output is engineering replay, not causal
evidence.

## Cold Start, Personal Recipes, Portion Learning, and Corrections

Cold starts use hard-safe context and catalog quality and expose
`PREFERENCE_EVIDENCE_INSUFFICIENT`. Personal recipes can rank only as private
items with adequate mapping/calculation evidence; they never become canonical
or globally healthier by usage alone.

`PortionLearning` accepts only actual-consumption observations and stores a
median/recent range/evidence count. Its preferred scale is a small soft nudge
to `RecipePortionFitter`; canonical serving definitions and culinary bounds
remain unchanged. Ingredient/recipe corrections are classified as personal
revision, staging evidence, or canonical discrepancy report—never a direct
canonical mutation.

## Catalog Gap Detector and Active Learning Queue

`CatalogGapDetector` emits de-identified `CatalogGapCandidate` records for
unknown dishes, external-search clusters, unmapped ingredients, correction
clusters, low diversity, regional absence, and repeated personal consumption.
Priority combines frequency, mapping potential, regional relevance and source
availability. Tasks are structured as `FIND_RECIPE_SOURCE`, `RESOLVE_ALIAS`,
`RESOLVE_INGREDIENT_MAPPING`, `VERIFY_SERVING`, `VERIFY_VARIANT_IDENTITY`, or
`COLLECT_MORE_USER_CONFIRMATION`. They are evidence requests only.

## Privacy and Feedback UX

N3.2 adds owner-scoped schema in migration `016` for recommendation memory,
feedback, profiles, actual portion observations, shadow logs, aggregate gaps
and evidence tasks. Shared gap data accepts aggregate counters only; no user
ID, conversation text, health condition, weight, goal or private note is
allowed.

The Flutter card renders `Thích`, `Không hợp`, `Lưu lại`, `Đã ăn`, `Đổi món`
and `Vì sao?` only when a trusted shadow recommendation ID is present. The
reason picker is optional and writes a structured code only. Public
explanations are mapped from allowlisted `RankingReasonCode` values by
`PublicReasoningTrace`; weights and private profile details are not displayed.

## Shadow Comparison and Development Metrics

`LearningQualityMetrics` reports repeat-dish/protein rate, diversity, catalog
coverage, external discovery frequency, personal recipe usage, preference
signal coverage, explicit-to-implicit ratio, portion correction rate and gap
count. There is intentionally no composite "AI learning score".

The engineering-only scenario set covers cold start, rich/conflicting history,
explicit dislike, temporary rejection, repeat dish/protein, new cuisine,
personal/staging/runtime candidates, portion correction, catalog gap, no
feasible candidate and web-unavailable behaviour. It does not use the frozen
research benchmark.

## Edge / Playwright E2E

Microsoft Edge was launched through Playwright against the local Flutter web
build. The real app shell, demo-account entry and nutrition onboarding rendered
correctly. The N3.2 feedback component itself passed Flutter widget interaction
tests for like/save/consume/reason visibility.

The built app did not receive a registered N3.2 shadow recommendation during
this local run, so no feedback controls were intentionally injected into an
unrelated legacy card. Full browser E2E for feedback persistence, refresh and
reconnect remains gated on a trusted N3.2 candidate-delivery path; this is not
treated as production readiness.

## Ponytail Codespace Audit

No Ponytail capability was installed in this runtime, so no unsupported plugin
operation was attempted. Cross-reference and duplicate-ranking inspection was
performed directly against the files. The finding was the intentional legacy
`suggest_dish` baseline plus the former N3 shadow scorer; only the latter is
refactored to V2 in this shadow phase.

## Qualification Verifier Status

`verify_plan_v2_scoped_qualification.py` preserves
`HISTORICAL_V1_CONTAMINATED=true` while separately evaluating the P2.1A
automated freeze. With Flutter 3.44.8/Dart 3.12.2 and artifact/source hashes
matching, current status is `READY_FOR_FIRST_SCORED_ACCEPTANCE`. This is not a
release qualification and does not rewrite V1 or modify frozen P2 sources.

## Hard Invariants

All required N3.2 invariant counters are zero:

```text
PREFERENCE_OVERRIDES_ALLERGY = 0
PREFERENCE_OVERRIDES_DIETARY_RESTRICTION = 0
PREFERENCE_OVERRIDES_POLICY_SAFETY = 0
IMPLICIT_FEEDBACK_PROMOTED_TO_HARD_FACT = 0
SHOWN_AS_CONSUMED = 0
OPENED_AS_POSITIVE_REWARD = 0
PERSONAL_DATA_GLOBAL_LEAK = 0
LLM_DIRECT_CANONICAL_WRITE = 0
WEB_NUTRITION_AS_AUTHORITY = 0
RESEARCH_CORPUS_MUTATION = 0
```

## Research Invariance and Remaining Issues

No frozen research or P2 source was changed. Offline corpus integrity tests
passed. The database-backed research verifier could not complete because the
configured database endpoint refused the connection; no workaround or corpus
write was attempted.

Remaining before any production adaptive rollout: collect shadow comparisons
from a real candidate-delivery path, complete browser persistence/reconnect
E2E with an authorised test account, inspect replay metrics, and explicitly
approve a later rollout. Canonical auto-promotion remains disabled.

```text
RECOMMENDATION_RANKER_V2_READY = YES
PERSONAL_PREFERENCE_LEARNING_READY = YES
DIVERSITY_RERANKING_READY = YES
CATALOG_GAP_DETECTOR_READY = YES
PORTION_LEARNING_READY = YES
SHADOW_EXPLORATION_READY = YES
SHADOW_BANDIT_READY = YES
PRODUCTION_ADAPTIVE_RANKING_READY = NO
CANONICAL_AUTO_PROMOTION_READY = NO
```
