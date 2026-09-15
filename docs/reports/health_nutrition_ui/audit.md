# Health and nutrition UI audit — 2026-09-08

Before-edit inventory:

| Surface | Existing implementation | Source / navigation |
| --- | --- | --- |
| Profile entry | `AuthWrapper`, `ProfileCompletionNotice` | UserProvider completeness gates; MaterialPageRoute, no separate named route |
| General / nutrition safety | `ProfileSettingsScreen` | UserModel, canonical nutrition, UserProvider explicit save |
| Nutrition / workout / safety intake | `WorkoutAccountIntakeScreen` | HealthProfile V2, NutritionProfile, WorkoutProfile; existing explicit completion methods |
| Nutrition today / diary | `NutritionScreen` | NutritionProvider selectedDate and canonicalDailySummary; existing home tab |
| Plan on selected day | `PlannedDayPlanSection` | PlanHistoryRepository and PlanHistoryResolver; read-only exact revision |
| Plan library / daily detail | `PlanListScreen`, `PlanDetailScreen`, `VersionedPlanCard` | PlanSnapshot, PlanDisplay, existing exact revision reads and lifecycle actions |
| Meal selection / saved meals | `_AddMealSheet`, `_SampleMealsTab`, `_SavedMealsTab`, `_FoodPickerList` | Existing catalog, saved templates and exact ingredient selection |
| Meal / recommendation card | `MealSummaryCard`, chat `_MealActionCard` | Existing meal/action models, public reason codes |
| Meal detail | Generic `DetailBottomSheet` for ingredient / exercise details | No existing aggregate dish detail; add shared `MealDetailContent` using existing ingredient and serving values |
| Recommendation feedback | `RecommendationFeedbackBar` | Existing N3.2.1 callback and exact recommendation identity; separate from logging |

Design foundation: AppColors primary #111827, off-white #F8FAFC, white surfaces;
existing calorie/protein/carbs/fat accents. AppSpacing 4/8/16/24/32; AppRadius
18/24 for cards and 14/18 for controls. Keep existing home bottom navigation
and plan entry points. No new planner, provider, remote image source or API.

Reference images were not present in the message; use the written direction.
Visual checks use native Flutter test rendering, never browser automation.
`protected-baseline.json` captures existing backend, model, provider, service
and asset content (including pre-existing working changes) before UI edits.
