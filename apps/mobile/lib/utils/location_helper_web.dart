import 'dart:html' as html;

Future<Map<String, double>?> getUserLocation() async {
  try {
    final geo = html.window.navigator.geolocation;
    final position = await geo.getCurrentPosition();
    final coords = position.coords;
    if (coords != null) {
      return {
        'latitude': coords.latitude?.toDouble() ?? 0.0,
        'longitude': coords.longitude?.toDouble() ?? 0.0,
      };
    }
  } catch (e) {
    // Geolocation not supported, permission denied, or timeout
  }
  return null;
}
