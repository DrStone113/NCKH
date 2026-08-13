import 'location_helper_stub.dart'
    if (dart.library.html) 'location_helper_web.dart' as impl;

class LocationHelper {
  static Future<Map<String, double>?> getUserLocation() {
    return impl.getUserLocation();
  }
}
