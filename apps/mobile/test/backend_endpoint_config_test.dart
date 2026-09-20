import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/config/backend_endpoint_config.dart';

void main() {
  group('BackendEndpointConfig', () {
    test('build-time endpoint takes precedence and is normalized', () {
      expect(
        BackendEndpointConfig.resolve(
          environmentBaseUrl: ' https://api.example.test/ ',
          runningOnWeb: true,
          browserUri: Uri.parse('http://100.114.7.37:3000'),
        ),
        'https://api.example.test',
      );
    });

    test('web endpoint follows the Tailscale host used by the browser', () {
      expect(
        BackendEndpointConfig.resolve(
          environmentBaseUrl: '',
          runningOnWeb: true,
          browserUri: Uri.parse('http://100.114.7.37:3000/login'),
        ),
        'http://100.114.7.37:8080',
      );
    });

    test('web endpoint preserves HTTPS for a secure origin', () {
      expect(
        BackendEndpointConfig.resolve(
          environmentBaseUrl: '',
          runningOnWeb: true,
          browserUri: Uri.parse(
            'https://desktop-pogrov1.tail725584.ts.net/login',
          ),
        ),
        'https://desktop-pogrov1.tail725584.ts.net:8080',
      );
    });

    test('Android native defaults to the emulator host', () {
      expect(
        BackendEndpointConfig.resolve(
          environmentBaseUrl: '',
          runningOnWeb: false,
          targetPlatform: TargetPlatform.android,
        ),
        'http://10.0.2.2:8080',
      );
    });

    test('desktop native defaults to localhost', () {
      expect(
        BackendEndpointConfig.resolve(
          environmentBaseUrl: '',
          runningOnWeb: false,
          targetPlatform: TargetPlatform.windows,
        ),
        'http://localhost:8080',
      );
    });
  });
}
