/// Models cho Open Food Facts API
/// Docs: https://openfoodfacts.github.io/openfoodfacts-server/api/

class OFFNutriments {
  final double? energyKcal100g;
  final double? proteins100g;
  final double? carbohydrates100g;
  final double? fat100g;
  final double? fiber100g;
  final double? sugars100g;
  final double? salt100g;

  OFFNutriments({
    this.energyKcal100g,
    this.proteins100g,
    this.carbohydrates100g,
    this.fat100g,
    this.fiber100g,
    this.sugars100g,
    this.salt100g,
  });

  factory OFFNutriments.fromJson(Map<String, dynamic> json) {
    double? _d(String key) {
      final v = json[key];
      if (v == null) return null;
      if (v is num) return v.toDouble();
      if (v is String) return double.tryParse(v);
      return null;
    }

    return OFFNutriments(
      energyKcal100g: _d('energy-kcal_100g') ?? _d('energy_100g'),
      proteins100g: _d('proteins_100g'),
      carbohydrates100g: _d('carbohydrates_100g'),
      fat100g: _d('fat_100g'),
      fiber100g: _d('fiber_100g'),
      sugars100g: _d('sugars_100g'),
      salt100g: _d('salt_100g'),
    );
  }

  double caloriesForGrams(double grams) => (energyKcal100g ?? 0) * grams / 100;
  double proteinForGrams(double grams) => (proteins100g ?? 0) * grams / 100;
  double carbsForGrams(double grams) => (carbohydrates100g ?? 0) * grams / 100;
  double fatForGrams(double grams) => (fat100g ?? 0) * grams / 100;
}

class OFFProduct {
  final String barcode;
  final String name;
  final String? brands;
  final String? quantity; // e.g. "200g", "1L"
  final String? imageUrl;
  final String? nutriscoreGrade; // a, b, c, d, e
  final OFFNutriments? nutriments;
  final String? servingSize; // e.g. "30g"
  final double? servingQuantity; // grams per serving

  OFFProduct({
    required this.barcode,
    required this.name,
    this.brands,
    this.quantity,
    this.imageUrl,
    this.nutriscoreGrade,
    this.nutriments,
    this.servingSize,
    this.servingQuantity,
  });

  factory OFFProduct.fromJson(Map<String, dynamic> json) {
    final product = json['product'] as Map<String, dynamic>? ?? json;

    // Name: try product_name_vi → product_name → generic_name
    final name = (product['product_name_vi'] as String?)?.trim().isNotEmpty == true
        ? product['product_name_vi'] as String
        : (product['product_name'] as String?)?.trim().isNotEmpty == true
            ? product['product_name'] as String
            : (product['generic_name'] as String?)?.trim().isNotEmpty == true
                ? product['generic_name'] as String
                : 'Sản phẩm không tên';

    // Image: front_image_url → image_url → image_front_url
    final imageUrl = product['image_front_url'] as String? ??
        product['image_url'] as String? ??
        product['image_front_small_url'] as String?;

    // Serving
    double? servingQuantity;
    final sq = product['serving_quantity'];
    if (sq != null) {
      if (sq is num) servingQuantity = sq.toDouble();
      if (sq is String) servingQuantity = double.tryParse(sq);
    }

    return OFFProduct(
      barcode: (product['code'] ?? product['_id'] ?? json['code'] ?? '').toString(),
      name: name,
      brands: product['brands'] as String?,
      quantity: product['quantity'] as String?,
      imageUrl: imageUrl,
      nutriscoreGrade: product['nutriscore_grade'] as String?,
      nutriments: product['nutriments'] != null
          ? OFFNutriments.fromJson(product['nutriments'] as Map<String, dynamic>)
          : null,
      servingSize: product['serving_size'] as String?,
      servingQuantity: servingQuantity,
    );
  }

  /// Hiển thị tên đầy đủ kèm thương hiệu
  String get displayName {
    if (brands != null && brands!.isNotEmpty) {
      return '$name — $brands';
    }
    return name;
  }

  /// Nutriscore color
  static const Map<String, int> _nutriscoreColors = {
    'a': 0xFF1E8F4E,
    'b': 0xFF86BB2D,
    'c': 0xFFF5A623,
    'd': 0xFFE07B39,
    'e': 0xFFE63E11,
  };

  int get nutriscoreColor =>
      _nutriscoreColors[nutriscoreGrade?.toLowerCase() ?? ''] ?? 0xFFADB5BD;
}

/// Response từ search API
class OFFSearchResponse {
  final int count;
  final int page;
  final int pageSize;
  final List<OFFProduct> products;

  OFFSearchResponse({
    required this.count,
    required this.page,
    required this.pageSize,
    required this.products,
  });

  factory OFFSearchResponse.fromJson(Map<String, dynamic> json) {
    final rawProducts = json['products'] as List<dynamic>? ?? [];
    final products = rawProducts
        .map((p) {
          try {
            return OFFProduct.fromJson({'product': p, 'code': p['code'] ?? p['_id'] ?? ''});
          } catch (_) {
            return null;
          }
        })
        .whereType<OFFProduct>()
        .where((p) => p.name != 'Sản phẩm không tên' && p.nutriments != null)
        .toList();

    return OFFSearchResponse(
      count: json['count'] as int? ?? products.length,
      page: json['page'] as int? ?? 1,
      pageSize: json['page_size'] as int? ?? 24,
      products: products,
    );
  }
}
