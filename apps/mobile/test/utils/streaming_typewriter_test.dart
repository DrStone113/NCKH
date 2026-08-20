import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/utils/streaming_typewriter.dart';

void main() {
  testWidgets('paces a burst and preserves grapheme clusters', (tester) async {
    final emitted = <String>[];
    var idleCount = 0;
    final typewriter = StreamingTypewriter(
      interval: const Duration(milliseconds: 10),
      onChunk: emitted.add,
      onIdle: () => idleCount++,
    );

    const response = 'Xin chào 👨‍👩‍👧‍👦, uống đủ nước nhé!';
    typewriter.add(response);

    expect(emitted.join(), isNot(response));
    expect(emitted, isNot(contains('👨')));

    await tester.pump(const Duration(seconds: 1));

    expect(emitted.join(), response);
    expect(emitted, contains('👨‍👩‍👧‍👦'));
    expect(emitted, isNot(contains('👨')));
    expect(idleCount, 1);
    typewriter.dispose();
  });

  testWidgets('coalesces chunks arriving in the same upstream burst',
      (tester) async {
    final emitted = <String>[];
    final typewriter = StreamingTypewriter(
      interval: const Duration(milliseconds: 10),
      onChunk: emitted.add,
      onIdle: () {},
    );

    typewriter
      ..add('Một ')
      ..add('câu ')
      ..add('trả lời được trả dồn.');

    expect(emitted.join(), 'M');

    await tester.pump(const Duration(seconds: 1));

    expect(emitted.join(), 'Một câu trả lời được trả dồn.');
    typewriter.dispose();
  });

  testWidgets('supports a faster pace for long thought streams',
      (tester) async {
    final normal = <String>[];
    final faster = <String>[];
    final normalTypewriter = StreamingTypewriter(
      interval: const Duration(milliseconds: 10),
      onChunk: normal.add,
      onIdle: () {},
    );
    final thoughtTypewriter = StreamingTypewriter(
      interval: const Duration(milliseconds: 10),
      batchMultiplier: 2,
      onChunk: faster.add,
      onIdle: () {},
    );

    normalTypewriter.add('abcdefghijklmnopqrst');
    thoughtTypewriter.add('abcdefghijklmnopqrst');

    expect(normal.join(), 'a');
    expect(faster.join(), 'ab');

    await tester.pump(const Duration(milliseconds: 20));

    expect(faster.join().length, greaterThan(normal.join().length));
    normalTypewriter.dispose();
    thoughtTypewriter.dispose();
  });

  test('uses adaptive batches for large backlogs', () {
    expect(StreamingTypewriter.batchSizeForBacklog(80), 1);
    expect(StreamingTypewriter.batchSizeForBacklog(81), 3);
    expect(StreamingTypewriter.batchSizeForBacklog(241), 6);
    expect(StreamingTypewriter.batchSizeForBacklog(601), 10);
    expect(StreamingTypewriter.batchSizeForBacklog(1201), 16);
  });
}
