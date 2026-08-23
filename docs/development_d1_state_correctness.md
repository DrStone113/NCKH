# Development Phase D1 — State Correctness

This phase changes production application state contracts, not the frozen A/B/C
research experiment. It does not implement the Context Planner and does not tune
RAG.

## Status contract

`AppStateValue<T>` carries `value`, `source`, `observed_at`, `status`, and
optional conflict metadata. Status is one of `KNOWN`, `MISSING`, `NOT_LOADED`,
`ERROR`, `CONFLICT`, or `STALE`. Availability is never inferred from a numeric
value, so a measured zero remains valid.

Write tools use `PERSISTED`, `REJECTED`, or `ERROR`. A success message is emitted
only for `PERSISTED`.

## Read/freshness audit

| Tool | Previous behavior | D1 behavior |
| --- | --- | --- |
| `get_user_profile` | Send-time `UserModel` snapshot | Server Firestore profile read plus current weight-history read; snapshot is explicitly `STALE` if refresh fails |
| `get_today_meals` | Send-time list/count/totals | Forced server meal-diary read; consumed and planned meals remain distinct |
| `get_today_exercises` | Send-time list/count/totals | Forced server exercise-diary read; cache is labelled `STALE` |
| `get_weight_history` | Server read, but read failure could resemble empty history | Empty authoritative history is `KNOWN`; failure is `READ_ERROR` |
| `get_lifestyle_logs` | Provider defaults/demo observations | Forced read with field-level `MISSING`/`NOT_LOADED`/`ERROR`; defaults are never observations |
| `get_active_plan` | Backend failure and no plan both became `null` | `ACTIVE_PLAN_FOUND`, `NO_ACTIVE_PLAN`, and `READ_ERROR` |

## Meal defect root cause and fix

Chatbot-created `MealModel` values inherited `isCompleted = false`. The write
could succeed but consumed totals intentionally sum only completed meals. In
addition, `NutritionProvider.addMeal` swallowed Firestore errors, so the caller
could announce success after a failed write.

D1 creates chatbot meal logs with `isCompleted = true` (`CONSUMED`), verifies
the persisted document with a server read, and rolls back optimistic state on
failure. Existing plan-imported meals remain `PLANNED` until completed; their
semantics were not changed.

## Weight precedence

The latest weight-history measurement is canonical because it has an explicit
measurement time. `profile.current_weight` is the fallback when history is
empty. If both exist and differ by more than 0.05 kg, the latest measurement is
returned with `CONFLICT` and both candidates are recorded.

After `log_weight`, profile weight is synchronized only after the measurement
write is confirmed and only when the new measurement is the latest non-future
measurement. A backdated measurement does not overwrite current profile weight.

## Water audit

- `health.water_intake`: canonical `water_consumed_today`, stored as individual
  intake events and summed for the current day.
- `lifestyle_logs.waterIntakeMl`: legacy lifestyle-water observation. It remains
  separately exposed as `lifestyle_water_logged_today` and is not merged into
  canonical consumption.
- `UserModel.dailyWaterGoal`: derived target (`weight_kg * 0.033` litres), exposed
  as `water_target`; it is not an intake observation.

Chatbot `log_lifestyle(type=water)` now writes the canonical health-water event.
If that source has not loaded or errors, consumed water is unavailable rather
than zero-filled.

## Remaining nutrition formula conflicts (deferred to D2)

No broad formula rewrite was performed in D1.

| Concern | Implementations | Conflict |
| --- | --- | --- |
| BMI value | Flutter `UserModel.bmi`; backend prompt `_calculate_body_metrics`; chatbot `log_weight` | Same basic equation, but validation/rounding and zero-height behavior differ |
| BMI category | Flutter `UserModel.bmiCategory` and health UI; backend prompt `_calculate_body_metrics` | Flutter uses normal `<25`; backend Asian categorization uses normal `<23` and pre-overweight `<25` |
| BMR | Flutter `UserModel.bmr`; backend `tools/tdee.py`; backend prompt calculator | Same Mifflin-St Jeor core, but backend tool validates inputs while Flutter/prompt fall back differently for unknown gender/activity |
| TDEE | Flutter `UserModel.tdee`; backend `tools/tdee.py`; backend prompt calculator | Multipliers match; invalid/default handling and rounding differ |
| Calorie target | Flutter `recommendedCalories`; backend `tools/tdee.py`; backend prompt calculator; planner weekly/day adjustments; nutrition UI fallback | Base deltas mostly match (-500/+300), but only prompt/planner enforce a 1200 kcal floor; UI also has a 2000 kcal missing-user fallback |
| Protein target | Backend prompt calculator; `PlannerAgent._protein_target`; stored plan targets | Prompt uses fixed 1.8/2.0/1.2 g/kg; planner uses goal- and phase-dependent 1.4–2.0 g/kg; Flutter mainly displays stored values |
| Water target | Flutter `UserModel.dailyWaterGoal`; backend prompt calculator | Same 0.033 L/kg, different rounding and provenance handling |

## D2 `CanonicalNutritionCalculator` dependency map

The D2 calculator should own validated BMI, BMI category policy, BMR, TDEE,
goal-adjusted calories, protein, and derived water target. Migration callers:

1. Flutter domain: `UserModel` calculated getters.
2. Flutter consumers: home/health stats, nutrition progress, goal/profile/account
   settings, and `AIChatProvider` context/calculation manifest.
3. Backend deterministic tool: `services.agent.tools.tdee.calculate_tdee`.
4. Backend prompt: `system_prompt._calculate_body_metrics` and all prompt
   formatting of derived targets.
5. Planner: `PlannerAgent.createLongTermPlan`, `_protein_target`,
   `_weekly_kcal_target`, and `_day_kcal_target`.
6. Proactive nudges: `proactive_service._estimate_daily_target`.
7. Plan API/storage consumers: plan creation routes and plan detail displays.
8. Tests: TDEE tool, planner, proactive, schema, mobile `UserModel`, and UI target
   tests.

The frozen research experiment package is intentionally excluded from automatic
migration; D2 must handle it only through an explicitly versioned research
decision.

## Production safety

`DEVELOPMENT_CONTEXT_TRACE` defaults to false. Even if enabled accidentally,
tracing is blocked when `APP_ENVIRONMENT=production`. Traces are structured log
records only, redact secrets/common PII, pseudonymize user identifiers, and are
never returned over the end-user WebSocket or stored in experiment records.
