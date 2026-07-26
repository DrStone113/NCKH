import 'package:flutter/material.dart';
import '../config/svg_proxy.dart';

/// Widget load ảnh từ wger.de — tự động proxy qua backend trên Web (CORS fix).
class WgerImage extends StatelessWidget {
  final String url;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget Function(BuildContext, Object, StackTrace?)? errorBuilder;

  const WgerImage(
    this.url, {
    super.key,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.errorBuilder,
  });

  @override
  Widget build(BuildContext context) {
    return Image.network(
      SvgProxy.auto(url),
      width: width,
      height: height,
      fit: fit,
      errorBuilder: errorBuilder ??
          (_, __, ___) => Container(
                color: Colors.grey.shade800,
                child: const Icon(Icons.fitness_center, color: Colors.white38),
              ),
    );
  }
}
