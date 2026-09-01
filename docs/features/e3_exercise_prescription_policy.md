# E3 — Versioned exercise prescription policy

## Outcome

E3 converts the exercise-policy review into a deterministic, self-hashed
contract. It covers population, goals, frequency, selection, order, load,
repetitions, sets, volume, rest, effort, duration, progression, regression,
missed sessions, substitutions, training experience, weekly balance, safety,
aerobic activity and energy estimation.

The original E3 baseline remains frozen at
`apps/backend/data/exercise_prescription_policy_v1.json`. The semantic gate in
[E3.1](e3_1_prescription_policy_gate.md) supersedes it with the versioned
`apps/backend/data/exercise_prescription_policy_v1_1.json`. The implementation
and evaluators are in
`apps/backend/modules/wger/exercise_prescription_policy.py`.

E3 does not change `suggest_workout`. E4 must combine this policy with a real
Exercise Profile and Training State; E6 will integrate the resulting planner
with the chatbot.

## Evidence boundary

The primary resistance source is the 2026 ACSM Position Stand, an overview of
137 systematic reviews involving more than 30,000 healthy adults. Its primary
recommendation is high-effort progressive resistance training at least twice
weekly, engaging all major muscle groups. Strength is enhanced by loads at or
above 80% 1RM, 2–3 sets and early placement in the session; hypertrophy is
enhanced by higher weekly volume around 10 or more sets. Failure, equipment
type and complex periodization did not consistently improve outcomes.

- ACSM 2026 Position Stand: https://pubmed.ncbi.nlm.nih.gov/41843416/
- Full position stand: https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/

The policy distinguishes:

| Provenance | Meaning |
|---|---|
| `EVIDENCE_BOUND` | A boundary directly supported by the cited guideline/review |
| `EVIDENCE_BOUND_PLUS_APP_RANGE` | Evidence anchors part of the rule; app policy supplies an operational range |
| `APP_POLICY` | Conservative deterministic product behavior, not claimed as a guideline mandate |
| `APP_AUTOREGULATION_POLICY` | RIR/RPE and feedback decision used by the future progression engine |
| `SAFETY_BOUNDARY` | Delimits an ordinary fitness planner from clinical guidance |
| `APP_CATALOG_POLICY` | Deterministic catalog matching and substitution constraints |

## Supported population and safety

The ordinary planner supports adults age 18 or older seeking healthy general
or recreational fitness, without current warning symptoms, acute injury,
recent surgery, severe/worsening pain or an unresolved condition that requires
clinical prescription.

Safety states are:

- `SUPPORTED`
- `NEEDS_CLARIFICATION`
- `REQUIRES_PROFESSIONAL_GUIDANCE`
- `STOP_AND_SEEK_MEDICAL_EVALUATION`

Warning symptoms include chest pain/pressure, fainting, unusual severe
shortness of breath, dizziness/confusion and fast or uneven heartbeat. The LLM
cannot override the gate. New sharp, severe, worsening, gait-altering or
persistent pain cannot be treated as an automatic exercise substitution or a
simple reduction in load.

The HHS guideline says asymptomatic people without diagnosed chronic
conditions most likely do not need medical consultation before ordinary
activity, while people with symptoms or known conditions should obtain an
appropriate plan with a professional:
https://odphp.health.gov/sites/default/files/2019-09/Physical_Activity_Guidelines_2nd_edition.pdf.

Pregnancy/postpartum, under-18 programming, clinical rehabilitation and
complex chronic conditions are not declared unsafe; they are outside this
policy and routed to an appropriate professional or dedicated policy.

## Goals and experience

Supported goals are:

`GENERAL_FITNESS`, `STRENGTH`, `HYPERTROPHY`, `MUSCULAR_ENDURANCE`,
`WEIGHT_MANAGEMENT`, `MOBILITY`, and `POWER`.

`UNKNOWN` experience remains `UNKNOWN`. It may use the operational profile
`CONSERVATIVE_DEFAULT`, but it is never relabeled as `NOVICE`. User-reported
experience and local training-history availability are separate signals. A
power goal requires coaching/skill assessment for novices and explicit
experience confirmation for unknown experience because the ordinary planner
cannot verify lifting technique.

### Resistance defaults

| Goal | Experienced load | Reps | Sets/exercise | Experienced weekly target | Target RIR |
|---|---:|---:|---:|---:|---:|
| General fitness | 50–75% 1RM | 8–15 | 2–3 | 6–12 sets/major muscle | 2–4 |
| Strength | 80–90% 1RM | 3–6 | 2–3 | 6–12 sets/priority muscle | 2–3 |
| Hypertrophy | 60–80% 1RM | 6–15 | 2–4 | 10–18 sets/target muscle | 1–3 |
| Muscular endurance | 30–60% 1RM | 12–20 | 2–3 | 6–12 sets/major muscle | 2–3 |
| Weight management | 50–75% 1RM | 8–15 | 2–3 | 6–12 sets/major muscle | 2–4 |
| Power | 30–70% 1RM | 3–6 | 2–4 | ≤24 repetitions × sets | 3–5 |

These rep and rest bands are operational app defaults. The policy does not
claim that one narrow repetition range is uniquely optimal. ACSM reports that
many loading schemes improve strength and hypertrophy, while heavier load is
most relevant to maximizing strength.

Novices generally use two to three weekly resistance days, two sets per
exercise initially, more repetitions in reserve and lower loads. Experienced
users may use a split and higher weekly volume, but frequency is not increased
merely to create more sessions when weekly volume is already adequate.

## Selection, order and weekly balance

Selection order is:

1. Pass the safety gate.
2. Match available equipment.
3. Match goal and experience.
4. Fill weekly muscle/movement gaps.
5. Honor preferred and disliked exercises.
6. Fit the session time budget.

Sessions normally contain 4–8 resistance movements. Technical or power work
comes first when the user is eligible, followed by goal-priority multi-joint
work, other compound movements, accessories, then core/carry/cooldown.

Weekly balance is evaluated across the week, not forced into every session.
The app checks squat, hinge, horizontal push/pull, vertical push/pull and a
core anti-extension/anti-rotation pattern, with locomotion, carry and
unilateral lower-body work included when appropriate. This exact movement
taxonomy is app policy; the evidence-bound requirement is coverage of all
major muscle groups at least twice weekly.

## Rest, RPE/RIR and failure

Rest defaults preserve performance rather than pretending one interval is
universally optimal:

- heavy/priority compound: 120–300 seconds;
- other multi-joint work: 90–180 seconds;
- accessories: 45–120 seconds.

The 2026 ACSM synthesis did not find consistent long-term outcome differences
from short versus long rest. A 2024 systematic review suggests a small
hypertrophy advantage above 60 seconds, with little appreciable difference
beyond about 90 seconds: https://pubmed.ncbi.nlm.nih.gov/39205815/.

Approximate effort mapping is RIR 4/3/2/1/0 to RPE 6/7/8/9/10. It is explicitly
labelled an estimate. Failure is not required. An experienced user may
optionally reach 0–1 RIR on the final set of a stable, low-risk isolation
movement; it is not the default for novices, technical/power movements,
unsupported compounds, pain, fatigue or form breakdown.

The proximity-to-failure evidence is goal-dependent and still uncertain. The
2024 meta-regression found little relationship with strength across a broad RIR
range and an exploratory trend toward more hypertrophy closer to failure:
https://pubmed.ncbi.nlm.nih.gov/38970765/.

## Progression and regression

E3 uses double progression. A load increase is eligible only after two
consecutive exposures in which the user:

- completes every prescribed set at the top of the rep range;
- remains inside the target RIR range;
- reports stable technique;
- reports no pain or warning symptoms.

The app-policy increment is 2.5–5% for upper-body and 2.5–7.5% for lower-body
movements. These exact percentages are conservative engineering defaults, not
a claim of a universally optimal biological dose.

Two consecutive failures below the minimum reps can reduce load by 5–10% or
volume by 20–30%. Technique breakdown results in hold/reduce. Pain results in a
safety stop, not a normal regression decision.

One missed session is skipped: the user resumes the next scheduled session and
does not double sessions or chase missed weekly volume. After two or more
missed sessions or seven days away, the return session uses 20–30% less volume
and optionally 5–10% less load. Illness or injury routes through the safety
gate.

## Exercise substitution

An automatic substitution candidate must have:

- the same reviewed movement pattern;
- overlap in primary muscle;
- available equipment;
- appropriate reviewed difficulty;
- no known limitation or safety conflict.

All E2 curated taxonomy is currently marked `human_reviewed=false`, so E3
returns `REVIEW_REQUIRED` rather than silently authorizing substitutions from
those heuristics. Human review or a later trusted taxonomy release is required
before production auto-substitution.

## Aerobic activity

The weekly adult target remains 150–300 minutes of moderate aerobic activity,
75–150 minutes of vigorous activity, or a combination. One vigorous minute is
approximately two moderate minutes for guideline accounting. Inactive users
start with tolerable activity and progress duration/frequency before vigorous
intensity. Resistance training does not replace the aerobic target, and a
weight-management goal does not authorize punitive volume.

Official source:
https://odphp.health.gov/our-work/nutrition-physical-activity/physical-activity-guidelines/current-guidelines/top-10-things-know.

## Estimated exercise energy expenditure

Energy is estimated only at session/activity level using a reviewed 2024 Adult
Compendium code:

```text
estimated kcal = MET × 3.5 × weight_kg / 200 × duration_minutes
```

The initial conditioning codes cover general/vigorous resistance, general/high
intensity bodyweight work and kettlebell-style circuits. Output is labelled
`estimated_energy_expenditure_kcal`, never exact calories burned. Per-set or
invented exercise-specific calorie claims are forbidden.

The 2024 Adult Compendium table used by E3 covers ages 19–59. For another age,
the evaluator returns `AGE_APPROPRIATE_TABLE_REQUIRED` instead of applying the
wrong table. The source contains measured and estimated population METs; it is
not an individual calorimetry measurement:

- https://pacompendium.com/adult-compendium/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC10818145/

## Verification

```powershell
cd apps/backend
py -3.10 scripts/manage_exercise_prescription_policy.py --verify
py -3.10 -m pytest -q tests/test_exercise_prescription_policy_e3.py
```

To intentionally freeze a reviewed policy change:

```powershell
py -3.10 scripts/manage_exercise_prescription_policy.py --write-policy
```

Policy, evidence provenance and behavioral test changes must be reviewed
together.
