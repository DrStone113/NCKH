# Flutter Plan Experience Integration

## Root cause

Plan Tool V2 already sent a structured `versioned_plan` to Flutter, including
the immutable `plan_id` and `revision_id`. Flutter rendered that card inside
chat, but had no discoverable Plan surface and the card actions used ambiguous
natural-language follow-up messages. This let chat copy refer to a Plan area
that did not exist.

## Existing navigation and design audit

`HomeScreen` is the runtime navigation hub. It uses an `IndexedStack` with four
fixed bottom destinations: Tổng quan, Dinh dưỡng, Vận động, and Cài đặt. Chat
is opened as the centered FAB's modal sheet. There is no route table or router
package; feature details use `MaterialPageRoute`.

The app's established visual language is the light bento theme: `BentoCard`,
`AppColors`, Inter typography, 12–24px radii/spacing, and the responsive
helpers used by the dashboard. Web is rendered in a phone wrapper; individual
feature surfaces still need mobile-safe layouts.

## Existing Plan V2 client components

| Contract | Existing component | Result |
| --- | --- | --- |
| Plan V2 tool result | server `versioned_plan` presentation | carries plan/revision identity and planned items |
| WebSocket/history parsing | `StructuredResponse.versionedPlan` | retains the exact structured payload |
| Chat UI | `VersionedPlanCard` | renders planned days and safe lifecycle labels |
| Persisted client-readable source | `/chat/sessions` and session messages | retains structured payload with the assistant message |
| Dedicated Plan V2 REST list/detail/lifecycle API | owner-scoped `/api/plan-v2/plans` routes | authoritative list, detail, active-plan, and lifecycle state |

## Information architecture decision

The chosen destination is a pushed **Kế hoạch** screen from the Tổng quan
quick-actions area. It is not a fifth bottom tab: the bottom bar has a centered
chat FAB and four balanced primary domains, while Plan V2 can span nutrition
and workout. A Dashboard entry follows the existing quick-action pattern and
keeps the fixed navigation bar unchanged.

Alternatives rejected:

- A new bottom-navigation tab would alter a deliberately balanced, notched
  four-destination bar and reduce space for labels.
- Nesting it under Dinh dưỡng or Vận động would misrepresent combined plans.
- An AppBar-only action would be less discoverable than the existing dashboard
  quick-action entry point.

## List, detail, and deep link

`PlanListScreen` reads the owner-scoped Plan V2 API through the shared
`PlanProvider`. It deduplicates the same plan/revision identity, then groups
ACTIVE/PAUSED, DRAFT/PENDING_CONFIRMATION/SAVED, and terminal history. It has
loading, empty, retryable error, pull-to-refresh, and no-plan-to-chat states.

`PlanDetailScreen` receives the exact structured map attached to the card or
selected from the authoritative list. The chat's **Xem kế hoạch** action pushes
it directly. No prose parsing is involved. A successful lifecycle operation
upserts its returned revision into `PlanProvider` immediately and then refreshes
the owner-scoped list so server-side superseding is also reflected everywhere.
Raw UUIDs, hashes, policy IDs, and database IDs are never rendered.

## Planned versus actual and lifecycle behavior

Both list and detail explicitly label plans as **dự kiến**. Opening or viewing
never writes a meal or workout observation. Lifecycle actions use the dedicated
owner-scoped REST contract and never turn a planned item into actual
consumption/completion.

Each nutrition day is rendered from that day's exact immutable items. Its
displayed total is recalculated from those same visible items rather than from
the current diary or profile. The current day's diary, when available, is shown
in a separate surface labelled as actual intake. The backend also carries the
revision's per-day summary, captured daily targets, exact `plan_item_id`,
serving size, and ingredient components for stable presentation.

## Chatbot copy and state management

The Plan V2 prompt now tells the assistant to use the delivered **Xem kế
hoạch** card instead of describing a speculative menu path. The card's prior
ambiguous lifecycle prompt buttons are removed; it now has only the exact view
action.

`PlanProvider` is the single owner-scoped client projection used by Home,
Nutrition, Plan list, and Plan detail. It caches immutable revision snapshots,
deduplicates concurrent reads, and clears the previous owner's data before a
new owner's request completes. Home shows today's compact planned menu;
Nutrition resolves the plan using the same selected date; Plan detail shows
the same item set and totals.

## Shadow mode and remaining constraint

Chat history remains a user-visible record of the structured snapshot, not the
authority for current lifecycle state. Cross-screen reads and lifecycle changes
use the owner-scoped Plan V2 API. Plan generation remains shadow by default;
this UI integration does not promote a plan, write canonical nutrition data,
or enable production rollout.

## Verification

Focused tests cover exact-date item totals, owner isolation, shared lifecycle
upsert without duplicates, list/detail rendering, compact Home presentation,
Nutrition date alignment, and the planned-versus-actual boundary. Scoped
Flutter analysis completes without issues. The focused Flutter suite passes 26
tests, and the focused backend Plan V2 suite passes 73 tests with 2 live tests
skipped when their external environment is unavailable.

## Frozen acceptance impact

No file named by
`validation/plan_tool_v2_p2/implementation-freeze-p2-1r-v1.json` was changed.
Plan Engine, persistence, comparator, scheduler, and agent Plan V2 tools are
untouched. The only backend change is user-facing chat copy in
`services/agent/system_prompt.py`, which is outside that frozen source set.
