import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/off_models.dart';

/// Service gọi Open Food Facts qua backend proxy (tránh CORS trên Flutter Web)
/// Proxy: localhost:8080/off/*  →  world.openfoodfacts.org
class OpenFoodFactsService {
  // Proxy qua backend local — cùng origin với app, không bị CORS
  static const String _proxyBase = 'http://localhost:8080/off';

  static const Duration _timeout = Duration(seconds: 15);

  final http.Client _client;
  OpenFoodFactsService({http.Client? client}) : _client = client ?? http.Client();

  void dispose() => _client.close();

  /// Tìm kiếm sản phẩm theo tên
  Future<OFFSearchResponse> searchByName(String query, {int page = 1}) async {
    if (query.trim().isEmpty) {
      return OFFSearchResponse(count: 0, page: 1, pageSize: 20, products: []);
    }

    final uri = Uri.parse('$_proxyBase/search').replace(queryParameters: {
      'q': query.trim(),
      'page': page.toString(),
      'page_size': '10',
    });

    debugPrint('🌍 [OFF] Search via proxy: $query');

    try {
      final response = await _client.get(uri).timeout(_timeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
        final result = OFFSearchResponse.fromJson(data);
        debugPrint('✅ [OFF] Found ${result.products.length} products');
        return result;
      } else if (response.statusCode == 502 || response.statusCode == 503) {
        throw OFFException('Backend chưa kết nối được Open Food Facts. Kiểm tra backend đang chạy.');
      } else if (response.statusCode == 504) {
        throw OFFException('Open Food Facts phản hồi quá chậm. Thử lại sau.');
      } else {
        throw OFFException('Lỗi tìm kiếm: HTTP ${response.statusCode}');
      }
    } on TimeoutException {
      throw OFFException('Backend không phản hồi. Kiểm tra backend đang chạy tại localhost:8080.');
    } on OFFException {
      rethrow;
    } catch (e) {
      if (e.toString().contains('Connection refused') || e.toString().contains('Failed to fetch')) {
        throw OFFException('Không kết nối được backend. Hãy khởi động backend trước.');
      }
      throw OFFException('Lỗi kết nối: $e');
    }
  }

  /// Lấy sản phẩm theo barcode
  Future<OFFProduct?> getByBarcode(String barcode) async {
    if (barcode.trim().isEmpty) return null;

    final uri = Uri.parse('$_proxyBase/product/${barcode.trim()}');

    debugPrint('🌍 [OFF] Barcode via proxy: $barcode');

    try {
      final response = await _client.get(uri).timeout(_timeout);

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
        if (data['status'] == 1 && data['product'] != null) {
          final product = OFFProduct.fromJson(data);
          debugPrint('✅ [OFF] Found: ${product.name}');
          return product;
        }
        return null;
      } else if (response.statusCode == 404) {
        return null;
      } else {
        throw OFFException('Lỗi tra cứu barcode: HTTP ${response.statusCode}');
      }
    } on TimeoutException {
      throw OFFException('Kết nối quá chậm.');
    } on OFFException {
      rethrow;
    } catch (e) {
      throw OFFException('Lỗi kết nối: $e');
    }
  }
}

class OFFException implements Exception {
  final String message;
  OFFException(this.message);

  @override
  String toString() => 'OFFException: $message';
}
