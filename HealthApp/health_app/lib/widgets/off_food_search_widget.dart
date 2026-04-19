import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/off_models.dart';
import '../models/meal_model.dart';
import '../providers/nutrition_provider.dart';
import '../providers/user_provider.dart';
import '../services/off_service.dart';
import '../theme/app_theme.dart';

/// Widget tìm kiếm thực phẩm từ Open Food Facts API
class OFFFoodSearchWidget extends StatefulWidget {
  final DateTime date;
  final String mealType;

  const OFFFoodSearchWidget({
    super.key,
    required this.date,
    required this.mealType,
  });

  @override
  State<OFFFoodSearchWidget> createState() => _OFFFoodSearchWidgetState();
}

class _OFFFoodSearchWidgetState extends State<OFFFoodSearchWidget> {
  final OpenFoodFactsService _offService = OpenFoodFactsService();
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _barcodeController = TextEditingController();

  List<OFFProduct> _results = [];
  bool _isSearching = false;
  bool _isBarcodeLookup = false;
  Timer? _debounceTimer;
  String? _errorMessage;
  int _currentPage = 1;
  bool _hasMore = false;

  @override
  void dispose() {
    _searchController.dispose();
    _barcodeController.dispose();
    _debounceTimer?.cancel();
    _offService.dispose();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    _debounceTimer?.cancel();
    setState(() => _errorMessage = null);

    if (query.trim().length < 2) {
      setState(() {
        _results = [];
        _isSearching = false;
        _hasMore = false;
      });
      return;
    }

    setState(() => _isSearching = true);
    _debounceTimer = Timer(const Duration(milliseconds: 600), () {
      _currentPage = 1;
      _search(query.trim(), reset: true);
    });
  }

  Future<void> _search(String query, {bool reset = false}) async {
    if (reset) {
      setState(() {
        _results = [];
        _currentPage = 1;
        _isSearching = true;
      });
    }

    try {
      final response = await _offService.searchByName(query, page: _currentPage);
      if (mounted) {
        setState(() {
          if (reset) {
            _results = response.products;
          } else {
            _results.addAll(response.products);
          }
          _isSearching = false;
          _errorMessage = null;
          _hasMore = response.products.length >= 10;
          _currentPage++;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isSearching = false;
          _errorMessage = e is OFFException ? e.message : 'Lỗi kết nối Open Food Facts';
        });
      }
    }
  }

  Future<void> _lookupBarcode(String barcode) async {
    if (barcode.trim().isEmpty) return;
    setState(() {
      _isBarcodeLookup = true;
      _errorMessage = null;
    });

    try {
      final product = await _offService.getByBarcode(barcode.trim());
      if (mounted) {
        setState(() => _isBarcodeLookup = false);
        if (product != null) {
          _showAddDialog(product);
        } else {
          setState(() => _errorMessage = 'Không tìm thấy sản phẩm với barcode "$barcode"');
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isBarcodeLookup = false;
          _errorMessage = e is OFFException ? e.message : 'Lỗi tra cứu barcode';
        });
      }
    }
  }

  void _showAddDialog(OFFProduct product) {
    final nutriments = product.nutriments;
    if (nutriments == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Sản phẩm này chưa có dữ liệu dinh dưỡng'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }

    // Default grams: serving_quantity nếu có, không thì 100g
    final defaultGrams = product.servingQuantity?.toStringAsFixed(0) ?? '100';
    final gramsController = TextEditingController(text: defaultGrams);

    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) {
          final grams = double.tryParse(gramsController.text) ?? 0;
          return AlertDialog(
            backgroundColor: AppColors.surface,
            title: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  product.name,
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
                if (product.brands != null && product.brands!.isNotEmpty)
                  Text(
                    product.brands!,
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Nutriscore badge
                  if (product.nutriscoreGrade != null)
                    _buildNutriscoreBadge(product.nutriscoreGrade!),
                  const SizedBox(height: 12),

                  // Per 100g info
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceLight,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'Dinh dưỡng / 100g:',
                          style: TextStyle(fontSize: 11, color: AppColors.textSecondary, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 6),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceAround,
                          children: [
                            _nutriStat('🔥', '${nutriments.energyKcal100g?.toStringAsFixed(0) ?? '?'}', 'kcal', AppColors.calories),
                            _nutriStat('💪', '${nutriments.proteins100g?.toStringAsFixed(1) ?? '?'}', 'g P', AppColors.protein),
                            _nutriStat('🌾', '${nutriments.carbohydrates100g?.toStringAsFixed(1) ?? '?'}', 'g C', AppColors.carbs),
                            _nutriStat('🥑', '${nutriments.fat100g?.toStringAsFixed(1) ?? '?'}', 'g F', AppColors.fat),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),

                  // Gram input
                  TextField(
                    controller: gramsController,
                    keyboardType: TextInputType.number,
                    autofocus: true,
                    decoration: InputDecoration(
                      labelText: 'Khối lượng',
                      suffixText: 'g',
                      helperText: product.servingSize != null
                          ? '1 khẩu phần = ${product.servingSize}'
                          : null,
                    ),
                    onChanged: (_) => setDialogState(() {}),
                  ),

                  // Quick gram options
                  const SizedBox(height: 8),
                  _buildQuickGrams(gramsController, product, setDialogState),

                  // Preview
                  if (grams > 0) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.06),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: AppColors.primary.withOpacity(0.2)),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.info_outline, size: 13, color: AppColors.primary),
                              const SizedBox(width: 4),
                              Text(
                                'Dinh dưỡng cho ${grams.toStringAsFixed(0)}g:',
                                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.primary),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceAround,
                            children: [
                              _nutriStat('🔥', nutriments.caloriesForGrams(grams).toStringAsFixed(0), 'kcal', AppColors.calories),
                              _nutriStat('💪', nutriments.proteinForGrams(grams).toStringAsFixed(1), 'g', AppColors.protein),
                              _nutriStat('🌾', nutriments.carbsForGrams(grams).toStringAsFixed(1), 'g', AppColors.carbs),
                              _nutriStat('🥑', nutriments.fatForGrams(grams).toStringAsFixed(1), 'g', AppColors.fat),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Huỷ'),
              ),
              ElevatedButton(
                onPressed: grams > 0
                    ? () {
                        _addMeal(product, grams);
                        Navigator.pop(ctx);
                        Navigator.pop(context); // Close search sheet
                      }
                    : null,
                child: const Text('Thêm vào nhật ký'),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildNutriscoreBadge(String grade) {
    final colors = {
      'a': const Color(0xFF1E8F4E),
      'b': const Color(0xFF86BB2D),
      'c': const Color(0xFFF5A623),
      'd': const Color(0xFFE07B39),
      'e': const Color(0xFFE63E11),
    };
    final color = colors[grade.toLowerCase()] ?? AppColors.textHint;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(6),
          ),
          child: Text(
            'Nutri-Score ${grade.toUpperCase()}',
            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
          ),
        ),
      ],
    );
  }

  Widget _buildQuickGrams(
    TextEditingController ctrl,
    OFFProduct product,
    StateSetter setDialogState,
  ) {
    final options = <int>[];
    if (product.servingQuantity != null) {
      options.add(product.servingQuantity!.round());
    }
    for (final g in [50, 100, 150, 200]) {
      if (!options.contains(g)) options.add(g);
    }
    options.sort();

    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: options.map((g) {
        final isSelected = ctrl.text == g.toString();
        return GestureDetector(
          onTap: () => setDialogState(() => ctrl.text = g.toString()),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: isSelected ? AppColors.primary : AppColors.primary.withOpacity(0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: AppColors.primary.withOpacity(isSelected ? 1 : 0.3),
              ),
            ),
            child: Text(
              '${g}g${product.servingQuantity?.round() == g ? ' (1 khẩu phần)' : ''}',
              style: TextStyle(
                fontSize: 11,
                color: isSelected ? Colors.white : AppColors.primary,
                fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
              ),
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _nutriStat(String emoji, String value, String unit, Color color) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 14)),
        const SizedBox(height: 2),
        Text(value, style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: color)),
        Text(unit, style: const TextStyle(fontSize: 10, color: AppColors.textSecondary)),
      ],
    );
  }

  void _addMeal(OFFProduct product, double grams) {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;
    final nutriments = product.nutriments!;

    final item = MealItem(
      id: '${DateTime.now().millisecondsSinceEpoch}_item',
      foodId: product.barcode.isNotEmpty ? 'off_${product.barcode}' : 'off_unknown',
      name: product.name,
      weightGrams: grams,
      calories: nutriments.caloriesForGrams(grams),
      protein: nutriments.proteinForGrams(grams),
      carbs: nutriments.carbsForGrams(grams),
      fat: nutriments.fatForGrams(grams),
    );

    final meal = MealModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: userId,
      name: product.name,
      date: DateTime(
        widget.date.year, widget.date.month, widget.date.day,
        DateTime.now().hour, DateTime.now().minute,
      ),
      mealType: widget.mealType,
      items: [item],
    );

    Provider.of<NutritionProvider>(context, listen: false).addMeal(meal);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('✅ Đã thêm "${product.name}" (${grams.toStringAsFixed(0)}g) vào nhật ký'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Header badge
        Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: const Color(0xFF00A651).withOpacity(0.1),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: const Color(0xFF00A651).withOpacity(0.3)),
              ),
              child: const Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('🌍', style: TextStyle(fontSize: 12)),
                  SizedBox(width: 4),
                  Text(
                    'Open Food Facts',
                    style: TextStyle(fontSize: 11, color: Color(0xFF00A651), fontWeight: FontWeight.w600),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            const Text(
              '3M+ sản phẩm toàn cầu',
              style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
            ),
          ],
        ),
        const SizedBox(height: 10),

        // Barcode input
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _barcodeController,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  hintText: 'Nhập barcode sản phẩm...',
                  hintStyle: TextStyle(fontSize: 13),
                  prefixIcon: Icon(Icons.qr_code, size: 20),
                  contentPadding: EdgeInsets.symmetric(vertical: 10),
                ),
                onSubmitted: _lookupBarcode,
              ),
            ),
            const SizedBox(width: 8),
            SizedBox(
              height: 44,
              child: ElevatedButton(
                onPressed: _isBarcodeLookup
                    ? null
                    : () => _lookupBarcode(_barcodeController.text),
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                ),
                child: _isBarcodeLookup
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('Tra cứu', style: TextStyle(fontSize: 13)),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),

        // Divider
        Row(
          children: [
            const Expanded(child: Divider()),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Text('hoặc tìm theo tên', style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
            ),
            const Expanded(child: Divider()),
          ],
        ),
        const SizedBox(height: 8),

        // Name search
        TextField(
          controller: _searchController,
          decoration: InputDecoration(
            hintText: 'Tìm sản phẩm (vd: sữa vinamilk, bánh oreo)...',
            hintStyle: const TextStyle(fontSize: 13),
            prefixIcon: const Icon(Icons.search, size: 20),
            suffixIcon: _isSearching
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : _searchController.text.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear, size: 18),
                        onPressed: () {
                          _searchController.clear();
                          setState(() {
                            _results = [];
                            _errorMessage = null;
                          });
                        },
                      )
                    : null,
            contentPadding: const EdgeInsets.symmetric(vertical: 10),
          ),
          onChanged: _onSearchChanged,
        ),
        const SizedBox(height: 8),

        // Error
        if (_errorMessage != null)
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.error.withOpacity(0.08),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.error.withOpacity(0.3)),
            ),
            child: Row(
              children: [
                const Icon(Icons.error_outline, color: AppColors.error, size: 16),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(_errorMessage!, style: const TextStyle(fontSize: 12, color: AppColors.error)),
                ),
              ],
            ),
          ),

        // Empty state
        if (_searchController.text.length >= 2 && !_isSearching && _results.isEmpty && _errorMessage == null)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 20),
            child: Center(
              child: Column(
                children: [
                  Icon(Icons.search_off, size: 40, color: AppColors.textHint),
                  SizedBox(height: 8),
                  Text('Không tìm thấy sản phẩm', style: TextStyle(color: AppColors.textSecondary)),
                  SizedBox(height: 4),
                  Text(
                    'Thử tìm bằng tiếng Anh hoặc nhập barcode',
                    style: TextStyle(fontSize: 11, color: AppColors.textHint),
                  ),
                ],
              ),
            ),
          ),

        // Results
        if (_results.isNotEmpty)
          Expanded(
            child: ListView.builder(
              itemCount: _results.length + (_hasMore ? 1 : 0),
              itemBuilder: (context, index) {
                if (index == _results.length) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Center(
                      child: TextButton.icon(
                        onPressed: _isSearching
                            ? null
                            : () => _search(_searchController.text.trim()),
                        icon: const Icon(Icons.expand_more, size: 18),
                        label: const Text('Tải thêm', style: TextStyle(fontSize: 13)),
                      ),
                    ),
                  );
                }
                return _buildProductCard(_results[index]);
              },
            ),
          ),
      ],
    );
  }

  Widget _buildProductCard(OFFProduct product) {
    final nutriments = product.nutriments;
    return GestureDetector(
      onTap: () => _showAddDialog(product),
      child: Container(
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: AppColors.surfaceLight),
        ),
        child: Row(
          children: [
            // Product image or placeholder
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: product.imageUrl != null
                  ? Image.network(
                      product.imageUrl!,
                      width: 52,
                      height: 52,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => _imagePlaceholder(),
                    )
                  : _imagePlaceholder(),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    product.name,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (product.brands != null && product.brands!.isNotEmpty)
                    Text(
                      product.brands!,
                      style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  const SizedBox(height: 4),
                  if (nutriments != null)
                    Text(
                      '${nutriments.energyKcal100g?.toStringAsFixed(0) ?? '?'} kcal  '
                      'P:${nutriments.proteins100g?.toStringAsFixed(0) ?? '?'}g  '
                      'C:${nutriments.carbohydrates100g?.toStringAsFixed(0) ?? '?'}g  '
                      'F:${nutriments.fat100g?.toStringAsFixed(0) ?? '?'}g  '
                      '(per 100g)',
                      style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Column(
              children: [
                if (product.nutriscoreGrade != null)
                  Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: Color(product.nutriscoreColor),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Center(
                      child: Text(
                        product.nutriscoreGrade!.toUpperCase(),
                        style: const TextStyle(color: Colors.white, fontSize: 13, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                const SizedBox(height: 4),
                const Icon(Icons.add_circle_outline, size: 18, color: AppColors.textHint),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _imagePlaceholder() {
    return Container(
      width: 52,
      height: 52,
      decoration: BoxDecoration(
        color: AppColors.surfaceLight,
        borderRadius: BorderRadius.circular(8),
      ),
      child: const Icon(Icons.fastfood, size: 24, color: AppColors.textHint),
    );
  }
}
