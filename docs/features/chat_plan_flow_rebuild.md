# Chat / Meal / Workout / Plan rebuild

## Authority and boundaries

`PlanApplicationService` is the application boundary for planned content. It
uses PostgreSQL Plan V2 previews and immutable revisions; it never writes a
meal-consumption or workout-completion observation. `MENU`, `WORKOUT`, and
`COMBINED_PLAN` are the public artifacts. A combined revision contains its
canonical meal and workout items directly, with component revisions retained
only as provenance.

Firestore remains the authority for actual diary/profile observations. Flutter
now exposes `PlannedMealProjection` and `PlannedWorkoutProjection` separately
from the actual `MealModel` and `ExerciseModel` collections. Marking a planned
item as eaten/completed must create an observation with an optional source
reference; it must not alter a Plan revision.

Legacy `/plans` records are an authenticated read-only archive. With
`LEGACY_PLAN_READ_ONLY=true` all legacy create/item/check-in mutations return
`410 LEGACY_PLAN_MUTATION_DISABLED`.

## API flow

1. `POST /api/plan-v2/previews` constructs exactly one MENU, WORKOUT, or
   COMBINED_PLAN preview and persists it durably.
2. `POST /api/plan-v2/actions/save` (the former `/plans/save` alias remains
   compatible) requires the exact `plan_id`, `revision_id`,
   content hash, and idempotency action id. It never invokes an engine again.
3. `POST /api/plan-v2/plans/{plan_id}/revisions` accepts a typed patch against
   the exact base revision. It creates a durable preview; save remains an
   explicit second action.
4. Lifecycle calls use expected revision numbers. Activation rejects an
   overlapping active content claim with `ACTIVE_SCHEDULE_CONFLICT` unless the
   caller explicitly requests conflict replacement.
5. Owner-scoped change events record actor, surface, operation, before/after
   payload, reason, and correlation id. Preview events refer to their saved
   base revision and retain the prospective revision in `after_payload`; after
   exact save the immutable revision FK is available.
6. `POST /api/plan-v2/plans/{plan_id}/attachments` performs an explicit,
   idempotent ownership transfer of a saved standalone MENU or WORKOUT into a
   COMBINED_PLAN. It preserves logical item IDs, creates a new direct-content
   combined revision, supersedes the source revision, updates active claims
   atomically, and records both transfer-in and transfer-out events.

`020_plan_flow_rebuild.sql` is idempotent and adds artifact kinds, durable
pending actions, change events, and active content claims.
`021_plan_patch_preview_idempotency.sql` adds the durable idempotency ledger
for typed revision previews. Pending actions are
claimed atomically and bound to plan, revision, and content hash. The
orchestrator restores a durable Plan confirmation after a restart and releases
the claim after a failed identity check.
`022_plan_attach_transfer.sql` adds the durable attachment action ledger.

## Routing and recommendation safeguards

`TurnIntentDecision` is the common typed decision contract used in tool
selection. It carries primary and secondary intents, health overlay, negated
actions, write policy, clarification state, confidence, reason codes, and
model version. The deterministic fallback recognizes meal suggestion, menu,
workout, combined plan, lifecycle/edit, actual observation, profile, health,
and general-wellness intents. Negated create/save/log actions are withheld
from the tool catalog. The development corpus covers diacritics, typos,
negation, multi-domain plans, health overlays, logging, profile updates and
clarification. The existing restricted JSON scope judge remains the
low-confidence/conflict safety boundary.

Dish selection continues catalog-first. Hard allergy/dietary/safety filters
run before deterministic ranking. Recent dish IDs and owner/session exposure
counts penalize repeated catalog candidates; they never relax a hard safety
constraint. Durable owner exposure hydration and a sealed real-SLM evaluation
are intentionally not claimed complete here.

## Evidence and release indicators

Focused backend evidence includes the Plan engine, plan tools, orchestrator,
pending-action, scope, typed intent, legacy route, and PostgreSQL Plan V2 API
suites. The live PostgreSQL test covers exact preview/save read-back, owner
isolation, lifecycle conflict behavior, a typed patch preview, audit events,
and idempotent standalone-to-combined ownership transfer. Flutter targeted
provider and Plan UI tests verify planned/actual projection separation,
history display, explicit save, and conflict replacement affordances; analyzer
is clean. Final local verification used the pinned Python 3.10 toolchain:
`1275 passed, 10 skipped` for the backend suite, and `220 passed` for the
Flutter suite. The three frozen V3 input/oracle/threshold SHA-256 values match
their freeze manifest; the implementation-baseline comparison is expected to
be false because this rebuild intentionally changes implementation sources.

The following is intentionally conservative. A `YES` requires the stated
gate, not just structural code review.

| Indicator | Value | Evidence / limitation |
| --- | --- | --- |
| `SEMANTIC_ROUTING_READY` | `NO` | No sealed holdout or real SLM runtime qualification yet. |
| `HEALTH_ROUTING_READY` | `NO` | Overlay fixtures exist, but no sealed recall measurement. |
| `FALSE_AMBIGUITY_RATE` | `NOT_MEASURED` | Must be measured on a sealed holdout, not development cases. |
| `MENU_PLAN_CONFUSION_FIXED` | `PARTIAL` | Typed menu/workout/combined contract and tests exist; no sealed corpus gate. |
| `WORKOUT_PLAN_CONFUSION_FIXED` | `PARTIAL` | Typed workout contract and tests exist; no sealed corpus gate. |
| `MEAL_RECOMMENDATION_DIVERSITY_READY` | `PARTIAL` | Deterministic recent/exposure penalties are implemented; 10-turn owner-persisted evaluation is pending. |
| `PLAN_PREVIEW_FLOW_READY` | `YES` | Durable preview API with authoritative payload and read-back tests. |
| `PLAN_EXPLICIT_SAVE_READY` | `YES` | Exact identity/hash/idempotent SQL save; no regeneration. |
| `PLAN_REGENERATED_ON_SAVE` | `NO` | Save reads the durable preview; it does not call an engine. |
| `PLAN_MENU_WORKOUT_SINGLE_SOURCE` | `PARTIAL` | New API/chat/mobile path uses Plan V2; archive remains readable by design. |
| `PLAN_LINKED_EDIT_SYNC_READY` | `PARTIAL` | Typed previews plus atomic menu/workout attachment transfer are implemented and audited; full authenticated menu/workout screen E2E remains pending. |
| `EDIT_ACTOR_AUDIT_READY` | `YES` | SQL change events capture actor, surface, operation and before/after state. |
| `PLANNED_ACTUAL_SEPARATION_READY` | `YES` | Flutter projections stay separate; actual observations carry optional Plan source references. |
| `PENDING_ACTION_TARGET_MUTATION` | `0` | Exact target identity is stored and verified before completion in focused tests. |
| `FALSE_POSITIVE_WRITE_INTENT` | `NOT_MEASURED` | Requires the sealed semantic holdout. |
| `HEALTH_SAFETY_CRITICAL_MISS` | `NOT_MEASURED` | Requires the sealed semantic holdout. |
| `FULL_E2E_FLOW_READY` | `NO` | Full authenticated mobile/browser E2E and sealed routing gates remain outstanding. |
| `FROZEN_RESEARCH_ARTIFACTS_UNCHANGED` | `YES` | Rebuild diff is outside frozen research/canonical evaluation artifacts. |

Production cutover must remain disabled until the holdout thresholds and all
hard gates are run successfully. Do not promote adaptive N3/N3.2 or external
recipe data into canonical candidates as part of this work.
