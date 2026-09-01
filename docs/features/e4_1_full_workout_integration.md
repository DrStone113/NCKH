# E4.1 full personalized workout integration

E4.1 connects the frozen deterministic E4.0 planner to the application without
changing its catalog, policy, planner semantics, nutrition policy, research
corpus, or D3.0.1 context-planner snapshot.

## Rollout and write controls

`WORKOUT_PLANNER_MODE` accepts `off`, `shadow`, and `enforced`; its default is
`shadow`. In `off` and `shadow`, `suggest_workout` returns the legacy payload.
Shadow calls E4 only for structural comparison logging. In `enforced`, the
same compatibility entry point delegates to E4 and returns an explicit E4
status on safety, context, catalog, planner, or validation failure. It never
falls back to legacy prescription.

`WORKOUT_WRITE_MODE` accepts `off` and `explicit`; its default is `off`. A
recommendation has no write path. Saving and result logging require a separate
explicit user action plus an idempotency key, and they return a read-back
verified write status.

## Authoritative inputs

`WorkoutProfile` is a nullable Firestore `users.workout_profile` extension.
It includes self-reported experience, availability, duration, location,
equipment, preferences/exclusions/limitations, pain, and the minimal safety
screen. Missing old fields remain missing; unknown experience is never made
novice.

Before a chat turn, Flutter reads the last 28 days of legacy exercise entries
from Firestore with `Source.server`. A successful empty result is `KNOWN`; a
read failure is `ERROR` and is not converted to zero sessions. Modern E4
results are loaded from PostgreSQL. The adapter preserves source status,
window, coverage and provenance, and does not manufacture sets, load, RPE,
RIR, pain, or completion for legacy rows.

The backend cannot independently query a user's Firestore document. The client
therefore supplies a server-sourced snapshot and its explicit read status over
the existing authenticated WebSocket. This boundary is visible in telemetry.

## Persisted workout-intake memory and confirmation

Chat intake writes through the existing authoritative
`users.workout_profile` document, never through a rolling chat summary. The
client-side `update_workout_profile` tool accepts only a typed patch and writes
it immediately after the user explicitly answers a question about experience,
availability, session duration, equipment, pain, injury, or limitations. A
successful read-back updates the active WebSocket context so a later tool call
in the same turn sees the persisted profile.

Each captured patch increments an intake revision and is marked
`PENDING_CONFIRMATION`. On the next workout request, the chatbot must recap
only the stored values and ask whether its memory is correct. An explicit yes
uses `mode=CONFIRM`; a correction creates a new pending revision instead of
overwriting it silently. E4 refuses an explicitly pending revision with
`PROFILE_CONFIRMATION_REQUIRED`, so an LLM instruction mistake cannot turn an
unconfirmed recap into a prescription.

The self-report `current_pain_status=NO` is not permanent safety clearance.
Its `safety_checked_at` timestamp is current only on that UTC calendar day;
an older or malformed timestamp maps to `UNKNOWN` and the existing E3 safety
gate asks for a fresh pain/injury/red-flag answer. “More than six months” of
training remains a textual detail, not automatic `EXPERIENCED` status.

## Account intake gate

Immediately after a registration, and before the authenticated home screen,
Flutter presents a typed health questionnaire. Its nutrition section accepts
optional free text for allergy/avoidance notes, food preferences, and nutrition
goals; these notes travel to chat for a recap/clarification but are never
silently converted into canonical allergy tags. The training and safety section
captures self-reported training experience, weekly availability, session
duration, location, equipment, current pain, managed health condition, warning
symptoms, acute injury, recent surgery, and the instruction to stop when
symptoms worsen. It is screening data rather than a diagnosis; explicit
`UNKNOWN` remains safe and is never fabricated into a clearance. Pregnancy
relevance is shown only after the user self-identifies as female; it is not
displayed to other or unreported profiles. Their persisted status remains
explicit (`NOT_APPLICABLE` for male, otherwise `UNKNOWN`) rather than guessed.

`WorkoutProfile.currentAccountIntakeVersion` and
`NutritionProfile.currentAccountIntakeVersion` are persisted with their
completed answer sets. When a later release adds a required account question,
increment the relevant version and extend the completeness predicate/form.
Authenticated users whose version or required answer is missing are routed to
the same form on their next app entry; already answered fields are prefilled.
The workout account version is intentionally separate from chat's
pending-confirmation revision, so a subsequent chat correction does not reopen
the full onboarding form.

## Persistence and energy semantics

Migration `008_personalized_workout_e4_1.sql` adds `workout_plans_e4` and
`workout_results_e4`. Plans have `SAVED`, `ACTIVE`, `COMPLETED`,
`PARTIALLY_COMPLETED`, `SKIPPED`, or `CANCELLED` states. Generated plans exist
only in an expiring process-local cache until explicitly saved; they are never
active by implication.

Results record only confirmed observations. Each optional set can hold index,
target reps, actual reps, load, RPE, RIR and completion. Session pain is a
separate `YES`/`NO`/`UNKNOWN` self-report. Device-reported and user-reported
energy are separate fields. The E4 Compendium estimate remains plan metadata
with its activity-code/mapping provenance; it is never stored as a measured
calorie value.

## Chat and presentation

The high-level tool surface is:

- `build_personalized_workout`
- `get_workout_substitutions`
- `save_workout_plan`
- `log_workout_result`

Private runtime context is injected after JSON-schema validation and is not
sent to the model, tool transcript, or invocation audit. The deterministic
`WorkoutPlanPresenter` builds the canonical card payload. The response
validator rejects mismatched exercise IDs, dosage, effort, progression,
duration, or energy metadata. When a plan is present, the final chat payload
uses deterministic E4 text/card data instead of an LLM rewrite.

Substitution uses E4's frozen movement, muscle, equipment, experience and
safety logic. A temporary rejection is not persisted as a dislike. Absence of
a compatible candidate returns `SUBSTITUTION_UNAVAILABLE`.

Flutter renders `PersonalizedWorkoutCard` separately from generic
`ActionItem`; it displays canonical source names and never generates a
Vietnamese name or calorie number. The card exposes optional actual reps/load,
an independent pain input, explicit save, completion, partial-completion, and
substitution actions.

## Observability and limitations

Development `ContextTrace` records structural E4 identifiers, field-status
classes, state coverage, selected canonical IDs, reason codes, validator
result, presentation path, and latency. It does not record profile values,
raw history, names, emails, addresses, or credentials.

The REST write endpoints inherit the current app's user-ID trust model; they do
not add a new bearer-token authorization layer. A production rollout should
bind `user_id` to the existing authenticated principal before enabling
`WORKOUT_WRITE_MODE=explicit`.
