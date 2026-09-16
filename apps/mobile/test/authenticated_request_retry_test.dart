import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/services/backend_api_service.dart';

void main() {
  test('retries one time with a forced refresh after unauthorized response',
      () async {
    final refreshAttempts = <bool>[];

    final result = await retryOnceAfterUnauthorized<int>(
      operation: (forceRefresh) async {
        refreshAttempts.add(forceRefresh);
        return forceRefresh ? 200 : 401;
      },
      isUnauthorized: (status) => status == 401,
    );

    expect(result, 200);
    expect(refreshAttempts, [false, true]);
  });

  test('does not refresh a successful authenticated response', () async {
    final refreshAttempts = <bool>[];

    final result = await retryOnceAfterUnauthorized<int>(
      operation: (forceRefresh) async {
        refreshAttempts.add(forceRefresh);
        return 200;
      },
      isUnauthorized: (status) => status == 401,
    );

    expect(result, 200);
    expect(refreshAttempts, [false]);
  });

  test('never retries an unauthorized response more than once', () async {
    final refreshAttempts = <bool>[];

    final result = await retryOnceAfterUnauthorized<int>(
      operation: (forceRefresh) async {
        refreshAttempts.add(forceRefresh);
        return 401;
      },
      isUnauthorized: (status) => status == 401,
    );

    expect(result, 401);
    expect(refreshAttempts, [false, true]);
  });
}
