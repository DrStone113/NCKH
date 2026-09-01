# Account Intake V2 — Unified Nutrition, Workout & Health Profile

## Profile Schema

`users.health_profile` is an additive V2 envelope:

- `schema_version: 2`
- `primary_support`: `NUTRITION`, `EXERCISE`, `BOTH`, or `GENERAL_HEALTH`
- `nutrition_profile`
- `workout_profile`
- `safety_profile`

Legacy top-level `nutrition_profile` and `workout_profile` remain readable and
are mirrored when the V2 envelope is saved. The migration does not reinterpret
old values.

## Nutrition Profile

V2.1 semantics: deterministic dish constraints combine confirmed canonical
allergen tags, confirmed dietary restrictions, and confirmed explicit food
exclusions. Free text and `CANDIDATE_FACT` values are never hard constraints.

The profile supports nullable structured values for goal, canonical food
allergens, dietary restrictions, preferred/disliked foods, cuisines, meal
preferences, exclusions, and notes. Absence remains `null`; it is never
silently treated as “none”. Explicit canonical allergen IDs are the only source
for deterministic allergy tags; confirmed dietary restrictions and explicit
food exclusions are included as separate hard constraints.

## Workout Profile

The shared `GeneralProfile` is a typed view over the authoritative user-root
fields (`age`, `height`, `weight`, `equation_sex`, activity level, and goal).
It is available to both domains without duplicating values into either
subprofile, so a later root update cannot make the two domains disagree.

The existing E4 workout profile stays the source for training and exercise
safety fields. Its persisted schema and explicit confirmation workflow are not
changed. V1 accounts with a complete workout profile are prefilled and do not
see that questionnaire again during the V2 upgrade.

## Safety Profile

`SafetyProfile` mirrors structured exercise safety and the existing canonical
nutrition-safety answers inside `health_profile`; it does not change the frozen
nutrition policy. Free text is not promoted to a diagnosis or a safety gate.

## Free-Text Support

The intake provides multiline text fields for goal description, food
preferences, food dislikes, other dietary restrictions, additional
health/nutrition notes, and workout preferences. Text receives provenance
`EXPLICIT_USER_TEXT` and is stored as supplied after length/whitespace checks.

## Conditional Questions

The first question asks what the user mainly wants help with. Nutrition-only
users receive food questions without being forced through training fields.
Workout details and exercise-safety questions only appear for `EXERCISE` or
`BOTH`. Pregnancy is shown only after the user has explicitly selected the
existing female profile state.

## Existing-User Migration

Any account without `health_profile.schema_version >= 2` is routed to the V2
screen. Existing values are prefilled. A completed V1 workout profile is kept;
only the new V2 priority/nutrition information is requested.

## Memory Semantics

Each newly persisted nutrition field records `value`, `status`, `source`,
`updated_at`, `confirmed_at` when applicable, and a freshness class. Sources
are `EXPLICIT_UI_SELECTION`, `EXPLICIT_USER_TEXT`, `USER_CONFIRMED`, `LEGACY`,
and `CANDIDATE_FACT`; candidates require a relevant confirmation before use.

Profile provenance uses `EXPLICIT_UI_SELECTION`, `EXPLICIT_USER_TEXT`,
`USER_CONFIRMED`, `LEGACY`, and `CANDIDATE_FACT`. Free text remains raw. A
candidate is not a hard restriction, diagnosis, or allergy. Explicit
single-field nutrition corrections update only the supplied field.

## Confirmation Semantics

Freshness is field-specific: `STABLE_UNTIL_CHANGED`,
`PERIODIC_CONFIRMATION`, `TIME_SENSITIVE`, or `CURRENT_OBSERVATION`. The E4
adapter remains the enforcement point for the same-day pain/safety check.

Fresh explicit V2 facts do not require repeated confirmation. A relevant recap
is required only for a legacy/candidate/conflicting fact or a changed domain;
the assistant must summarize only the facts needed for that request. Existing
time-sensitive exercise pain semantics remain unchanged.

## Chatbot Context

Nutrition requests receive general + nutrition + nutrition safety + canonical
nutrition state. Workout requests receive general + workout + exercise safety
and training state. Cross-domain requests receive both; mixed send-time state is
pruned to the relevant domain rather than injecting the full `HealthProfile`.

The mobile client scopes profile context per message: nutrition requests send
nutrition + nutrition safety, workout requests send workout + exercise safety,
and cross-domain requests send both. Canonical dietary restrictions derived
from explicit allergen selections are passed to the dish policy. The prompt
prohibits converting free text into a canonical allergy without confirmation.

## UI Changes

The screen is framed as **Hồ sơ sức khỏe của bạn** in the existing light/bento
language. Its sections are: priority, eating, training, and safety. Friendly
cards, chips, optional fields, and “Thêm thông tin ăn uống” replace the former
workout-first medical-form flow.

## Tests

- `apps/mobile/test/health_profile_v2_test.dart`
- `apps/mobile/test/widgets/workout_account_intake_screen_test.dart`
- `apps/mobile/test/workout_profile_memory_test.dart`
- `apps/backend/tests/test_dynamic_system_prompt.py`
- `apps/backend/tests/test_tool_catalog.py`

## Research Invariance

No frozen research A/B/C artifact, nutrition-policy-v1.0.1,
exercise-prescription-policy-v1.1.0, E2 catalog, D3 validation artifact, or
workout explicit-write behavior was modified by this feature.

## Remaining Issues

Account-intake free-text editing is available in onboarding and via explicit
chat updates. A dedicated profile-settings editor for every optional V2 field
can be added later without a schema migration.
