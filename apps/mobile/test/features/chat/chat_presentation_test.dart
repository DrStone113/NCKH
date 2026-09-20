import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/chat_presentation.dart';

void main() {
  test('formats internal active-plan goals for users', () {
    expect(formatActivePlanGoal('lose_weight'), 'Giảm cân');
    expect(formatActivePlanGoal('GAIN_MUSCLE'), 'Tăng cơ');
    expect(formatActivePlanGoal(' maintain '), 'Duy trì cân nặng');
  });

  test('does not expose unknown internal goal codes', () {
    expect(formatActivePlanGoal('NEW_INTERNAL_GOAL'), 'Sức khỏe tổng thể');
    expect(formatActivePlanGoal(null), 'Sức khỏe tổng thể');
  });
}
