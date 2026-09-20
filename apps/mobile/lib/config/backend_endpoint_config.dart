import 'package:flutter/foundation.dart';

/// Resolves the backend endpoint for the current runtime.
///
/// A build-time [API_BASE_URL] always wins. Development web builds otherwise
/// follow the hostname used to open the app, allowing the same build to work
/// through localhost, a LAN address, or a Tailscale address.
class BackendEndpointConfig {
  static const String _environmentBaseUrl =
      String.fromEnvironment('API_BASE_URL');
  static const String _desktopDefault = 'http://localhost:8080';
  static const String _androidEmulatorDefault = 'http://10.0.2.2:8080';

  static String get baseUrl => resolve();

  @visibleForTesting
  static String resolve({
    String? environmentBaseUrl,
    bool? runningOnWeb,
    Uri? browserUri,
    TargetPlatform? targetPlatform,
  }) {
    final configured = (environmentBaseUrl ?? _environmentBaseUrl).trim();
    if (configured.isNotEmpty) return _withoutTrailingSlash(configured);

    if (runningOnWeb ?? kIsWeb) {
      final location = browserUri ?? Uri.base;
      if (location.host.isNotEmpty) {
        final scheme = location.scheme == 'https' ? 'https' : 'http';
        return Uri(
          scheme: scheme,
          host: location.host,
          port: 8080,
        ).toString();
      }
    }

    final platform = targetPlatform ?? defaultTargetPlatform;
    if (platform == TargetPlatform.android) {
      return _androidEmulatorDefault;
    }
    return _desktopDefault;
  }

  static String _withoutTrailingSlash(String value) =>
      value.endsWith('/') ? value.substring(0, value.length - 1) : value;
}
