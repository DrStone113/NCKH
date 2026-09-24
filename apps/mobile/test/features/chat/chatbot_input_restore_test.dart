import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/screens/chatbot_screen.dart';
import 'package:health_app/providers/ai_chat_provider.dart';
import 'package:health_app/providers/exercise_provider.dart';
import 'package:health_app/providers/health_provider.dart';
import 'package:health_app/providers/lifestyle_provider.dart';
import 'package:health_app/providers/nutrition_provider.dart';
import 'package:health_app/providers/user_provider.dart';
import 'package:provider/provider.dart';

class PendingRestoreChatProvider extends AIChatProvider {
  final restoreStarted = Completer<void>();
  final finishRestore = Completer<bool>();

  @override
  Future<void> initLocation() async {}

  @override
  Future<bool> restoreLatestSession({
    required Future<List<Map<String, dynamic>>> Function() loadSessions,
    required Future<List<Map<String, dynamic>>> Function(String) loadMessages,
    int maxCandidates = 5,
  }) {
    restoreStarted.complete();
    return finishRestore.future;
  }

  @override
  Future<void> connect(String sessionId) async {
    setTestingTransportState(ChatTransportState.connected);
  }
}

void main() {
  testWidgets('new conversation enables input while restore is still pending',
      (tester) async {
    final chat = PendingRestoreChatProvider();
    final user = UserProvider()..setDemoUser();
    addTearDown(chat.dispose);
    addTearDown(user.dispose);

    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<AIChatProvider>.value(value: chat),
        ChangeNotifierProvider<UserProvider>.value(value: user),
        ChangeNotifierProvider(create: (_) => ExerciseProvider()),
        ChangeNotifierProvider(create: (_) => NutritionProvider()),
        ChangeNotifierProvider(create: (_) => LifestyleProvider()),
        ChangeNotifierProvider(create: (_) => HealthProvider()),
      ],
      child: const MaterialApp(home: ChatbotScreen(showBackButton: false)),
    ));
    await tester.pump();
    expect(chat.restoreStarted.isCompleted, isTrue);
    expect(chat.finishRestore.isCompleted, isFalse);
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);

    await tester.tap(find.byTooltip('Tạo cuộc trò chuyện mới'));
    await tester.pump();

    expect(chat.finishRestore.isCompleted, isFalse);
    expect(chat.currentSessionId, isNotNull);
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
    expect(
      tester
          .widget<IconButton>(find.ancestor(
            of: find.byIcon(Icons.arrow_upward_rounded),
            matching: find.byType(IconButton),
          ))
          .onPressed,
      isNotNull,
    );

    await tester.pumpWidget(const SizedBox.shrink());
    chat.finishRestore.complete(false);
  });

  testWidgets('composer predicate follows connected idle and streaming states',
      (tester) async {
    final chat = PendingRestoreChatProvider();
    final user = UserProvider()..setDemoUser();
    addTearDown(chat.dispose);
    addTearDown(user.dispose);
    chat.setTestingTransportState(ChatTransportState.connected);

    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<AIChatProvider>.value(value: chat),
        ChangeNotifierProvider<UserProvider>.value(value: user),
        ChangeNotifierProvider(create: (_) => ExerciseProvider()),
        ChangeNotifierProvider(create: (_) => NutritionProvider()),
        ChangeNotifierProvider(create: (_) => LifestyleProvider()),
        ChangeNotifierProvider(create: (_) => HealthProvider()),
      ],
      child: const MaterialApp(home: ChatbotScreen(showBackButton: false)),
    ));
    await tester.pump();

    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);
    chat.finishRestore.complete(false);
    await tester.pump();
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);

    chat.setTestingTransportState(ChatTransportState.streaming);
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isFalse);

    chat.setTestingTransportState(ChatTransportState.connected);
    await tester.pump();
    expect(tester.widget<TextField>(find.byType(TextField)).enabled, isTrue);
  });
}
