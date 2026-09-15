# N3.2.1 Final No-Browser Closure Reconciliation

## Closure policy

N3.2.1 closes the trusted development/shadow recommendation-feedback path. It
does not release adaptive ranking to production or authorize a canonical recipe
write.

Browser automation is not a closure input. This reconciliation uses the recorded
focused 33/33 backend evidence, migration/source evidence, and focused Flutter
model/widget evidence. No browser, Playwright command, Flutter web build,
locator probe, or broad test suite was used.

\`N3_2_1_CLOSED\` depends only on the non-browser gates below.

## Evidence used

The recorded focused backend command passed **33/33** tests (with 14
pre-existing development JWT-key-length warnings):

\`\`\`text
C:\\Project\\NCKH\\.venv-e4-py310\\Scripts\\python.exe -m pytest \\
  tests/test_n3_2_1_trusted_shadow_feedback.py \\
  tests/test_n3_2_1_feedback_postgres_live.py \\
  tests/test_adaptive_recommendation_intelligence_n3_2.py \\
  tests/test_adaptive_nutrition_n3.py -q
\`\`\`

It covers PostgreSQL migration/schema, durable read-back/reload, transaction
rollback, idempotency, owner boundaries, learning, portion and catalog-gap
evidence, shadow-bandit observability, and hard constraints. It is recorded
evidence and was not rerun.

The focused Flutter contract command passed **3/3**:

\`\`\`text
flutter test test/widgets/recommendation_feedback_bar_test.dart
\`\`\`

It covers exact server-issued identity parsing, feedback UI/action dispatch, and
the failed-submit path. A failed API callback remains retryable, displays an
error, and never displays an accepted state.

## Non-browser closure gates

| Gate | Status | Supporting tests/files | Behavior proved |
| --- | --- | --- | --- |
| \`N3_2_1_SQL_INTEGRATION_READY\` | PASS | Migration \`017_adaptive_feedback_persistence_n3_2_1.sql\`; \`test_postgres_migration_durable_idempotency_readback_and_owner_boundary\`; \`test_postgres_portion_catalog_and_rollback_are_transactional\` in \`apps/backend/tests/test_n3_2_1_feedback_postgres_live.py\` | PostgreSQL migration/schema, insert and exact owner read-back, concurrent idempotency, fresh-store reload, personal portion evidence, and atomic rollback. |
| \`N3_2_1_API_INTEGRATION_READY\` | PASS | \`test_feedback_is_owner_bound_idempotent_and_never_creates_consumption\`; \`test_trusted_delivery_has_one_safe_structured_chat_contract\` in \`apps/backend/tests/test_n3_2_1_trusted_shadow_feedback.py\`; \`apps/backend/modules/nutrition/adaptive_router.py\`; live SQL tests above | Authenticated principal is the owner authority. Delivery emits exact event/candidate/policy IDs; feedback requires them, is idempotent and owner-bound, denies foreign access, reads back the result, and updates through the configured durable-store contract. No client \`user_id\` is authoritative. |
| \`N3_2_1_FLUTTER_CONTRACT_READY\` | PASS | \`apps/mobile/test/widgets/recommendation_feedback_bar_test.dart\` (3/3 current pass); \`apps/mobile/lib/features/chat/screens/chatbot_screen.dart\`; \`apps/mobile/lib/services/backend_api_service.dart\` | Structured \`ActionItem\` details retain exact event/candidate/policy IDs. UI renders explicit LIKE/DISLIKE. The screen forwards the exact IDs with a stable retry key to the authenticated API. Failed API calls show no false success, and feedback invokes no meal-log path. |
| \`N3_2_1_FEEDBACK_LOOP_READY\` | PASS | \`test_dislike_changes_future_ranking_but_not_today_and_hard_gate_wins\`; \`test_portion_correction_updates_private_prior_not_actual_meal_state\`; \`test_staging_corrections_create_only_deidentified_catalog_gap_evidence\`; \`test_feedback_taxonomy_is_strength_aware_and_explicit_conflict_wins\`; \`test_hard_constraints_filter_before_preference_and_rejection_is_contextual\`; \`test_portion_learning_uses_actual_observations_and_only_nudges_fitter\` | Explicit feedback persists, reconstructs private state after reload, and is consulted by later ranking. \`NOT_TODAY\` is contextual; hard constraints win; portion correction updates only the personal prior; feedback creates no consumption. |

## Gate rationale

Migration 017 has an owner-scoped idempotency boundary and durable feedback,
portion, catalog-gap, and recommendation-event evidence. The recorded live
PostgreSQL tests use separate stores and fresh read-back, ruling out an
in-process cache; rollback prevents partial success.

The router derives identity from the authenticated principal. It requires the
exact \`recommendation_event_id\`, \`candidate_id\`, and policy version, with no
latest-card fallback. The mobile screen refuses eligibility until all three
values exist, forwards them unchanged, and derives
\`<recommendation_event_id>:<event_type>\` for idempotent retry. Its API client
throws on non-2xx, and the feedback widget acknowledges only after that Future
succeeds.

The deterministic feedback loop is:

\`\`\`text
recommendation A
  -> explicit owner-scoped feedback
  -> durable feedback/evidence rows
  -> reconstructed private preference or portion state after reload
  -> later shadow ranking consults that state
\`\`\`

Preference is soft evidence: it never bypasses allergy, dietary restriction, or
safety gates. Portion feedback changes a private prior, not canonical serving.
Eligible corrections may create only de-identified staging catalog-gap evidence.
None of these feedback events records actual meal consumption.

## Hard invariants

| Invariant | Status | Supporting evidence |
| --- | --- | --- |
| \`SHOWN_AS_CONSUMED = 0\` | PASS | \`test_trusted_delivery_has_one_safe_structured_chat_contract\`; \`test_recommendation_memory_is_not_consumption_and_repository_stays_private\` |
| \`OPENED_AS_CONSUMED = 0\` | PASS | \`test_preference_exposure_has_no_weight_and_old_feedback_decays\`; separate recommendation/feedback/meal contracts |
| \`FEEDBACK_CREATED_MEAL_LOG = 0\` | PASS | \`test_feedback_is_owner_bound_idempotent_and_never_creates_consumption\`; portion-correction test |
| \`DOUBLE_LEARNING_FROM_RETRY = 0\` | PASS | PostgreSQL concurrent-idempotency/read-back test; routed-feedback idempotency test |
| \`CROSS_USER_FEEDBACK = 0\` | PASS | PostgreSQL owner-bound read-back test; routed foreign-owner 404 assertion |
| \`PREFERENCE_OVERRIDES_ALLERGY = 0\` | PASS | later-ranking hard-gate test; \`test_allergen_and_prompt_injection_are_hard_gates\` |
| \`PREFERENCE_OVERRIDES_RESTRICTION = 0\` | PASS | hard-constraints-first test; \`test_dietary_restrictions_are_checked_from_canonical_tags_or_fail_closed\` |
| \`PREFERENCE_OVERRIDES_SAFETY = 0\` | PASS | hard-constraints-first test and N3 hard-gate evidence |
| \`PRIVATE_DATA_GLOBAL_LEAK = 0\` | PASS | \`test_recommendation_memory_is_not_consumption_and_repository_stays_private\`; \`test_private_data_never_enters_global_aggregate_and_blocked_source_is_rejected\` |
| \`LLM_DIRECT_CANONICAL_WRITE = 0\` | PASS | \`test_personal_memory_staging_feedback_and_promotion_stay_scoped_and_disabled\`; fail-closed canonical writer |
| \`CANONICAL_AUTO_PROMOTION = 0\` | PASS | \`test_n3_migration_and_source_registry_keep_canonical_writes_disabled\` |
| \`BANDIT_CONTROLS_PRODUCTION = 0\` | PASS | \`test_corrections_gap_queue_bandit_and_replay_are_shadow_only_and_auditable\` |
| \`RESEARCH_CORPUS_MUTATION = 0\` | PASS | \`test_development_scenario_set_is_not_a_frozen_research_dataset\`; no frozen research asset is a feedback-write target |

## Historical browser fields — non-gating

These fields are retained only for provenance. They do not determine closure and
are not blockers:

\`\`\`text
BROWSER_RUNTIME_READY = YES
BROWSER_NAME = Brave
BRAVE_LOCATOR_PROBE_READY = NO
LIVE_E2E_FAILURE_CLASS = PLAYWRIGHT_HARNESS
N3_2_1_PRODUCT_E2E_READY = NO
AUTOMATED_BROWSER_E2E = NOT_USED_BY_DESIGN
\`\`\`

## Final status

\`\`\`text
TRUSTED_SHADOW_DELIVERY_READY = YES
RECOMMENDATION_FEEDBACK_PERSISTENCE_READY = YES
PERSONAL_PREFERENCE_FEEDBACK_LOOP_READY = YES
PORTION_FEEDBACK_LOOP_READY = YES
CATALOG_GAP_FEEDBACK_READY = YES
SHADOW_BANDIT_OBSERVABILITY_READY = YES
N3_2_1_SQL_INTEGRATION_READY = YES
N3_2_1_API_INTEGRATION_READY = YES
N3_2_1_FLUTTER_CONTRACT_READY = YES
N3_2_1_FEEDBACK_LOOP_READY = YES
AUTOMATED_BROWSER_E2E = NOT_USED_BY_DESIGN
N3_2_1_CLOSED = YES
PRODUCTION_ADAPTIVE_RANKING_READY = NO
CANONICAL_AUTO_PROMOTION_READY = NO
\`\`\`
