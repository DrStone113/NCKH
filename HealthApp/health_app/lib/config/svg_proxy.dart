import 'package:flutter/foundation.dart';
import 'wger_config.dart';

/// Proxy URL helper — giải quyết CORS khi Flutter Web fetch tài nguyên từ wger.de.
/// Native (Android/iOS) dùng URL gốc, Web dùng proxy qua backend.
class SvgProxy {
  static String get _base =>
      WgerConfig.baseUrl.replaceAll(RegExp(r'/wger.*$'), '');

  /// Proxy SVG nhóm cơ: /static/images/muscles/...
  static String resolve(String wgerUrl) {
    if (!kIsWeb) return wgerUrl;
    final path = Uri.tryParse(wgerUrl)?.path;
    if (path == null) return wgerUrl;
    return '$_base/wger/svg?path=${Uri.encodeComponent(path)}';
  }

  /// Proxy ảnh bài tập: /media/exercise-images/...
  static String resolveImage(String wgerUrl) {
    if (!kIsWeb) return wgerUrl;
    final path = Uri.tryParse(wgerUrl)?.path;
    if (path == null) return wgerUrl;
    return '$_base/wger/img?path=${Uri.encodeComponent(path)}';
  }

  /// Tự động chọn proxy đúng dựa vào URL
  static String auto(String wgerUrl) {
    if (!kIsWeb) return wgerUrl;
    if (wgerUrl.contains('/media/exercise-images/')) {
      return resolveImage(wgerUrl);
    }
    if (wgerUrl.contains('/static/images/muscles/')) {
      return resolve(wgerUrl);
    }
    return wgerUrl;
  }
}
