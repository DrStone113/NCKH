import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/widgets/plan_detail_bottom_sheet.dart';

void main() {
  test('breaks a 60-day roadmap into eight weeks and four days', () {
    final breakdown = planWeekBreakdown(60);

    expect(breakdown.fullWeeks, 8);
    expect(breakdown.remainingDays, 4);
    expect(breakdown.totalWeeks, 9);
    expect(formatPlanDurationByWeeks(60), '60 ngày • 8 tuần + 4 ngày');
  });

  test('scales four phases over a nine-week roadmap', () {
    final phases = [
      for (var week = 1; week <= 9; week++) planPhaseIndexForWeek(week, 9),
    ];

    expect(phases, orderedEquals([1, 1, 2, 2, 3, 3, 4, 4, 4]));
  });

  test('reads weekly schedule metadata from plan items', () {
    final schedule = planScheduleFromItems([
      {
        'payload': {
          'schedule': {
            'week_index': 9,
            'week_day': 4,
            'is_partial_week': true,
            'day_kind': 'active_recovery',
          },
        },
      },
    ]);

    expect(schedule?['week_index'], 9);
    expect(schedule?['week_day'], 4);
    expect(schedule?['is_partial_week'], isTrue);
    expect(schedule?['day_kind'], 'active_recovery');
  });

  test('formats a roadmap day with weekday and calendar date', () {
    expect(
      formatPlanDayCalendarLabel(
        startDate: '2026-08-14',
        dayIndex: 4,
      ),
      'Thứ Hai • 17/08',
    );
  });

  test('keeps missing days visible in a plan week', () {
    final grouped = groupPlanItemsByDay(
      rawItems: [
        {
          'id': 'meal-1',
          'day_index': 1,
          'item_type': 'meal',
          'title': 'Cháo cá',
        },
        {
          'id': 'outside-week',
          'day_index': 8,
          'item_type': 'meal',
          'title': 'Ngày tuần sau',
        },
      ],
      startDayIndex: 1,
      endDayIndex: 7,
    );

    expect(grouped.keys, orderedEquals([1, 2, 3, 4, 5, 6, 7]));
    expect(grouped[1], hasLength(1));
    expect(grouped[1]!.single['_originalIndex'], 0);
    expect(grouped[2], isEmpty);
    expect(grouped[7], isEmpty);
  });
}
