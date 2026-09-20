String formatActivePlanGoal(Object? rawGoal) {
  final goal = rawGoal?.toString().trim().toLowerCase();
  switch (goal) {
    case 'lose_weight':
      return 'Giảm cân';
    case 'gain_muscle':
      return 'Tăng cơ';
    case 'maintain':
      return 'Duy trì cân nặng';
    default:
      return 'Sức khỏe tổng thể';
  }
}
