import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/wger_service.dart';
import '../models/wger_models.dart';
import '../models/meal_model.dart';
import '../providers/nutrition_provider.dart';
import '../providers/user_provider.dart';
import '../config/wger_config.dart';
import '../theme/app_theme.dart';

/// Widget tìm kiếm thực phẩm từ wger API
class WgerFoodSearchWidget extends StatefulWidget {
  final DateTime date;
  final String mealType;

  const WgerFoodSearchWidget({
    super.key,
    required this.date,
    required this.mealType,
  });

  @override
  State<WgerFoodSearchWidget> createState() => _WgerFoodSearchWidgetState();
}

class _WgerFoodSearchWidgetState extends State<WgerFoodSearchWidget> {
  final WgerService _wgerService = WgerService();
  final TextEditingController _searchController = TextEditingController();
  List<WgerIngredient> _results = [];
  bool _isSearching = false;
  Timer? _debounceTimer;
  String? _errorMessage;

  @override
  void dispose() {
    _searchController.dispose();
    _debounceTimer?.cancel();
    _wgerService.dispose();
    super.dispose();
  }

  void _onSearchChanged(String query) {
    // Cancel previous timer
    _debounceTimer?.cancel();

    // Clear error message
    setState(() {
      _errorMessage = null;
    });

    // Only search if query length >= minSearchLength
    if (query.length < WgerConfig.minSearchLength) {
      setState(() {
        _results = [];
        _isSearching = false;
      });
      return;
    }

    // Set loading state
    setState(() {
      _isSearching = true;
    });

    // Debounce search
    _debounceTimer = Timer(WgerConfig.searchDebounce, () {
      _search(query);
    });
  }

  Future<void> _search(String query) async {
    try {
      final response = await _wgerService.searchIngredients(query);
      if (mounted) {
        setState(() {
          _results = response.results;
          _isSearching = false;
          _errorMessage = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _results = [];
          _isSearching = false;
          _errorMessage = e.toString();
        });
      }
    }
  }

  void _onIngredientSelected(WgerIngredient ingredient) {
    _showWeightDialog(ingredient);
  }

  void _showWeightDialog(WgerIngredient ingredient) {
    final gramsController = TextEditingController(text: '100');
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(ingredient.name),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Nhập khối lượng (gram):',
              style: TextStyle(fontSize: 14, color: AppColors.textSecondary),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: gramsController,
              keyboardType: TextInputType.number,
              autofocus: true,
              decoration: const InputDecoration(
                labelText: 'Khối lượng',
                suffixText: 'g',
                border: OutlineInputBorder(),
              ),
              onChanged: (value) {
                // Trigger rebuild to update preview
                (context as Element).markNeedsBuild();
              },
            ),
            const SizedBox(height: 16),
            _buildNutritionPreview(ingredient, gramsController),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Huỷ'),
          ),
          ElevatedButton(
            onPressed: () {
              final grams = double.tryParse(gramsController.text);
              if (grams != null && grams > 0) {
                _addMealFromIngredient(ingredient, grams);
                Navigator.pop(context);
                Navigator.pop(context); // Close the search widget
              }
            },
            child: const Text('Thêm'),
          ),
        ],
      ),
    );
  }

  Widget _buildNutritionPreview(WgerIngredient ingredient, TextEditingController gramsController) {
    final grams = double.tryParse(gramsController.text) ?? 0;
    
    if (grams <= 0) {
      return const Text(
        'Nhập khối lượng để xem thông tin dinh dưỡng',
        style: TextStyle(fontSize: 12, color: AppColors.textSecondary, fontStyle: FontStyle.italic),
      );
    }

    final calories = ingredient.caloriesForGrams(grams);
    final protein = ingredient.proteinForGrams(grams);
    final carbs = ingredient.carbsForGrams(grams);
    final fat = ingredient.fatForGrams(grams);

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.primary.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: AppColors.primary.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Dinh dưỡng dự kiến:',
            style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.primary),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: [
              _buildNutrientInfo('🔥', calories.toStringAsFixed(0), 'kcal', AppColors.calories),
              _buildNutrientInfo('💪', protein.toStringAsFixed(1), 'g', AppColors.protein),
              _buildNutrientInfo('🌾', carbs.toStringAsFixed(1), 'g', AppColors.carbs),
              _buildNutrientInfo('🥑', fat.toStringAsFixed(1), 'g', AppColors.fat),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildNutrientInfo(String emoji, String value, String unit, Color color) {
    return Column(
      children: [
        Text(emoji, style: const TextStyle(fontSize: 16)),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: color),
        ),
        Text(
          unit,
          style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
        ),
      ],
    );
  }

  void _addMealFromIngredient(WgerIngredient ingredient, double grams) {
    final userId = Provider.of<UserProvider>(context, listen: false).currentUser?.id;
    if (userId == null) return;

    final meal = MealModel(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      userId: userId,
      name: ingredient.name,
      date: DateTime(
        widget.date.year,
        widget.date.month,
        widget.date.day,
        DateTime.now().hour,
        DateTime.now().minute,
      ),
      mealType: widget.mealType,
      weightGrams: grams,
      calories: ingredient.caloriesForGrams(grams),
      protein: ingredient.proteinForGrams(grams),
      carbs: ingredient.carbsForGrams(grams),
      fat: ingredient.fatForGrams(grams),
    );

    Provider.of<NutritionProvider>(context, listen: false).addMeal(meal);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Đã thêm "${ingredient.name}" vào nhật ký'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Search field
        TextField(
          controller: _searchController,
          decoration: InputDecoration(
            hintText: 'Tìm kiếm thực phẩm từ wger (tối thiểu ${WgerConfig.minSearchLength} ký tự)...',
            hintStyle: const TextStyle(fontSize: 13),
            prefixIcon: const Icon(Icons.search, size: 20),
            suffixIcon: _isSearching
                ? const Padding(
                    padding: EdgeInsets.all(12.0),
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : null,
            contentPadding: const EdgeInsets.symmetric(vertical: 10),
          ),
          onChanged: _onSearchChanged,
        ),
        const SizedBox(height: 12),

        // Error message
        if (_errorMessage != null)
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.error.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: AppColors.error.withOpacity(0.3)),
            ),
            child: Row(
              children: [
                const Icon(Icons.error_outline, color: AppColors.error, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _errorMessage!,
                    style: const TextStyle(fontSize: 12, color: AppColors.error),
                  ),
                ),
              ],
            ),
          ),

        // Results
        if (_searchController.text.length >= WgerConfig.minSearchLength && !_isSearching && _results.isEmpty && _errorMessage == null)
          Container(
            padding: const EdgeInsets.all(20),
            child: const Column(
              children: [
                Icon(Icons.search_off, size: 48, color: AppColors.textHint),
                SizedBox(height: 8),
                Text(
                  'Không tìm thấy thực phẩm',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              ],
            ),
          ),

        // Results list
        if (_results.isNotEmpty)
          Expanded(
            child: ListView.builder(
              shrinkWrap: true,
              itemCount: _results.length,
              itemBuilder: (context, index) {
                final ingredient = _results[index];
                return GestureDetector(
                  onTap: () => _onIngredientSelected(ingredient),
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.cardDark,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          ingredient.name,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 14,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Per 100g: ${ingredient.energy?.toStringAsFixed(0) ?? 'N/A'} kcal | '
                          'P: ${ingredient.protein?.toStringAsFixed(1) ?? 'N/A'}g | '
                          'C: ${ingredient.carbohydrates?.toStringAsFixed(1) ?? 'N/A'}g | '
                          'F: ${ingredient.fat?.toStringAsFixed(1) ?? 'N/A'}g',
                          style: const TextStyle(
                            fontSize: 11,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
      ],
    );
  }
}
