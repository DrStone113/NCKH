/// Read-only projections of authoritative PostgreSQL planned state.
///
/// These types intentionally do not implement Firestore serialization and do
/// not expose completion toggles. Actual diary models remain observation-only.
class PlannedMealProjection {
  final String planItemId;
  final String planId;
  final String revisionId;
  final String userId;
  final String name;
  final String mealType;
  final DateTime date;
  final double calories;
  final double protein;
  final double carbs;
  final double fat;

  const PlannedMealProjection({
    required this.planItemId,
    required this.planId,
    required this.revisionId,
    required this.userId,
    required this.name,
    required this.mealType,
    required this.date,
    required this.calories,
    required this.protein,
    required this.carbs,
    required this.fat,
  });
}

class PlannedWorkoutProjection {
  final String planItemId;
  final String planId;
  final String revisionId;
  final String userId;
  final String name;
  final DateTime date;
  final int duration;
  final double caloriesBurned;
  final String type;
  final String timeOfDay;

  const PlannedWorkoutProjection({
    required this.planItemId,
    required this.planId,
    required this.revisionId,
    required this.userId,
    required this.name,
    required this.date,
    required this.duration,
    required this.caloriesBurned,
    required this.type,
    required this.timeOfDay,
  });
}
