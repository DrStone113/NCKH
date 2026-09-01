# E4.0 — Deterministic Personalized Workout Planner (shadow mode)

## Outcome and phase boundary

E4.0 adds an auditable, history-aware workout planner without replacing the
legacy `suggest_workout` tool. The planner is deterministic, does not use an
LLM to select or prescribe exercises, does not mutate user state, and is not
wired into chatbot generation. `WORKOUT_PLANNER_MODE` accepts only `off` and
`shadow`; the default is `off`.

Frozen inputs remain unchanged:

- E2 `canonical-exercise-v1.0.0`, 885 records, content SHA-256
  `c048fe7a6f73cfdb53961ea151b7c4d624259607e49d028c9d08a02de01df348`;
- E3.1 `exercise-prescription-policy-v1.1.0`, semantic SHA-256
  `b25bee0f3cfda41f6a457cac18e0e1191f212ad6f048d8863ec03c7cb1cc8a01`;
- research corpus `offline-v1-636`, its manifest, conditions A/B/C, and
  `nutrition-policy-v1.0.1`.

## Runtime reproducibility

E4 verification stays on Python 3.10. The clean verification environment is:

| Component | Exact version |
|---|---:|
| CPython | 3.10.21 |
| pip | 26.2.1 |
| pytest | 8.4.2 |
| Hypothesis | 6.151.9 |

`apps/backend/requirements-e4-py310.lock` records the full resolved dependency
set. `apps/backend/data/workout_planner_e4_runtime_v1.json` records the runtime
and resolution mechanism. The suite runs with normal `python -m pytest -q`;
there is no repository compatibility shim.

The former `dataclasses(slots=True, init=False)`/Hypothesis failure was observed
on the initial Python 3.10.0 patch. It does not reproduce on Python 3.10.21.
Therefore it is classified as an obsolete patch-runtime limitation, not a
product behavior and not a reason to migrate the project to Python 3.11.

## Contracts and state semantics

All E4 contracts are frozen dataclasses with slots and JSON-safe serialization.
`ExerciseProfile` separates authoritative profile facts from unknown state and
uses the D1-style states `KNOWN`, `MISSING`, `NOT_LOADED`, `STALE`, `ERROR`,
`CONFLICT`, and `UNKNOWN`. Experience is explicitly `NOVICE`, `EXPERIENCED`, or
`UNKNOWN`; unknown is never relabeled as novice. Equipment is never inferred
from exercise history, and free-text limitations are not converted into a
diagnosis.

`WorkoutRequest` contains current-turn constraints such as duration, location,
equipment override, body area, include/exclude lists, temporary preferences,
and session type. It is distinct from persistent `ExerciseProfile` facts.
`write_intent` defaults to false and is rejected in E4.0.

`TrainingState` contains explicit observations for 7/28-day session counts,
aerobic minutes, last activity, muscle/movement exposure, exercise performance,
sets, reps, load, RPE/RIR, completion, missed sessions, pain, substitutions, and
active-plan status. Every observation retains source, observation window,
computation time, status, provenance, and coverage.

## Legacy history normalization

The current legacy log can derive session counts, resistance-session counts,
aerobic minutes, last-session time, and completion rate. Catalog joins can only
partially derive muscle/movement exposure. Legacy rows that contain only
exercise, duration, and calories cannot supply sets, reps, load, RPE/RIR, pain,
missed sessions, or substitutions; those values stay missing rather than being
filled with zero or invented values.

Unavailable history yields `HISTORY_UNAVAILABLE`. The planner may use the
policy's conservative operational prescription for an ordinary supported goal,
but it does not claim that the user is fresh, recovered, novice, or at zero
weekly volume. Progression remains unavailable without complete prior
performance observations.

## Planning pipeline

The pipeline is ordered and deterministic:

1. E3.1 applicability and safety gate.
2. Goal-domain resolution and `SessionRequirement` construction.
3. Hard catalog filtering.
4. Reason-coded candidate ranking.
5. Time-budget construction.
6. E3.1 prescription, progression, substitution, and optional energy mapping.
7. Independent plan validation.

Safety runs before selection. Significant current pain, acute injury, or recent
surgery requires professional guidance; warning symptoms are unsupported for
ordinary planning; unknown safety facts require clarification. The gate does
not diagnose and cannot be overridden by ranking or catalog metadata.

Ambiguous “endurance/sức bền” returns clarification. Muscular endurance stays
in the resistance domain. Aerobic endurance is handed off in E4.0 because the
frozen E3.1 contract does not contain a complete session-level aerobic dosage
contract for this planner.

## Catalog filtering and ranking

The frozen 885-record catalog is filtered in exact, auditable stages: safety,
profile/request exclusions, explicit include constraints, equipment, location,
structural catalog eligibility, instruction sufficiency, goal domain,
experience/technical gate, and explicit limitations. Each stage records
`before`, `removed`, `after`, and a reason code. A removed exercise cannot be
restored by ranking.

`REQUIRES_EXPERIENCE_CONFIRMATION` is contextual. It does not globally reject
ordinary general-fitness candidates whose difficulty is unspecified. Advanced
or power use requires confirmed experience, and power also requires the
technique screen required by E3.1. An empty equipment set is not interpreted as
bodyweight equipment.

Ranking is a transparent list of components. Each component has a rule ID,
integer priority, provenance, and reason code. Inputs can include goal fit,
requested body area, underexposed muscle/movement signals, recent exact
exercise exposure, persistent preference/dislike, current-turn inclusion,
active-plan context, and setup efficiency. Movement variety is labeled as a
product heuristic or soft planning target, never a safety rule.

## Time, prescription, progression, and substitution

The versioned time model uses five minutes of session overhead, 45 seconds per
set, the E3.1 minimum rest, 60 seconds between exercises, and 30 seconds of
setup for each selected exercise requiring equipment. The solver builds within
the requested budget from the
highest-priority candidate onward; it does not create a long plan and truncate
it afterward, and it never shortens E3.1 rest to fit extra exercises.

Sets, repetition range, rest, effort target, RPE/RIR semantics, volume bounds,
and policy rule IDs are read from E3.1 at runtime rather than copied into E4.
Weight-management uses the same E3.1 semantics and does not claim that higher
reps, shorter rest, or fabricated calorie burn produces more fat loss.

Progression calls the E3.1 resolver only when prior prescription and completion,
sets, reps, load, RIR/RPE, technique, and pain observations are available as
required. Otherwise it returns `PROGRESSION_UNAVAILABLE` with no fabricated
previous values.

Substitutions require compatible movement pattern, primary muscle, equipment,
difficulty/experience, and safety. They are structural catalog matches, not
name-similarity guesses. E2 review debt remains explicit as
`SUBSTITUTION_UNAVAILABLE`.

## WorkoutPlan and validator

`WorkoutPlan` records planner, policy, and catalog versions; profile/training/
safety state; goal; duration budget and estimate; time status; structured
exercises; filter trace; reason-code facts; optional energy estimate; and
readiness. Each exercise keeps canonical and Wger source IDs, source display
name, eligibility status, equipment/muscle/movement metadata, prescription,
progression, substitution, ranking facts, duration, and policy rule IDs. E4 does
not fabricate Vietnamese names.

Energy estimation is optional and session-level. Only an approved 2024 Adult
Compendium mapping can produce `estimated_energy_expenditure`; unmapped
activities return `NO_CALORIE_ESTIMATE`. The result is an estimate, never
reported as measured calories.

`WorkoutPlanValidator` checks safety, equipment, catalog status, exclusions,
experience, time, policy dosage, duplicates, progression, substitution, and
energy provenance. Hard violations prevent `READY`. Explanations remain
structured facts; E4.0 produces no free-form coaching prose.

## Shadow comparison

The standalone comparator runs only when `WORKOUT_PLANNER_MODE=shadow`. For the
same request it records overlap, equipment/safety violations, history response,
goal, duration, policy compliance, and catalog eligibility for legacy
`suggest_workout` and E4. Its output is an engineering artifact and does not
replace or mutate the production response.

## Development evaluation

The development-only oracle has 104 hand-authored invariant scenarios covering
all requested goals, experience states, locations/equipment, 15/30/45/60-minute
budgets, history states, progression, preferences/exclusions, pain/safety,
ambiguous endurance, and substitution. It does not open research pilot/final
cases and does not require one exact exercise list where several plans are
valid.

Evaluation on Python 3.10.21 produced:

| Metric | Result |
|---|---:|
| Safety invariant violations | 0 |
| Hard equipment violations | 0 |
| Catalog hard-eligibility violations | 0 |
| Policy hard-rule compliance | 100% |
| Time-budget compliance | 100% |
| Required-history behavior accuracy | 100% |
| Progression correctness | 100% |
| Unsupported progression | 0 |
| Fabricated history values | 0 |
| Substitution validity | 100% |
| Unsupported calorie estimates | 0 |
| Personalization sensitivity (7 pairs) | 100% |
| Irrelevant-input stability (2 pairs) | 100% |
| Determinism | 100% |
| Planner latency median / p95 / max | 9.972 / 13.820 / 18.587 ms |

Across 22 legacy comparison cases, the evaluator counted 132 legacy policy
violations and 68 legacy catalog-eligibility violations, versus zero E4 hard
policy and catalog violations. Exercise overlap has intentionally no target.

## Verification

From `apps/backend` in the locked Python 3.10.21 environment:

```powershell
python -m pytest -q
python -m scripts.evaluate_workout_planner_e4
python scripts/manage_exercise_prescription_policy.py --verify
python scripts/manage_exercise_catalog.py --verify
python scripts/audit_exercise_data.py --verify
python scripts/manage_catalog_ingestion.py --verify
python scripts/validate_dish_catalog.py
```

Verified result: 761 passed, 1 skipped. The E4 module has 34 passing tests and
the four Hypothesis/property modules have 16 passing tests without a shim.

## Remaining boundary

E4.0 is ready as a shadow planner baseline. E4.1 still needs an explicit
integration decision, authoritative profile/history adapters, operational
telemetry/storage policy, chatbot explanation rendering from reason codes, and
a controlled rollout. None of those E4.1 behaviors are implemented here.
