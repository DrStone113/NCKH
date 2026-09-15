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

### Basic account details (2026-09-08)

Authentication now opens the existing personal-profile form in account-setup
mode before the domain questionnaire. Both email registration and first Google
login create an incomplete user document: age, height, weight, activity and
goal remain null until supplied. A Google/display name is only a prefill.

The required form asks for name, age, gender (with an explicit decline option),
height, weight, activity and goal. Equation sex remains a separate optional
answer and is never inferred from gender. Measurements are shown before the
optional nutrition-safety questions. The same validated form remains available
in Settings.

`users.basic_profile_completed_at` records successful confirmation independently
of the V2 nutrition/workout envelope. Accounts missing this marker confirm their
existing values once; even a completed V2 envelope cannot bypass this step.
Invalid required values reopen the form. Saving must succeed in Firestore before
the provider marks completion or the auth wrapper advances. A failed save keeps
the entries and displays a retryable error. Restoring a Firebase session with a
missing user document uses the same incomplete-account creation path.

Root cause: both authentication paths previously invented age 25, height 170 cm,
weight 68 kg and target weight 65 kg. The V2 questionnaire only asked domain
preferences and exercise safety, and its completion gate never checked the
general profile. These defaults must not be restored to real account creation.
The nutrition-only save also no longer validates hidden exercise/pregnancy
answers when a user has selected female in the basic form.

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

- `apps/mobile/test/basic_account_profile_test.dart`
- `apps/mobile/test/widgets/basic_account_intake_test.dart`
- `apps/mobile/test/health_profile_v2_test.dart`
- `apps/mobile/test/widgets/workout_account_intake_screen_test.dart`
- `apps/mobile/test/workout_profile_memory_test.dart`
- `apps/backend/tests/test_dynamic_system_prompt.py`
- `apps/backend/tests/test_tool_catalog.py`

Basic-profile verification on 2026-09-08: **38 Flutter tests passed** across
the two new test files, existing settings/intake widgets, HealthProfile V2 and
canonical nutrition integration. Dart analysis of the six affected source
files and three new/updated test files reported no issues. Widget checks use
a 390 × 844 viewport and cover blank submission, exact decimal measurements,
transition to domain intake, failed persistence and retry. Provider tests use
the isolated demo account; this is not a live Firebase signup qualification.

The first test attempt found a pre-existing SDK mismatch: generated package
configuration referenced `C:/Tools/flutter` while the runner used the project's
Flutter 3.44.8 SDK. Running the pinned SDK's `flutter pub get --offline`
regenerated that configuration and aligned the four SDK-constrained transitive
dependencies in `pubspec.lock`. No SDK source was patched.

## Research Invariance

No frozen research A/B/C artifact, nutrition-policy-v1.0.1,
exercise-prescription-policy-v1.1.0, E2 catalog, D3 validation artifact, or
workout explicit-write behavior was modified by this feature.

## Profile completeness before chat (2026-09-08)

`ProfileReadiness` checks actual required values, basic confirmation, and the
completed domain payload. A schema/version marker alone cannot bypass missing
data. The existing app-entry gate reopens the relevant intake for incomplete
accounts, including existing accounts.

The chat screen shows an actionable missing-fields checklist. Each item opens
the basic profile or nutrition/workout form, and a successful save returns to
chat. Nutrition questions check confirmed allergies/restrictions and missing
energy/safety inputs; workout questions check workout intake. General questions
do not demand unrelated sensitive details. Explicit empty allergy/restriction
selections remain confirmed empty lists after serialization; absent or legacy
answers remain unconfirmed.

Before each send (including retry), real accounts refresh the user document
from Firestore server. Missing required data, read errors or an account switch
stop submission before WebSocket connection. Failed checks preserve the draft;
an owner-scoped in-memory draft also survives navigation back through intake.
The isolated demo uses its local profile and is not relabelled server-backed.

Optional personalization gaps do not block general conversation. They are sent
as allowlisted field IDs to the backend, whose prompt asks only for information
needed by the current request before personalizing the affected advice. Declined
or unknown answers remain unknown. This prompt guidance complements existing
deterministic safety gates; it is not a new backend authorization mechanism.
Checked, scoped snapshots replace prior WebSocket context so omitted fields
from earlier turns cannot silently return.

Verification uses synthetic model/provider fixtures and Flutter widgets, with
no live Firebase signup or live chatbot qualification. Focused tests cover
missing actual fields despite completion stamps, confirmed empty lists,
round trips, fresh versus stale profiles, read failure, account changes, form
navigation and successful return to chat. Backend tests cover prompt formatting,
malformed identifiers and replacement of stale context.

Focused result on 2026-09-08: **56 Flutter tests passed** across readiness,
completion notice, basic account, settings/intake, health/workout profile,
canonical nutrition integration and chat history tests; **20 backend tests
passed** across readiness prompt, dynamic prompt and chat gateway. Dart analysis
of the eight affected source files and three new/updated tests found no issues.
