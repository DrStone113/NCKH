# PLAN SYSTEM REBUILD AUDIT

> Scope: current application code in `apps/backend` and `apps/mobile`, inspected on 2026-09-16. This audit does not change production code, migrations, research/frozen artifacts, git history, or remote state.
>
> Method: trace reachable call paths rather than infer from names or historic reports. The Docker daemon was unavailable during this audit, so no live database contents/schema state were queried. A focused backend test collection was attempted but could not start because the active Python installation lacks `pydantic`, `fastapi`, and `sqlalchemy`; no test result below is presented as fresh runtime qualification.

## 1. Current Architecture

There are four independently reachable plan-like systems. They overlap in user-facing terminology but do not share one authoritative lifecycle or payload contract.

```text
1. Legacy nutrition + workout bundle
Flutter Chat quick action
  -> BackendApiService.createLongTermPlan()
  -> POST /plans
  -> PlannerAgent + plan_tools
  -> plans + plan_items
  -> legacy active-plan card / plan_detail_bottom_sheet

2. Versioned Plan V2
Flutter PlanProvider / PlanList / PlanDetail
  -> BackendApiService /api/plan-v2/*
  -> modules/plans/v2_router.py
  -> PlanSqlRepository
  -> plan_v2_plans + plan_v2_revisions + plan_v2_items

3. Chat Plan V2 tool path
WebSocket chat
  -> ToolDispatcher injects PlanRuntimeContext
  -> build_*_plan / revise_plan / save_plan
  -> PlanEngine memory repository (+ optional plan_v2_previews)
  -> structured chat_messages + in-memory PendingUserAction

4. Standalone E4 workout plan
Chat personalized-workout card or /workouts/*
  -> WorkoutIntegrationService
  -> workout_plans_e4 + workout_results_e4
```

`main.py` mounts both `/plans` and `/api/plan-v2`, while the server tool catalog registers Plan V2 tools whenever `PLAN_TOOL_MODE != off`. The checked-in default remains `shadow` (`config.py` and `.env.example`); `apps/backend/.env` does not override it.

### Status of major components

| Component | Current status | Notes |
|---|---|---|
| `services/plan_engine/contracts.py` | Useful foundation | Strong immutable identity, canonical hash, owner, date, planned-item, and validation concepts. |
| `PlanSqlRepository` and migrations 010-013/018 | Useful but incomplete product persistence | Transactions, owner scope, idempotency, read-back, overlap exclusion, and durable previews are implemented. |
| `/api/plan-v2` | Partially usable API | Reads/save/lifecycle work for persisted V2 data; only direct nutrition draft creation is exposed; no revision-history or revise endpoint. |
| `PlanProvider` / Plan library / Plan detail | Partially usable presentation | Repository-backed V2 list/read and lifecycle buttons exist. Creation/edit/revision history/deep links are missing. |
| Chat Plan V2 tool integration | Split rollout path | It creates structured cards and pending confirmations, but default `shadow` saving is process-memory state, not the library's persisted source. |
| Legacy `/plans` + `PlannerAgent` | Live legacy path | Chat quick actions still create it; it owns a different schema/status model and combines planned items with completion/check-in behavior. |
| E4 workout plans | Live separate domain | Correctly separates prescribed workout from actual results, but it is not coherently linked to a persisted multi-day Plan V2 revision. |

## 2. Current Data Flow

### A. Chat generates a versioned nutrition/workout plan

```text
User
  -> AIChatProvider WebSocket
  -> ChatGateway authenticates bearer token
  -> ToolDispatcher injects owner/session/context
  -> plan_v2.build_nutrition_plan or build_workout_schedule
  -> PlanEngine builds an in-memory PlanRevision
  -> optional PlanSqlRepository.put_preview (30-day non-authoritative preview)
  -> AgentOrchestrator stores versioned_plan in chat_messages.structured_data
  -> VersionedPlanCard -> PlanDetailScreen
```

For a ready draft, `AgentOrchestrator` asks `PendingUserActionStore` to create a save action. The store marks only the process-memory revision `PENDING_CONFIRMATION`. On a chat confirmation, it calls the exact `save_plan` tool with IDs and content hash.

With the current default `PLAN_TOOL_MODE=shadow`, `save_plan` calls `MemoryPlanRepository.save` and returns `write_status=SHADOW_SAVED`. It deliberately does not persist a `plan_v2_revisions` record. Therefore the Plan Library, which calls `GET /api/plan-v2/plans`, cannot see that chat-saved plan after a normal default-mode save.

### B. Chat quick action creates a different active plan

```text
User taps 7/14/30-day quick action in ChatbotScreen
  -> _createPlanFromQuickAction(days)
  -> BackendApiService.createLongTermPlan
  -> POST /plans
  -> PlannerAgent.createLongTermPlan
  -> legacy plans row (immediately active) + legacy plan_items
  -> ChatbotScreen._activePlan
  -> showPlanDetailBottomSheet
```

The legacy planner creates a nutrition header, daily meals, and its own workout schedule. It does not use the Plan V2 revision API, and its workout prescription is not the E4 multi-day plan wrapper.

### C. V2 Library and daily UI reads

```text
Home / Nutrition / PlanListScreen
  -> PlanProvider.loadForUser
  -> PlanHistoryRepository.loadForUser
  -> GET /api/plan-v2/plans
  -> PlanSqlRepository.list_owned
  -> newest persisted revision for each V2 plan
  -> PlanProvider snapshots
  -> PlanListScreen / PlannedDayPlanSection / PlanDetailScreen
```

This is the correct V2 read path. Despite a stale method/comment name, `PlanListScreen._loadPlansFromChatHistory()` actually calls `PlanProvider`, not chat history. `PlanSnapshot.fromChatMessage()` is only a recovery/parser helper and has no current call site.

### D. Chat's active-plan card is a hybrid

```text
ChatbotScreen._loadActivePlan
  -> BackendApiService.getActivePlan(userId)
  -> GET /api/plan-v2/plans/active/NUTRITION
  -> if no V2 result: GET /plans/{userId}/active
  -> showPlanDetailBottomSheet (legacy renderer/mutations)
```

The V2 presentation has `period_start`, `period_end`, `days`, `plan_item_id`, and `lifecycle_status`; it does not have the legacy `duration_days`, `goal`, top-level `items`, or legacy `completed` fields expected by `plan_detail_bottom_sheet.dart`.

### E. E4 workout path

```text
PersonalizedWorkoutCard
  -> POST /workouts/plans/{e4_plan_id}/save
  -> workout_plans_e4
  -> explicit actual result
  -> POST /workouts/plans/{e4_plan_id}/results
  -> workout_results_e4
```

This path is separate from a Plan V2 workout revision. A V2 workout item contains an `e4_workout_plan_id` in JSON, but there is no relational, lifecycle, or result-link contract joining that reference to a persisted V2 parent revision.

## 3. Root Causes

Only issues evidenced in current code are listed.

| ID | Root cause | Files involved | Current behavior | Expected behavior | Severity |
|---|---|---|---|---|---|
| RC-01 | Two active-plan stores are reachable from the same Chat screen and selected with a fallback rule. | `modules/plans/router.py`, `modules/plans/v2_router.py`, `backend_api_service.dart`, `chatbot_screen.dart` | Quick action writes legacy `plans`; V2 lifecycle writes `plan_v2_*`; active read prefers V2 then legacy. Both can exist for one owner. | One product Plan flow selects one authoritative store/contract; legacy data is explicitly historical, not a hidden fallback. | Critical |
| RC-02 | Chat's default save semantics and mobile library's read semantics disagree. | `config.py`, `tools/plan_v2.py`, `pending_user_action.py`, `orchestrator.py`, `plan_history.dart` | Default chat confirmation is `SHADOW_SAVED` in memory; library lists only SQL-persisted V2 revisions. | A successful user-visible save must be durable and appear in the same repository-backed library, or be explicitly labeled as a non-save preview. | Critical |
| RC-03 | One V2 result is rendered/mutated as a legacy plan. | `chatbot_screen.dart`, `plan_detail_bottom_sheet.dart`, `backend_api_service.dart`, `tools/plan_v2.py` | Chat's active V2 nutrition plan opens the legacy bottom sheet; it expects different fields and posts legacy item completion/check-ins. | Route each payload only to its matching typed screen/actions; never send V2 IDs to legacy endpoints. | Critical |
| RC-04 | Rollout/feature flag meaning is split across entry points. | `config.py`, `tools/plan_v2.py`, `modules/plans/v2_router.py` | Tool path respects `shadow/enforced` and forbids enforced chat mode in production; HTTP V2 router persists SQL unconditionally and does not consult the flag. | One explicitly named rollout gate must govern every write path, with a single defined behavior per environment. | High |
| RC-05 | Revision/edit and lifecycle contracts are only partially surfaced. | `contracts.py`, `engine.py`, `lifecycle.py`, `v2_router.py`, `plan_detail_screen.dart` | Engine supports only remove/move/time/duration patches; API exposes no revise endpoint; Flutter exposes no edit action; `COMPLETED` exists in the enum but no HTTP operation/UI command can reach it. | Editing creates a new revision through one service; every supported lifecycle state has one command, transition rule, and UI affordance. | High |
| RC-06 | Nutrition, workout, and combined plans are not a complete common product model. | `engine.py`, `tools/plan_v2.py`, `v2_router.py`, `workout_planner/integration.py` | Nutrition has a direct draft API; workout is chat-only; `COMBINED_HEALTH` has a container method but no tool/API creation path and no child navigation contract. E4 also persists its own standalone plans. | Shared plan envelope with domain-specific items and explicit child links; no duplicate workout persistence/lifecycle. | High |
| RC-07 | Legacy planning conflates plan lifecycle/progress with observations. | `db/init.sql`, `modules/plans/router.py`, `plan_detail_bottom_sheet.dart`, `ai_chat_provider.dart`, `nutrition_provider.dart` | Legacy `plan_items.completed` is toggled; plan check-ins are inserted as `plan_items` with type `exercise`; some client paths attempt completion writes for plan IDs. | Planned item remains planned. Meals, exercise results, weight, and reviews are separate observations, optionally linked explicitly to a plan item. | High |
| RC-08 | The Plan contract lacks the product sections needed for baseline, progress, adjustment and safety. | `contracts.py`, `engine.py`, migrations 010-018 | V2 stores goal/constraints/summary/provenance JSON and validates generation inputs, but has no first-class baseline, progress cadence, adjustment policy/review, or stop-condition records. | The nine required sections must be auditable plan content/policy, not prose or ad-hoc legacy check-ins. | High |
| RC-09 | Revision history and deterministic reference resolution are absent at the product boundary. | `persistence.py`, `v2_router.py`, `plan_history.dart`, `orchestrator.py` | List returns only the newest revision per plan; exact read needs IDs; chat relies on LLM/tool selection for “that plan.” | Revision list/detail and an explicit plan reference token must resolve the exact owner-scoped plan/revision without prose inference. | High |
| RC-10 | Plan state can remain stale across an account transition until a consumer reloads it. | `plan_provider.dart`, `main.dart`, `user_provider.dart` | `PlanProvider.clear()` has no call site; it clears old data only when `loadForUser` is later called with another owner. | Auth state owns/reset plan state immediately; each refresh/read is owner-bound and replacement-safe. | Medium |
| RC-11 | There is no app deep-link route for an exact plan/revision. | `main.dart`, all plan screens | Navigation uses `MaterialPageRoute` with an in-memory plan map only. | A route/URI or equivalent app navigation contract accepts a plan reference and fetches the exact owner-scoped revision. | Medium |
| RC-12 | Clean-schema/bootstrap content lags migration evolution unless migrations run. | `db/init.sql`, migrations 010-013/018, `db/database.py` | `init.sql` defines early V2 shapes; later changes such as the write-action primary key and preview tables are supplied by startup migrations. | Deployment must require all migrations and verify schema version; bootstrap schema should remain synchronized or intentionally minimal. | Medium |

## 4. Broken User Flows

| Required flow | Current result | Assessment |
|---|---|---|
| A. Chat creates nutrition plan -> View plan | Card is structured and viewable. Default chat confirmation is shadow-only; V2 Library does not list it. | Broken as a saved product flow |
| B. Chat creates workout plan -> View plan | Chat can build a V2 workout schedule; no direct workout draft API, no unified persisted E4 parent/child lifecycle, and no active workout card in Chat. | Broken/partial |
| C. Edit plan -> display new revision | Chat engine has a small patch subset only; HTTP and Flutter editor are absent. | Broken |
| D. Save plan | Direct V2 detail can call save if it has a durable preview. Chat confirmation normally reports `SHADOW_SAVED`, not durable product save. | Partial and inconsistent |
| E. Activate plan | V2 detail can activate an already saved persisted revision. Chat card has no lifecycle callbacks; legacy plan is created active. | Partial and inconsistent |
| F. Pause/resume | V2 detail can issue pause/resume. Legacy has no such state; chat card does not expose it. | Partial |
| G. Cancel plan | V2 detail can cancel. Legacy API has no plan cancellation command. | Partial |
| H. Restart -> plan remains | Persisted V2 revisions remain; memory shadow state and in-memory pending action do not. A preview expires after 30 days. | Partial |
| I. Second device same account | Persisted V2 list is owner-scoped and can work. Shadow-only and legacy/V2 fallback state do not form one cross-device product view. | Partial |
| J. Chat says “that plan” | `get_plan` accepts exact IDs, but the product has no durable visible reference token/resolver or selected-plan context contract. | Partial |
| K. Plan does not create actual meal/workout log | V2 model defends this well. Legacy completion/check-in UI writes back to `plan_items`; direct E4 result path is separate. | Partial; legacy violates the desired boundary |

## 5. Source-of-Truth Problems

### Current sources by state

| State | Actual current source | Problem |
|---|---|---|
| Legacy active plan | `plans` + `plan_items` | Still created by quick actions and shown by fallback. Different status/item contract. |
| Persisted V2 plan | `plan_v2_plans`, `plan_v2_revisions`, `plan_v2_items` | Best current candidate for versioned planned state, but only some paths write it. |
| V2 draft | `MemoryPlanRepository` and optionally `plan_v2_previews` | Process memory is not durable. Preview is durable but expires and is deliberately non-authoritative. |
| Pending confirmation | `PendingUserActionStore` memory | Lost on process restart and after TTL; only safe as transient UI command state. |
| Chat card | `chat_messages.structured_data` | Historical presentation/recovery record, not authoritative lifecycle state. |
| Direct E4 workout | `workout_plans_e4` / `workout_results_e4` | Valid own domain, but separate from multi-day Plan V2 wrapper. |
| Flutter `PlanProvider` | In-memory projection of V2 list | Cache/projection only; not a source of truth. |

### Proposed single source of truth

For a rebuilt product Plan, one owner-scoped PostgreSQL Plan aggregate must be the source of truth for saved revisions and lifecycle. The current V2 persistence concepts are the closest reusable foundation; whether the implementation keeps the name `plan_v2_*` or creates a replacement namespace is a migration decision, not an assumption for this audit.

Chat history, Flutter provider, pending actions, cached E4 previews, and deep-link payloads must carry only a `PlanReference` (`plan_id`, `revision_id`, owner-bound content/version information) and must resolve through the same Plan read service. Legacy `/plans` records must become explicitly labeled read-only history during cutover, never an active-plan fallback.

## 6. Backend Problems

1. Both routers are mounted and both are called by active mobile code. The code does not impose an owner-level or global mutual-exclusion rule between legacy `plans.status='active'` and V2 `lifecycle_status='ACTIVE'`.
2. The V2 HTTP router has no `POST /revisions`/edit route, no completed operation, no exact draft read route, and no workout/combined draft route. Its list route returns one newest revision per plan, not revision history.
3. `PlanEngine.revise()` is deliberately limited to remove, move, time and duration. Contract enum values for add/replace/goal/constraint are not implemented by the engine.
4. Tool `save_plan` behaves differently from HTTP `save_plan`: shadow mode saves only memory, whereas HTTP saves SQL regardless of `PLAN_TOOL_MODE`. A user-visible “saved” result therefore depends on entry point.
5. `PendingUserActionStore.create_plan_save_action()` requires the revision to exist in `MemoryPlanRepository`; it cannot recover an already durable preview after a process restart. It is appropriate as a transient confirmation helper, not durable workflow ownership.
6. Legacy `PlannerAgent` is a second nutrition/workout planning algorithm. It creates an active header before the V2 flow and uses legacy `suggest_workout`, whereas the V2 workout schedule delegates to E4.
7. The active legacy check-in endpoint writes a record into `plan_items` as `item_type='exercise'`, mixing progress data with scheduled item storage.

## 7. Database Problems

### Current schema assessment

| Schema | Assessment | Why |
|---|---|---|
| `plan_v2_plans`, `plan_v2_revisions`, `plan_v2_items`, `plan_v2_write_actions` | USEABLE FOUNDATION | Owner scope, immutable content hash, revision ordering, lifecycle validation, ordered items, overlap exclusion, and idempotency exist. |
| `plan_v2_previews` | USEABLE AS TRANSIENT DRAFT STORAGE | Exact owner-scoped, expiring preview supports save-after-restart; it is rightly non-authoritative. |
| Legacy `plans`, `plan_items` | SHOULD_BE_REPLACED AS PRODUCT PLAN STORE | No revision model, only `active/completed/cancelled`, mixes plan item completion/check-in, and serves a separate planner. Preserve only for read-only legacy migration/history. |
| `workout_plans_e4`, `workout_results_e4` | KEEP AS WORKOUT PRESCRIPTION/OBSERVATION DOMAIN | It has explicit idempotency and separates actual results. It needs an explicit integration/link contract with the product Plan, not replacement by a generic plan item. |
| `init.sql` V2 block | NEEDS_MIGRATION DISCIPLINE | It represents an earlier V2 shape; migrations must run on every deployment. Do not rely on a partial bootstrap schema alone. |

### Missing or insufficient schema capability

- No first-class plan baseline/initial assessment snapshot and validation timestamp.
- No typed progress policy, adjustment rule, review/evaluation, or safety/stop-condition records.
- No append-only plan status-event history; current V2 status updates one revision row.
- No revision-history list/selection contract exposed by API.
- No stable cross-domain relation from a plan item/revision to a saved E4 workout plan/result.
- No explicit observation-link table. This is necessary to say an actual meal/workout was optionally associated with a planned item without changing the planned item into an actual record.
- `plan_v2_previews` lacks a durable user-command/confirmation record; it should not be treated as a saved plan.

## 8. Flutter Problems

### Working portions

- `PlanProvider`, `PlanHistoryRepository`, `PlanListScreen`, and `PlannedDayPlanSection` read V2 plans through `/api/plan-v2/plans` and avoid parsing model prose.
- `PlanDetailScreen` fetches the exact revision before rendering when one is persisted, and its V2 lifecycle calls are owner-token authenticated.
- `PlanDisplay` and `VersionedPlanCard` render planned data separately from daily meal/exercise logs.

### Broken or facade-only portions

- `ChatbotScreen` still exposes an active legacy/V2 hybrid card and opens `plan_detail_bottom_sheet.dart`, a legacy renderer with mutable `completed` items and legacy check-ins.
- `_createPlanFromQuickAction` creates a legacy plan even though the same screen can show V2 cards and library navigation.
- `VersionedPlanCard` shows lifecycle button positions, but the chat card supplies only `onView`; save/edit/activate/pause/resume/cancel are not callable there.
- `PlanDetailScreen` has save/lifecycle controls but no editor. The presentation component has an `onEdit` slot without a product implementation.
- There is no Flutter client method for V2 draft creation, revision creation, revision listing, or exact deep-link navigation.
- `PlanProvider.clear()` is not linked to logout/identity changes. Its owner guard reduces exposure after the next load but does not proactively clear retained plan state.
- The app uses in-memory `MaterialPageRoute`; no URI/deep-link route resolves an exact plan reference.

## 9. Chatbot Problems

1. Chat generation correctly uses structured Plan V2 tools rather than exposing legacy row-writing tools to the LLM.
2. Chat confirmation creates an exact hash-bound pending action, which is valuable, but the action is process-local and default completion is shadow-only.
3. Chat has no deterministic "current/that plan" reference resolver. The tool accepts IDs, but those IDs are not a first-class conversation/entity reference with owner and revision context.
4. The same Chat screen contains both the legacy quick-create action and V2 card navigation. This is the concrete source of parallel plan creation.
5. Direct personalized E4 workout cards have save/result callbacks, while V2 multi-day workout cards do not define the corresponding child-plan/result behavior. The product presents two competing workout-plan experiences.
6. Chat history should retain `PlanReference` plus presentation snapshot for history. It must never become the lifecycle or active-plan authority.

## 10. Legacy Problems

- `services/agent/tools/plan_tools.py`, `services/agent/planner.py`, and `modules/plans/router.py` remain live through quick actions and legacy mobile APIs.
- Legacy status literals (`active`, `completed`, `cancelled`) cannot express draft, saved, paused, superseded, revision conflict, or exact content identity.
- Legacy `plan_items.completed` means planned/actual semantics are ambiguous. A check-in is even stored as an exercise-shaped plan item.
- Legacy planner has its own weekly phases/workout schedule and therefore competes with the canonical E4 path.
- Legacy reads are a fallback after a V2 active read rather than a consciously separated “legacy history” surface.

## 11. KEEP / FIX / REWRITE / REMOVE

| Classification | Components | Decision |
|---|---|---|
| KEEP | `PlanRevision` identity/hash/owner/period contracts; `PlanSqlRepository` transaction/read-back/idempotency patterns; `PlanProvider` owner-scoped projection; `PlanDisplay`; V2 planned-vs-actual validator; canonical nutrition and E4 engines | Retain the concepts and tested boundaries. Extend only after one product contract is approved. |
| FIX | V2 route coverage, rollout gating, revision/list APIs, completed lifecycle command, deterministic reference resolution, auth-bound provider reset, exact route navigation, transient preview confirmation | These are localized boundary gaps; they should conform to the rebuilt contract. |
| REWRITE | One Plan application service/API used by chat and Flutter; mobile creation/edit/plan detail actions; progress/review/adjustment/safety policy layer; parent-child integration with E4 | Required to remove split flow and to support the nine required plan sections. Do not rewrite canonical nutrition or E4 prescription algorithms. |
| REMOVE (after cutover) | Chat quick action call to `POST /plans`; legacy active-plan fallback; `plan_detail_bottom_sheet.dart` legacy mutations; `mark_plan_item_complete` for planned state; legacy check-in-as-plan-item write | Remove only after migration/cutover, with historical records retained read-only. |
| LEGACY_ONLY | `/plans` router, `PlannerAgent`, `plan_tools`, legacy `plans`/`plan_items` UI/model adapters | Keep only for read-only migration/history until a measured retirement date. Do not route new users or writes into it. |
| KEEP SEPARATE | `workout_plans_e4`, `workout_results_e4`, meal/exercise/weight diary tables | These are prescription or actual-observation domains. Integrate by explicit references, never merge their facts into the Plan aggregate. |

## 12. Proposed Architecture

This is a post-audit proposal, not a preselected "Plan V3" decision. It preserves good V2 persistence concepts and canonical nutrition/E4 engines while replacing the duplicate orchestration boundary.

```text
Flutter: Plan Library / Detail / Editor / Deep link
  -> PlanRepository (one typed remote contract, token-authenticated)
  -> Plan API
  -> PlanApplicationService
       -> Plan aggregate repository (authoritative PostgreSQL)
       -> Nutrition plan builder (canonical nutrition/catalog only)
       -> Workout schedule builder (E4 only)
       -> Progress/review service (reads actual observations only)
       -> Safety gate (deterministic constraints and stop conditions)

Chatbot
  -> PlanCommand / PlanReference, not prose plan reconstruction
  -> the same PlanApplicationService
  -> structured chat card containing the exact PlanReference

Meal / workout result / weight / lifestyle observations
  -> their existing authoritative stores
  -> optional explicit PlanItemObservationLink
  -> never mutate planned item into actual consumption/completion
```

### Plan contract, including the required nine sections

`PlanRevision` is the immutable, auditable proposed content. `Plan` owns current lifecycle and an append-only lifecycle/event history. A chat confirmation is a separate command state, not a mutation of a revision merely because it is waiting for a reply.

1. **Mục tiêu (Goal)**: domain, target outcome, target date/range, user-approved goal snapshot, and rationale/reference provenance.
2. **Trạng thái ban đầu (Baseline)**: verified profile/body/training/safety input references, captured-at time, availability state, and non-fabricated missing fields. It is a snapshot, never a silently filled zero/default.
3. **Nhu cầu năng lượng (Energy need)**: canonical TDEE/calorie target, formula/policy version, units, and applicability. A combined plan must not create cross-domain energy compensation.
4. **Mục tiêu dinh dưỡng (Nutrition targets)**: calories, protein, carbohydrate/fat targets or explicit unavailable status, dietary/allergen hard constraints, and source versions.
5. **Kế hoạch ăn (Meal schedule)**: date/slot, canonical dish/food references, portions, planned nutrient values, policy provenance, and item status `PLANNED/CANCELLED/SUPERSEDED` only.
6. **Kế hoạch vận động (Workout schedule)**: date/slot, saved E4 prescription reference or immutable E4 snapshot/reference, exercise policy/catalog versions, and prescribed duration. It does not contain actual sets/reps/results.
7. **Theo dõi tiến triển (Progress tracking)**: review cadence and which owner-scoped actual sources can be read (weight, meal diary, workout results, lifestyle). Actual values remain in those stores; a link is optional and explicit.
8. **Quy tắc điều chỉnh (Adjustment rules)**: deterministic thresholds, required observation window, versioned rule set, and a review outcome. A review proposes a new revision; no LLM or background job silently edits a saved/active plan.
9. **Safety / stop conditions**: deterministic contraindications, required specialist/clarification states, user-visible stop/review conditions, safety-profile freshness, and the action permitted/blocked. Safety governs generation, activation, and adjustment.

### Lifecycle proposal

`DRAFT -> SAVED -> ACTIVE <-> PAUSED -> COMPLETED` with `CANCELLED` available from non-terminal user states and `SUPERSEDED` created by an approved replacement/cutover. Invalid transitions fail with an optimistic-concurrency version. `PENDING_CONFIRMATION` belongs to a durable command/confirmation record, not the lifecycle of immutable plan content. The product must decide whether `COMPLETED` is user-confirmed or review-driven, then expose exactly one command and audit event for it.

### Domain/combined proposal

- `NUTRITION` and `WORKOUT` share the aggregate/revision/lifecycle envelope but have typed sections/items.
- `COMBINED_HEALTH` is a reference container over explicitly selected nutrition/workout child `PlanReference`s. It owns goals, baseline, progress, adjustment, and safety policy, but does not copy child items or calculate cross-domain calorie compensation.
- Editing any meaningful content creates a new child/parent revision with explicit parent reference; it never updates an existing item row in place.

## 13. Proposed Data Model

Names are illustrative. Reuse or replace current V2 tables only after schema mapping is approved.

```text
plans
  id, owner_user_id, domain, current_revision_id, lifecycle_status,
  current_lifecycle_version, created_at, archived_at

plan_revisions (immutable)
  id, plan_id, revision_number, parent_revision_id, content_hash,
  goal_snapshot, baseline_snapshot, energy_target, nutrition_targets,
  progress_policy, adjustment_policy, safety_policy, provenance, created_at

plan_items (immutable per revision)
  id, revision_id, logical_item_id, scheduled_date, slot, item_type,
  planned_content, canonical_refs, policy_provenance, item_status

plan_status_events
  id, plan_id, revision_id, from_status, to_status, expected_version,
  action_id, actor, occurred_at

plan_commands / plan_confirmations
  owner_user_id, action_id, command_type, plan_id, revision_id,
  expected_hash, state, expires_at, completed_at

plan_reviews
  id, plan_id, base_revision_id, observation_window, rule_version,
  outcome, proposed_revision_id, reviewed_at

plan_item_observation_links
  id, plan_item_id, observation_type, observation_id, linked_by, linked_at
```

Foreign keys/reference integrity must link a workout item to an E4 prescription when that prescription is saved. Observation links are optional and must not be required before a plan is displayed, saved, activated, paused, cancelled, or completed.

## 14. Proposed User Flows

### Create and save

1. User requests nutrition, workout, or combined plan in chat or Plan UI.
2. Caller sends bounded input; application service resolves authoritative profile, canonical nutrition/E4 data, constraints, safety, and references.
3. Service writes an owner-scoped durable draft/command and returns one `PlanReference` plus typed presentation.
4. User explicitly saves. The same service validates expected draft hash and writes the immutable revision/read-back result.
5. Chat stores the reference and snapshot; Flutter immediately reads/upserts the returned authoritative record. The library reads the same record on restart/device two.

### Edit/review

1. UI/chat identifies exact `plan_id`, `revision_id`, and expected revision number; ambiguous “that plan” asks the user to choose from owner-scoped candidates.
2. Domain resolver converts only allowed structured changes into canonical references.
3. Service creates a new draft revision, preserves parent identity, runs validation/safety, then saves only on explicit confirmation.
4. Old revision remains retrievable in revision history; active replacement follows a documented overlap/supersession rule.

### Lifecycle

1. Save does not imply activation.
2. Activation, pause, resume, completion, and cancellation call one idempotent command endpoint.
3. Server records an event, verifies optimistic version, returns authoritative read-back and valid next actions.
4. Flutter replaces cached projection only with that response or a subsequent authoritative refresh.

### Progress and adjustment

1. User logs actual meals/workout results/weight in their normal modules.
2. A review reads actual records and plan policy over an explicit window.
3. It may link observations and propose an adjustment revision, but never turns a scheduled item into an actual one and never auto-promotes a change.
4. Stop conditions block unsafe generate/activate/adjust actions and route to the appropriate clarification/specialist flow.

## 15. Migration / Cutover Strategy

1. **Inventory, do not rewrite**: inventory legacy `plans`, `plan_items`, E4 plans/results, V2 revisions/previews, and chat references. Do not modify frozen/research artifacts or mutate raw historical observations.
2. **Define qualification classes**: classify legacy rows as read-only displayable, explicitly migratable, unversioned, or invalid. Do not auto-convert a legacy plan that lacks baseline, canonical provenance, or clean planned/actual separation.
3. **Build new flow behind a new owner-level rollout flag**: a user/account is either on the new authoritative Plan flow or legacy read-only flow; never dual-write an active plan.
4. **Migrate only explicit, validated candidates**: create a new immutable revision with preserved source/provenance and a mapping record. Otherwise require the user to create a new plan and retain legacy record as history.
5. **Cut active reads first**: remove legacy fallback from the primary active-plan API. If legacy history must be shown, label it “legacy history” and do not expose lifecycle/mutation controls.
6. **Cut writes next**: remove Chat quick action legacy creation and legacy item completion/check-in calls once equivalent new flows are released and tested.
7. **Retire legacy only after evidence**: measure zero new legacy writes, successful migration/read-back, correct owner isolation, and recovery behavior. Keep a reversible feature flag for routing, not a write-both-data strategy.

## 16. Implementation Plan

| Step | Files / modules | What changes | Dependencies | Risks | How to test | Done condition |
|---|---|---|---|---|---|---|
| 1. Lock domain contract | New Plan contract specification; `services/plan_engine/contracts.py`; Flutter typed models | Define the nine sections, `PlanReference`, lifecycle/event semantics, item/observation boundary, error codes, and JSON examples. Decide completed semantics. | Product/safety review | Recreating legacy ambiguity | Contract serialization/validation tests and cross-client golden fixtures | One accepted contract shared by backend/chat/mobile |
| 2. Map and harden persistence | V2 migrations/repository or replacement repository | Add plan/current state, immutable revisions/items, events, command confirmation, review/policy and observation-link data. Preserve owner scope, hash/read-back and idempotency. | Step 1; migration inventory | Unsafe automatic conversion, data lock contention | Disposable Postgres migration, rollback, read-back, conflict, index tests | New schema is migration-versioned and all writes/read-backs are transactional |
| 3. Create one application service | New/rewritten Plan service; retain canonical nutrition and E4 adapters | Centralize create, preview, save, revise, lifecycle, list, exact read, review. Delete duplicate state rules from routers/widgets. | Steps 1-2 | Accidentally duplicating nutrition/E4 policy | Unit/service tests using fake canonical adapters | Every command returns authoritative `PlanReference` + typed presentation |
| 4. Replace API surface | `modules/plans/v2_router.py` or successor; auth | Expose draft/save/revise/list/revision-history/exact/lifecycle/review endpoints for nutrition/workout/combined. Make rollout gate uniform. | Step 3 | Breaking mobile callers | OpenAPI/contract tests, owner and idempotency API tests | No primary API relies on legacy fallback or caller-supplied owner id |
| 5. Integrate E4 correctly | `workout_planner/integration.py`, Plan service | Define when an E4 prescription is persisted, how a plan item references it, and how explicit actual results link back. | Steps 1-4 | Mixing prescription and result | Save/result/link/owner tests | One workout schedule has one visible parent/reference story |
| 6. Rebuild Flutter data layer | `backend_api_service.dart`, `plan_provider.dart`, typed models | Replace map-only orchestration with typed Plan repository; clear on auth transition; use returned authoritative state. | Step 4 | Stale cache/partial migration | Provider owner-switch, refresh, restart tests | Library/detail/daily projections use only new Plan API |
| 7. Rebuild Flutter UI/navigation | Plan list/detail/editor, app router/deep links, remove legacy sheet from new flow | Implement create/edit/revision history/lifecycle/progress/safety states; deep link exact reference; loading/error/empty UI. | Steps 4, 6 | Hiding safety state or exposing invalid commands | Widget, accessibility, navigation and response-state tests | All supported lifecycle/action states are usable and unambiguous |
| 8. Rewire chatbot | `orchestrator.py`, `pending_user_action.py`, tool descriptors, `chatbot_screen.dart` | Chat emits/consumes `PlanReference`; pending command is durable/expiring; “that plan” resolves exact targets; delete quick legacy creation. | Steps 3-4 | LLM choosing an ambiguous plan | Exact-reference, ambiguous-reference, restart and confirmation tests | Chat uses the same plan service/API behavior as Flutter UI |
| 9. Migrate/cut over | New migration scripts, read-only legacy adapter, feature flags | Execute inventory/classification, account rollout, explicit migrations, and active-read cutover. | Steps 1-8 | Data loss, dual active states | Dry run, sampled read-back, user/foreign-owner E2E | No new legacy plan writes for migrated accounts |
| 10. Retire legacy | `/plans`, `PlannerAgent`, `plan_tools`, bottom sheet/client completion paths | Delete/decommission only after cutover evidence; preserve documented read-only archive if needed. | Step 9 | Removing a needed historical path | No-reference search, regression and migration-retention tests | Legacy paths are unreachable for new product writes |

## 17. Test Plan

| Layer | Required coverage |
|---|---|
| Contract/unit | nine plan sections; required/missing baseline; canonical reference validation; planned-not-actual rejection; lifecycle transition table; safety/stop rules; adjustment rule outcome; content hash stability; `PlanReference` serialization. |
| Repository/PostgreSQL | create/read exact; revision parent/version conflict; save idempotency; lifecycle idempotency; status events; active-overlap behavior; preview/confirmation expiry; rollback; indexes; owner isolation; foreign reference denial; observation link does not mutate plan item. |
| API | nutrition/workout/combined create; read/list/revision history; edit; save; activate; pause/resume; complete; cancel; bad hash; stale expected version; duplicate action; restart recovery; no legacy fallback; token refresh/auth error behavior. |
| Flutter unit/widget | loading/error/empty states; list/detail/revision picker; create/edit; lifecycle button availability; safe stop-condition display; provider logout/account switch clear; stale refresh; planned day render; no completion toggle on planned item; exact deep link route. |
| Chatbot | generation returns typed reference; save confirmation binds exact hash; ambiguous “that plan” requires selection; exact old revision read; chat restart recovery; no re-generation on open; no legacy tool/quick-create path; card and Plan Library agree on reference. |
| E2E | A nutrition create/view; B workout create/view; C edit/new revision; D save; E activate; F pause/resume; G cancel; H restart persistence; I second-device same account; J exact chat reference; K planned != actual; legacy migration/read-only view; user A cannot read/write user B. |

No test may count a planned meal/workout as an actual observation merely because it is displayed, saved, activated, or completed at Plan lifecycle level.

## 18. Risks

- Moving legacy users automatically can fabricate missing baseline/provenance or preserve ambiguous `completed` semantics. Default to explicit migration/classification.
- A dual-write transition creates the same duplicate-active problem the rebuild is meant to remove. Use a per-owner routing flag, not two writes.
- E4 prescription and actual workout results must remain independently authoritative; an integration link must not copy target sets/reps into results.
- Adjustment rules are health-affecting. Keep deterministic safety/dietary constraints, immutable review evidence, and explicit confirmation; do not let an LLM directly mutate a canonical plan.
- Existing authentication failures cannot be attributed to Plan code from this audit. New API work must include token refresh/owner-isolation tests before a production claim.
- The current test environment lacks backend dependencies and Docker is not running. Rebuild qualification requires a reproducible dependency environment and disposable Postgres database before enabling a cutover.

## 19. Recommended First Implementation Step

Start with **Step 1: approve the single Plan contract and its golden JSON fixtures**, especially the distinction between plan lifecycle, revision content, transient confirmation, and actual observations. Use the nine required sections as the acceptance checklist. Then implement the one application-service/persistence boundary before altering Flutter or chatbot UI.

This is the smallest safe first move because it resolves the proven source-of-truth split without prematurely choosing a version label, transport technology, or a new nutrition/workout algorithm.

```
PLAN_ROOT_CAUSE_IDENTIFIED = YES
PLAN_REBUILD_ARCHITECTURE_READY = YES
PLAN_REBUILD_IMPLEMENTATION_PLAN_READY = YES
SAFE_TO_START_REBUILD = YES (staged rebuild only; no production cutover until Steps 1-8 are verified)
```
