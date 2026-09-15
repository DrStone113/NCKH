# N3.3 ADAPTIVE RANKING SHADOW EVALUATION REPORT

Product engineering evaluation, 2026-09-07. **Adaptive ranking is not ready for rollout.**
The frozen ranker fails explicit-current-request precedence, a diversity stress
scenario, and an injected canonical-reference validation probe. Genuine durable
usage could not be read. These findings do not reopen N3.2.1 or change its closure.

Changes are limited to the N3.3 evaluator, focused tests, an offline/read-only
runner, this report, and N3.3 evidence files. No ranking weights, production
configuration, feedback SQL architecture, Flutter architecture, Plan V2,
research assets, or canonical catalog were changed. No browser automation,
commit, or push was performed.

## Frozen Ranking Baselines

Machine-readable versions, configurations, features, and SHA-256 values:
[frozen ranking inventory](../../apps/backend/validation/n3_3/n3-3-frozen-ranking-baselines-v1.json).

| Component | Frozen version | Configuration and features |
| --- | --- | --- |
| BASELINE_RANKER | SUGGEST_DISH_DETERMINISTIC_BASELINE | Existing `suggest_dish`: canonical meal/query/restriction/ingredient filtering, region preference, non-recent candidate pool with fallback; then minimum absolute serving-scale deviation, calorie error, catalog ID. Calorie bounds .7–1.5; serving scale .65–1.60. |
| ADAPTIVE_RANKER | RECOMMENDATION_RANKER_V2_WEIGHT_POLICY_V1 | Nutrition .30, preference .22, source .12, mapping .10, portion .10, diversity .07, novelty .05, effort .02, budget .02. Hard gate precedes soft scores. Inputs include owner preference, recent memory, canonical nutrients, recipe attributes, and caller-supplied portion fit. |
| DIVERSITY_RERANKER | RECOMMENDATION_RANKER_V2_DIVERSITY_COMPONENT_V1 | Component inside RankerV2, not a separate reorder stage. Maximum applicable penalty: dish .70, protein .35, cuisine .15, preparation .12. Exact dish intent clears all repeat penalties; novelty remains separate. |
| SHADOW_BANDIT_POLICY | CONTEXTUAL_BANDIT_SHADOW_V1 | Deterministic reward/exploration scorer, observation-only. It never chooses the delivered recommendation. |

Baseline/diversity names above are descriptive evaluation identifiers; source
hashes pin implementations that do not carry independent release versions.

| Source | SHA-256 |
| --- | --- |
| `services/agent/tools/dish.py` | `168b5e25e6cd8d8c66dc30aa3c8d4879cb5bc310a39caf262caee35388c957c6` |
| `modules/nutrition/adaptive/intelligence.py` | `597a8eb3411ec37e5f6ab74ccc832180f1d03761c627a4e052b2f8cb085974cf` |
| `modules/nutrition/adaptive_router.py` | `70c79949874df4ddebd0f8516738644ec440ce22c5301050902891a87b19ce03` |
| `modules/nutrition/adaptive/recommendation.py` | `c915a7e9dab5e41bf6829e7ec3a25966e63e73c26d60a9ba586b3ae1cd93b65b` |

All paths in this table are relative to `apps/backend`. Before/after hashes for
377 protected files are identical, including ranking sources, migrations,
canonical data, root research data, experiment/acceptance sources and artifacts,
Plan V2 sources, Flutter sources/tests, configuration, and the N3.2.1 closure
report. This is a file-isolation check, not a rerun of scientific benchmarks.

Current configuration is `adaptive_recommendation_mode=shadow`,
`app_environment=development`. Chat preserves the canonical tool result.
The existing dedicated development delivery endpoint already selects RankerV2's
top candidate; it must not be mistaken for an unpersonalized baseline exposure.
N3.3 changes neither delivery path and introduces no online authority.

## Available Real Feedback

[Durable audit evidence](../../apps/backend/validation/n3_3/n3-3-durable-feedback-audit-v1.json)
records the final attempt at 2026-09-07T12:33:52Z. Both sandbox and approved
outside-sandbox connection attempts failed with `ConnectionRefusedError`,
Windows error 1225. No SQL query reached the database; no migrations or writes
were attempted. No service was started.

```text
REAL_RECOMMENDATION_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
REAL_FEEDBACK_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
USERS_WITH_FEEDBACK = NOT_AVAILABLE_DATABASE_UNREACHABLE
LIKED_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
DISLIKED_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
SAVED_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
REJECTED_EVENTS = NOT_AVAILABLE_DATABASE_UNREACHABLE
```

These are unknown, not zero. Durable PreferenceEvidence rows and
PersonalPortionPrior inputs are also unavailable for this evaluation.
NOT_TODAY, ACTUALLY_CONSUMED, repeated consumption, and correction counts are
likewise unavailable; they have not been folded into another event count.

Durability alone would not establish genuine user origin: these are
development/shadow tables and the frozen schema lacks a dedicated usage-origin
register. The read-only collector reports any future nonempty totals as
unclassified until provenance is verified. Test users are never inferred to be
real users from their names, UUIDs, or a policy label.

The metric helper excludes unknown/synthetic provenance, requires exact
owner/recommendation/candidate/policy binding and immutable feedback IDs, and
deduplicates events. Raw feedback counts remain distinct from rates based on
unique exposures with each outcome. No reporting denominator minimum has been
authorized for observed data, so rates remain withheld by default; a chosen
reporting minimum would not constitute rollout sufficiency.

## Baseline vs Adaptive Comparison

Persisted [development comparisons](../../apps/backend/validation/n3_3/n3-3-shadow-development-v1.json)
carry `SYNTHETIC_DEVELOPMENT` and `N3_3_SHADOW_DEVELOPMENT`.
There are two explicitly separate development sources:

- Twelve controlled scenarios use synthetic baseline orders with stated
  ground truth. Those orders are not claimed to be production captures.
- Three synthetic contexts read the current canonical product catalog.
  A's full eligible order is derived from the frozen baseline's existing
  scale/filter functions and ordering key, with top-1 verified against an
  actual `suggest_dish` call. B evaluates that same candidate snapshot.
  These contexts have no user feedback, GPS, or recommendation history.

| Canonical development context | Eligible candidates | A top-1 verified | Top-1 changed | Top-3 Jaccard overlap | Valid retention |
| --- | ---: | --- | --- | ---: | ---: |
| lunch, 500 kcal | 112 | YES | YES | 0 | 1.0 |
| dinner, 600 kcal, query “gà” | 9 | YES | YES | .2 | 1.0 |
| breakfast, 400 kcal | 49 | YES | YES | 0 | 1.0 |

No canonical projection was excluded; all 170 candidate evaluations retained
valid references and passed the tested hard constraints. These counts can
include the same dish across contexts. Top-k overlap means intersection divided
by union of the top-k sets, with k=3. Changed identity or overlap does not by
itself establish improvement; these three contexts have no objective user
preference ground truth.

Each comparison records A/B order, top identities, candidate-set fingerprint,
policy versions, shadow-bandit choice, promotion/demotion, repetition change,
top-k diversity and coverage, valid retention, and portion-fit compatibility.
Invalid A identities are disclosed without silently replacing A's top candidate.
The checker uses the independent quality gate plus supplied canonical registry
and scenario expectations, not the ranker's own filtering method as its oracle.

No genuine observed A/B context could be replayed. Existing durable logs do not
contain complete candidate snapshots, context, owner-state-at-exposure, and
separate A/B orders for every delivery. The N3.3 files store the executed
development comparisons only; universal live comparison capture remains unmet.

## Positive Feedback Behavior

The frozen preference policy defines separate affinities: LIKED .85, SAVED .25,
ACTUALLY_CONSUMED .50, REPEATED_CONSUMPTION .80, legacy REPEATED .65.
DISLIKED is -.90 and SUBSTITUTED -.10. Confidence, bounded affinity, and
90-day decay at profile construction also apply. SHOWN and OPENED create no
preference affinity and no bandit reward.

Strong LIKE promotion is IMPROVED in the controlled comparison. Single-event
tests retain distinct confidence-adjusted affinities (.17/.05/.10/.16 for
like/save/actual/repeated actual use) and flag insufficient evidence.
Synthetic actual-use events test semantics only; they are not real meal logs.
The feedback endpoint continues to require the separate actual-meal contract.

Positive preference can nevertheless overpower repetition controls; the
diversity stress result below fails the no-runaway-repetition requirement.

## Negative Feedback Behavior

DISLIKED contributes negative owner-private preference evidence; strong-DISLIKE
demotion is IMPROVED. Existing focused API/store-contract tests preserve durable
event identity and idempotency; fresh live PostgreSQL durability is not claimed.

REJECTED:DO_NOT_LIKE has explicit negative affinity -.85.
REJECTED:NOT_TODAY and REJECTED:INGREDIENT_UNAVAILABLE contribute zero durable
dish-dislike evidence. Unavailable/correction feedback follows the existing
eligible staging catalog-gap route; personal corrections remain personal.

However, NOT_TODAY produces no temporary/contextual ranking effect in the
frozen path. A neutral profile and a NOT_TODAY profile produce identical IDs
and scores. Its timestamp/reason alone does not implement a temporary penalty.
A generic repeat penalty from exposure is not a NOT_TODAY-specific effect.
Unavailable evidence is not proven to filter later candidate availability;
that is not converted into permanent dislike.

## Explicit Request Precedence

REGRESSED. With interpreted current intent from “Tôi muốn ăn gà hôm nay”,
the valid requested chicken dish loses to a strongly liked fish alternative.
The exact-dish test also reproduces the failure.

Required ordering is `current explicit request > learned preference >
diversity/repetition penalty`, subject to hard constraints. The implementation
only clears repeat penalties for an exact dish-title match; it does not give
current intent precedence over preference scores. A learned cuisine or protein
preference cannot be treated as satisfying the user's present request.

An explicit fish request with a fish allergy still excludes fish in focused
regression. N3.3 does not change request parsing, ranker logic, or weights.

## Diversity

A simple recent-dish scenario is IMPROVED, with diversity component change
+.70. That local success does not survive stronger personalization pressure.

In 20 deterministic synthetic stress contexts with two valid dishes/proteins,
five strong fish likes produce fish at every adaptive top-1. A synthetic
non-repeat reference alternates the available dishes:

| Concentration across stress top-1 outputs | Synthetic reference | Adaptive |
| --- | ---: | ---: |
| Most common dish share | .50 | 1.00 |
| Most common main protein share | .50 | 1.00 |
| Unique dishes | 2 | 1 |

This is a concrete collapse counterexample, not a scientific ideal diversity
threshold or an estimate from 20 real users. Repetition controls remain in the
code, but their bounded penalty does not guarantee rotation.

Top-k dish/protein/cuisine coverage and concentration are stored per comparison.
Recipe-family metadata is unavailable. Missing cuisine/protein features are
reported as missing coverage, not fabricated categories or zero concentration.
The current `features_for` protein heuristic searches tokens in canonical IDs;
production protein coverage requires separate scrutiny.

`DIVERSITY_MAJOR_REGRESSION = YES` applies to this development stress failure.
No real-user concentration metric is available.

## Cold Start

No-feedback profiles contain no invented evidence. Very-little-feedback
profiles remain bounded and signal insufficient evidence.

Baseline fallback is nevertheless not preserved: all three canonical
no-feedback contexts change top-1 under the adaptive scoring formula. The
synthetic cold-start comparison also changes identity. That is not evidence
of user benefit and does not satisfy a strict baseline-fallback requirement.
The evaluator reports NOT_APPLICABLE when preference ground truth is absent,
rather than calling such changes IMPROVED or falsely UNCHANGED.

## Stale / Conflicting Evidence

An active confirmed explicit preference overrides conflicting inferred history;
the controlled conflict-demotion case is IMPROVED. A temporary confirmed fact
expires at the fixed replay clock, and the neutral ordering is restored.

Two requirements remain unsatisfied:

- Five LIKE events from 60 days earlier overpower one current DISLIKE:
  resulting affinity is still +1.0. Recent explicit feedback is added to older
  evidence; it does not necessarily take precedence.
- Stored preference affinity is +1.0 both now and 365 days later without a
  rebuild. The SQL reader returns stored affinity/confidence and
  `affinity_for` does not re-decay them. A freshly rebuilt single 180-day-old
  LIKE does decay; that does not prove stale durable profiles decay on read.

The fixed replay timestamp and deterministic fixture identities prevent the
evaluation clock and random UUID tie-breaks from changing regression results.
Current explicit intent remains vulnerable as described above.

## Portion Personalization

Two synthetic PORTION_CORRECTED observations, 220 g and 240 g, produce a
230 g private median and a preferred scale of 1.15 against a 200 g serving.
The existing fitter returns FIT within its bounds. Canonical candidate
content is unchanged; the other owner's prior is absent. Corrections are
not relabelled ACTUALLY_CONSUMED.

Existing focused tests verify correction idempotency, private prior storage,
and no actual-meal side effect. Production integration of a prior into
ranking's caller-supplied `portion_fit_quality` is not established by these
component tests. No actual-user portion improvement is claimed. Stored
comparison portion scores are compatibility inputs, not measured consumption.

## Shadow Bandit Observability

The dedicated development endpoint logs policy version, candidate-set IDs and
fingerprint, shadow choice, delivered choice, and recommendation-event binding.
The candidate-set digest occupies `context_fingerprint` in the policy log;
the exposure record's context fingerprint has different semantics.

Separate baseline-top and adaptive-top fields are absent. The normal chat
delivery helper records a single canonical candidate without the same full
bandit comparison log. Thus N3.2.1's closed observability contract does not
establish N3.3 comparison coverage on every delivery.

The new offline comparison artifact includes separate A/B/bandit identities,
policy versions and fingerprint; outcome binding is null because no genuine
bound outcome was available. This does not amend frozen SQL persistence.

Two additional source-audit limitations are relevant:

- Existing outcome updates bind by recommendation-event ID, while the bandit
  scorer credits `selected_candidate_id`, the shadow choice. If that choice
  differs from the delivered candidate, the delivered outcome is not evidence
  of the shadow candidate's reward.
- The shadow-log reader is a global recent-log pool, not owner-filtered.
  It must not become an owner-personalized or production control path.

The frozen bandit reward table explicitly maps LIKE .8, SAVE .35, DISLIKE -.8,
REJECTED -.45, and actual/repeated consumption 1.0; its REJECTED reward does not
distinguish reasons. Raw events and reasons remain separate in N3.3.
These deterministic logs have no validated randomized policy/propensity.
Numeric 1.0 fields from deterministic decision objects are not inferred
propensities.

```text
COUNTERFACTUAL_POLICY_EVALUATION = NOT_SUPPORTED
```

No IPS/DR estimates, engagement uplift, or causal claims are made.

## Privacy

The N3.3 comparison boundary rejects foreign preference profiles, foreign
recommendation memory, and foreign personal candidates. Existing owner-bound
API feedback tests and scoped catalog-gap tests pass. The portion probe confirms
other owners are unaffected. The read-only collector emits aggregates only,
never credentials, owner IDs, preference values, health, goals, weight, or chat.

```text
CROSS_USER_PREFERENCE_LEAK = 0
PRIVATE_HEALTH_DATA_GLOBAL_PROMOTION = 0
GLOBAL_CATALOG_FROM_RAW_PERSONAL_DATA = 0
```

These zeroes describe the executed scoped development checks and N3.3 changes,
not a live audit of inaccessible records. The pure frozen ranker relies on its
caller to supply owner-bound state; the new evaluator enforces that boundary.
Global shadow-bandit history is the separate limitation above. No raw private
state was exported or promoted.

## Hard Constraints

```text
ALLERGY_VIOLATIONS = 0
RESTRICTION_VIOLATIONS = 0
SAFETY_VIOLATIONS = 0
INVALID_CANONICAL_REFERENCES = 1
PREFERENCE_OVERRIDES_HARD_CONSTRAINT = 0
```

The 12 primary scenarios and 170 canonical candidate evaluations have no
detected hard violation. Additional focused cases reject revoked candidates,
missing nutrition, incomplete mappings, negative nutrients, and an explicitly
requested allergenic dish despite positive preference evidence.

The nonzero reference count comes from one separately labelled development
probe: a mapping retains status EXACT but its canonical ID is changed to an
unknown ID. The frozen ranker's quality gate accepts it; the independent N3.3
registry check detects it. This is a ranker-boundary validation weakness, not
evidence that a production canonical catalog row was corrupted or that an
invalid dish was delivered to a real user. Upstream canonical mapping normally
supplies valid references, but that dependency is insufficient for claiming
the requested zero-violation gate passed.

Consequently `HARD_CONSTRAINT_REGRESSION = YES` and rollout remains NO.
“Regression” here means failure against N3.3's required gate, not a ranking
change introduced during this evaluation.

## Development Regression

The 12 required `N3_3_SHADOW_DEVELOPMENT` scenarios were executed and stored.
All are `SYNTHETIC_DEVELOPMENT`, separate from observed-user metrics.

| Scenario | Relative objective comparison | Requirement finding |
| --- | --- | --- |
| Strong like | IMPROVED | Preferred candidate promoted |
| Strong dislike | IMPROVED | Disliked candidate demoted |
| NOT_TODAY | NOT_APPLICABLE | No permanent dislike; temporary effect missing |
| Cold start | NOT_APPLICABLE | No fabricated evidence; baseline fallback not preserved |
| Conflicting preferences | IMPROVED | Active confirmed fact wins; recent feedback probe still fails |
| Explicit current request | REGRESSED | Current valid chicken request loses to learned fish preference |
| Diversity pressure | IMPROVED | Basic rotation passes; 20-context stress separately REGRESSED |
| Allergy conflict | UNCHANGED hard-valid top-1 | Allergic candidate excluded |
| Diet restriction conflict | UNCHANGED hard-valid top-1 | Vegetarian candidate retained |
| Portion correction | UNCHANGED ordering | Private bounded prior and unchanged canonical serving |
| Candidate unavailable | NOT_APPLICABLE | No permanent dislike; scoped gap evidence |
| Stale preference | NOT_APPLICABLE | Rebuild decay works; stale stored-state probe fails |

NOT_APPLICABLE is deliberate when no objective ranking preference is supplied.
For the unchanged hard/portion cases, the stored overall quality status is
NOT_APPLICABLE; the table's UNCHANGED describes the measured valid top-1.
Tests of defect detection pass while these product requirements fail.

Fresh focused verification:

```text
Combined N3.3 + N3.2 intelligence + N3.2.1 trusted feedback:
38 passed, 14 pre-existing JWT development-key warnings, 2.34s

Final N3.3 after adding four invalid-candidate probes:
27 passed, 0 warnings, 0.40s
```

This covers 42 distinct focused tests across the two runs (27 final N3.3 and
15 unchanged companion tests), not a claim of a fresh combined 42-test command.
The combined run used the three named files only. SQL live integration was not
rerun successfully; historical N3.2.1 SQL evidence remains historical.
No unrelated full suite or browser test was run.

Reproduction from `apps/backend` with the repository Python environment:

```text
python scripts/evaluate_n3_3_shadow.py inventory
python scripts/evaluate_n3_3_shadow.py development
python scripts/evaluate_n3_3_shadow.py durable
python -m pytest tests/test_n3_3_adaptive_ranking_shadow_evaluation.py -q
```

The runner emits JSON and performs no filesystem/SQL writes. Results of this
execution were saved under `validation/n3_3`.
[Isolation and check evidence](../../apps/backend/validation/n3_3/n3-3-isolation-and-checks-v1.json)
contains commands, counts, frozen hashes and final flags. The set is not an
acceptance benchmark and has no scientific acceptance threshold.

## Observed Usage Limitations

No observed exposure count, LIKE/DISLIKE/SAVE/REJECT rate, repeat rate,
preference agreement, diversity concentration, catalog-gap rate or
portion-correction frequency is reported. Genuine durable records could not be
read; origin verification and complete pre-exposure snapshots are also needed.
The metric helper's unavailable-rejection rate is only a catalog-gap proxy and
cannot represent all retrieval gaps. Portion-correction frequency uses unique
corrected exposures over exposures, with raw correction events counted separately.

```text
INSUFFICIENT_REAL_USAGE_FOR_ROLLOUT_DECISION = YES
```

This indicates insufficient accessible evidence, not a fabricated finding that
actual usage is zero. There is no justified sample-size pass.
All N3.3 numbers are product-engineering development comparisons, never
research A/B/C, offline-v1-636, sealed benchmark, oracle, or thesis results.

## Rollout Readiness

Rollout is NO because the canonical-reference gate fails, explicit intent loses,
the stress case collapses diversity, contextual negative feedback and stale
precedence are incomplete, strict cold-start fallback is missing, genuine usage
is unavailable, and full observed A/B capture is absent. Passing the evaluator
tests does not satisfy the requirement that development product regressions pass.

Unsupported counterfactual evaluation is a limit on causal inference, not by
itself proof a future observational product rollout could never be justified.
Any controlled rollout still requires a separate explicit user decision.

```text
N3_3_SHADOW_EVALUATION_READY = NO
HARD_CONSTRAINT_REGRESSION = YES
PRIVACY_REGRESSION = NO
DIVERSITY_MAJOR_REGRESSION = YES
COUNTERFACTUAL_POLICY_EVALUATION = NOT_SUPPORTED
INSUFFICIENT_REAL_USAGE_FOR_ROLLOUT_DECISION = YES
ADAPTIVE_RANKING_ROLLOUT_READY = NO
PRODUCTION_ADAPTIVE_RANKING_READY = NO
CANONICAL_AUTO_PROMOTION_READY = NO
N3_2_1_REMAINS_CLOSED = YES
```

The evaluation tooling and report are delivered; N3_3_SHADOW_EVALUATION_READY
stays NO because complete observed comparison coverage and the required
behavioral gates are not established.

## Remaining Risks

- Ranker changes for explicit intent, stale evidence, contextual rejection,
  canonical-reference validation and repetition need a new frozen baseline;
  this evaluation did not tune them.
- Genuine usage provenance, reporting denominators, exposure windows and a
  product sufficiency decision remain undefined/unverified.
- Future comparison capture must preserve event identity, owner scope and
  pre-exposure state without changing frozen N3.2.1 migrations.
- Shadow reward attribution and the global log pool require resolution before
  any bandit-controlled experiment.
- Portion-prior integration, metadata coverage, availability behavior and
  longer natural usage sequences remain unproven by this focused set.
- PostgreSQL access is still unavailable. Historical SQL success does not
  replace a fresh observed-data inventory.

Production adaptive ranking and canonical auto-promotion remain disabled.
N3.2.1 remains closed. Work stops at this shadow evaluation.
