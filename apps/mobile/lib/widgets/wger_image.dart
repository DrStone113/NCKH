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
    final pixelRatio = MediaQuery.devicePixelRatioOf(context);
    final cacheWidth = width != null && width!.isFinite
        ? (width! * pixelRatio).round().clamp(1, 4096)
        : null;
    final cacheHeight = height != null && height!.isFinite
        ? (height! * pixelRatio).round().clamp(1, 4096)
        : null;
    return Image.network(
      SvgProxy.auto(url),
      width: width,
      height: height,
      fit: fit,
      cacheWidth: cacheWidth,
      cacheHeight: cacheHeight,
      filterQuality: FilterQuality.low,
      gaplessPlayback: true,
      loadingBuilder: (context, child, progress) {
        if (progress == null) return child;
        return Container(
          width: width,
          height: height,
          color: Colors.grey.shade100,
          alignment: Alignment.center,
          child: const SizedBox.square(
            dimension: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        );
      },
      errorBuilder: errorBuilder ??
          (_, __, ___) => Container(
                color: Colors.grey.shade800,
                child: const Icon(Icons.fitness_center, color: Colors.white38),
              ),
    );
  }
}
