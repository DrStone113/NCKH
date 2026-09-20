import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/features/chat/chat_tail_follower.dart';

void main() {
  testWidgets(
    'follows streamed message growth and footer height changes to the bottom',
    (tester) async {
      tester.view.physicalSize = const Size(390, 650);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final key = GlobalKey<_TailFollowerHarnessState>();
      await tester.pumpWidget(
        MaterialApp(home: _TailFollowerHarness(key: key)),
      );

      key.currentState!.follow();
      await _pumpSettledFrames(tester);
      _expectAtBottom(key.currentState!.controller);

      key.currentState!.growStreamingMessage();
      await _pumpSettledFrames(tester);
      _expectAtBottom(key.currentState!.controller);

      key.currentState!.growFooter();
      await _pumpSettledFrames(tester);
      _expectAtBottom(key.currentState!.controller);
    },
  );
}

Future<void> _pumpSettledFrames(WidgetTester tester) async {
  for (var i = 0; i < 6; i += 1) {
    await tester.pump();
  }
}

void _expectAtBottom(ScrollController controller) {
  expect(controller.hasClients, isTrue);
  expect(controller.position.extentAfter, lessThanOrEqualTo(0.5));
}

class _TailFollowerHarness extends StatefulWidget {
  const _TailFollowerHarness({super.key});

  @override
  State<_TailFollowerHarness> createState() => _TailFollowerHarnessState();
}

class _TailFollowerHarnessState extends State<_TailFollowerHarness> {
  final controller = ScrollController();
  late final follower = ChatTailFollower(controller);
  double messageHeight = 180;
  double footerHeight = 64;

  void follow() => follower.request(settleFrames: 4);

  void growStreamingMessage() {
    setState(() => messageHeight = 420);
    follow();
  }

  void growFooter() {
    setState(() => footerHeight = 144);
    follow();
  }

  @override
  void dispose() {
    follower.dispose();
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          Expanded(
            child: ListView(
              controller: controller,
              children: [
                const SizedBox(height: 700),
                SizedBox(height: messageHeight),
              ],
            ),
          ),
          SizedBox(height: footerHeight),
        ],
      ),
    );
  }
}
