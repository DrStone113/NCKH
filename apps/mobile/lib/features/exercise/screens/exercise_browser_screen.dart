import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../../services/local_exercise_service.dart';
import '../../../models/wger_models.dart';
import '../../../models/exercise_model.dart';
import '../../../providers/exercise_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../theme/app_theme.dart';
import '../../../widgets/wger_image.dart';
import 'exercise_detail_screen.dart';

class ExerciseBrowserScreen extends StatefulWidget {
  const ExerciseBrowserScreen({super.key});

  @override
  State<ExerciseBrowserScreen> createState() => _ExerciseBrowserScreenState();
}

class _ExerciseBrowserScreenState extends State<ExerciseBrowserScreen> {
  final LocalExerciseService _local = LocalExerciseService();
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();

  bool _isLoading = true;
  String _searchQuery = '';
  String? _selectedCategory;
  int? _selectedMuscleId;
  String? _selectedMuscleLabel;

  // Pagination
  static const int _pageSize = 20;
  int _currentPage = 1;
  List<WgerExercise> _displayedExercises = [];
  List<WgerExercise> _filteredExercises = [];

  @override
  void initState() {
    super.initState();
    _loadData();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 200) {
      _loadMorePage();
    }
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);
    await _local.loadExercises();
    _applyFilter();
    setState(() => _isLoading = false);
  }

  void _applyFilter() {
    var list = _local.allExercises;

    if (_selectedCategory != null) {
      list = list.where((e) => e.categoryName == _selectedCategory).toList();
    }
    if (_selectedMuscleId != null) {
      list = list.where((e) =>
          e.muscles.any((m) => m.id == _selectedMuscleId) ||
          e.musclesSecondary.any((m) => m.id == _selectedMuscleId)).toList();
    }
    if (_searchQuery.isNotEmpty) {
      final q = _searchQuery.toLowerCase();
      list = list.where((e) => e.name.toLowerCase().contains(q)).toList();
    }

    _filteredExercises = list;
    _currentPage = 1;
    _displayedExercises = _local.getPage(_filteredExercises, 1, pageSize: _pageSize);
  }

  void _loadMorePage() {
    final nextPage = _currentPage + 1;
    final more = _local.getPage(_filteredExercises, nextPage, pageSize: _pageSize);
    if (more.isEmpty) return;
    setState(() {
      _displayedExercises.addAll(more);
      _currentPage = nextPage;
    });
  }

  bool get _hasMore =>
      _displayedExercises.length < _filteredExercises.length;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('Khám phá bài tập'),
        actions: [
          if (!_isLoading)
            Padding(
              padding: const EdgeInsets.only(right: 12),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.success.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.offline_bolt, size: 13, color: AppColors.success),
                      const SizedBox(width: 4),
                      Text(
                        '${_local.allExercises.length} bài',
                        style: const TextStyle(fontSize: 11, color: AppColors.success, fontWeight: FontWeight.w600),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
      body: _isLoading ? _buildLoading() : _buildContent(),
    );
  }

  Widget _buildLoading() {
    return const Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(),
          SizedBox(height: 16),
          Text('Đang tải dữ liệu bài tập...', style: TextStyle(color: AppColors.textSecondary)),
        ],
      ),
    );
  }

  Widget _buildContent() {
    return Column(
      children: [
        _buildSearchAndFilter(),
        _buildResultCount(),
        Expanded(child: _buildExerciseList()),
      ],
    );
  }

  Widget _buildSearchAndFilter() {
    return Container(
      color: AppColors.surface,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      child: Column(
        children: [
          // Search bar
          TextField(
            controller: _searchController,
            decoration: InputDecoration(
              hintText: 'Tìm bài tập...',
              prefixIcon: const Icon(Icons.search, size: 20),
              suffixIcon: _searchQuery.isNotEmpty
                  ? IconButton(
                      icon: const Icon(Icons.clear, size: 18),
                      onPressed: () {
                        _searchController.clear();
                        setState(() {
                          _searchQuery = '';
                          _applyFilter();
                        });
                      },
                    )
                  : null,
              contentPadding: const EdgeInsets.symmetric(vertical: 10),
              filled: true,
              fillColor: AppColors.surfaceLight,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
            ),
            onChanged: (val) {
              setState(() {
                _searchQuery = val;
                _applyFilter();
              });
            },
          ),
          const SizedBox(height: 10),
          // Filter chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                // Category filter
                _buildFilterChip(
                  label: _selectedCategory ?? 'Tất cả',
                  icon: Icons.category_outlined,
                  isActive: _selectedCategory != null,
                  onTap: _showCategoryPicker,
                ),
                const SizedBox(width: 8),
                // Muscle filter
                _buildFilterChip(
                  label: _selectedMuscleLabel ?? 'Nhóm cơ',
                  icon: Icons.accessibility_new,
                  isActive: _selectedMuscleId != null,
                  onTap: _showMusclePicker,
                ),
                if (_selectedCategory != null || _selectedMuscleId != null) ...[
                  const SizedBox(width: 8),
                  GestureDetector(
                    onTap: () {
                      setState(() {
                        _selectedCategory = null;
                        _selectedMuscleId = null;
                        _selectedMuscleLabel = null;
                        _applyFilter();
                      });
                    },
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                      decoration: BoxDecoration(
                        color: AppColors.error.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(color: AppColors.error.withValues(alpha: 0.3)),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.close, size: 14, color: AppColors.error),
                          SizedBox(width: 4),
                          Text('Xoá lọc', style: TextStyle(fontSize: 12, color: AppColors.error)),
                        ],
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip({
    required String label,
    required IconData icon,
    required bool isActive,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isActive ? AppColors.primary.withValues(alpha: 0.15) : AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isActive ? AppColors.primary.withValues(alpha: 0.5) : AppColors.surfaceLight,
          ),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: isActive ? AppColors.primary : AppColors.textSecondary),
            const SizedBox(width: 5),
            Text(
              label,
              style: TextStyle(
                fontSize: 12,
                color: isActive ? AppColors.primary : AppColors.textSecondary,
                fontWeight: isActive ? FontWeight.w600 : FontWeight.normal,
              ),
            ),
            const SizedBox(width: 4),
            Icon(Icons.arrow_drop_down, size: 16,
                color: isActive ? AppColors.primary : AppColors.textSecondary),
          ],
        ),
      ),
    );
  }

  Widget _buildResultCount() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          Text(
            '${_filteredExercises.length} bài tập',
            style: const TextStyle(fontSize: 13, color: AppColors.textSecondary),
          ),
          if (_selectedCategory != null || _selectedMuscleId != null || _searchQuery.isNotEmpty)
            Text(
              ' (đã lọc)',
              style: TextStyle(fontSize: 12, color: AppColors.primary.withValues(alpha: 0.8)),
            ),
        ],
      ),
    );
  }

  Widget _buildExerciseList() {
    if (_filteredExercises.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.search_off, size: 56, color: AppColors.textHint),
            const SizedBox(height: 12),
            const Text('Không tìm thấy bài tập', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            TextButton(
              onPressed: () {
                setState(() {
                  _searchController.clear();
                  _searchQuery = '';
                  _selectedCategory = null;
                  _selectedMuscleId = null;
                  _selectedMuscleLabel = null;
                  _applyFilter();
                });
              },
              child: const Text('Xoá bộ lọc'),
            ),
          ],
        ),
      );
    }

    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.all(16),
      itemCount: _displayedExercises.length + (_hasMore ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _displayedExercises.length) {
          return const Padding(
            padding: EdgeInsets.all(16),
            child: Center(child: CircularProgressIndicator()),
          );
        }
        return _buildExerciseCard(_displayedExercises[index]);
      },
    );
  }

  Widget _buildExerciseCard(WgerExercise exercise) {
    final categoryColors = {
      'Arms': const Color(0xFF667eea),
      'Legs': const Color(0xFFf5576c),
      'Abs': const Color(0xFF4facfe),
      'Chest': const Color(0xFFfa709a),
      'Back': const Color(0xFF30cfd0),
      'Shoulders': const Color(0xFF43e97b),
      'Cardio': const Color(0xFFff9a56),
      'Calves': const Color(0xFFa18cd1),
    };
    final color = categoryColors[exercise.categoryName] ?? AppColors.primary;

    return GestureDetector(
      onTap: () => _openDetail(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 14),
        decoration: BoxDecoration(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: AppColors.surfaceLight),
          boxShadow: [
            BoxShadow(color: Colors.black.withValues(alpha: 0.05), blurRadius: 8, offset: const Offset(0, 2)),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Image / Gradient header
            ClipRRect(
              borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
              child: SizedBox(
                height: 160,
                width: double.infinity,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    // Background
                    if (exercise.imageUrl != null)
                      WgerImage(
                        exercise.imageUrl!,
                        fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => _gradientBg(color),
                      )
                    else
                      _gradientBg(color),
                    // Gradient overlay
                    Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [Colors.transparent, Colors.black.withValues(alpha: 0.6)],
                        ),
                      ),
                    ),
                    // Category badge
                    Positioned(
                      top: 10,
                      left: 12,
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: color.withValues(alpha: 0.9),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          exercise.categoryName.toUpperCase(),
                          style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.white, letterSpacing: 0.5),
                        ),
                      ),
                    ),
                    // Equipment badge
                    if (exercise.equipment.isNotEmpty)
                      Positioned(
                        top: 10,
                        right: 12,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.55),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.build_circle, size: 11, color: Colors.white70),
                              const SizedBox(width: 4),
                              Text(
                                exercise.equipment.first.name,
                                style: const TextStyle(fontSize: 10, color: Colors.white70),
                              ),
                            ],
                          ),
                        ),
                      ),
                    // Name at bottom
                    Positioned(
                      left: 12,
                      right: 12,
                      bottom: 10,
                      child: Text(
                        exercise.name,
                        style: const TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          shadows: [Shadow(color: Colors.black54, blurRadius: 4)],
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            // Muscles + action
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child: Row(
                children: [
                  Expanded(
                    child: exercise.muscles.isNotEmpty
                        ? Wrap(
                            spacing: 5,
                            runSpacing: 4,
                            children: exercise.muscles.take(3).map((m) => Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: color.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: color.withValues(alpha: 0.25)),
                              ),
                              child: Text(
                                m.nameEn,
                                style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600),
                              ),
                            )).toList(),
                          )
                        : const Text('Không có thông tin nhóm cơ',
                            style: TextStyle(fontSize: 11, color: AppColors.textHint)),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton.icon(
                    onPressed: () => _addToJournal(exercise),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: color,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    ),
                    icon: const Icon(Icons.add, size: 14),
                    label: const Text('Thêm', style: TextStyle(fontSize: 12)),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _gradientBg(Color color) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [color, color.withValues(alpha: 0.6)],
        ),
      ),
      child: Center(
        child: Icon(Icons.fitness_center, size: 60, color: Colors.white.withValues(alpha: 0.25)),
      ),
    );
  }

  void _openDetail(WgerExercise exercise) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => ExerciseDetailScreen(exercise: exercise)),
    );
  }

  void _showCategoryPicker() {
    final categories = _local.categories;
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(height: 12),
          Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 16),
          const Text('Chọn danh mục', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          ListTile(
            leading: const Icon(Icons.all_inclusive),
            title: const Text('Tất cả'),
            selected: _selectedCategory == null,
            selectedColor: AppColors.primary,
            onTap: () {
              setState(() { _selectedCategory = null; _applyFilter(); });
              Navigator.pop(context);
            },
          ),
          ...categories.map((cat) => ListTile(
            leading: const Icon(Icons.fitness_center),
            title: Text(cat.name),
            trailing: Text(
              '${_local.getByCategory(cat.name).length}',
              style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
            ),
            selected: _selectedCategory == cat.name,
            selectedColor: AppColors.primary,
            onTap: () {
              setState(() { _selectedCategory = cat.name; _applyFilter(); });
              Navigator.pop(context);
            },
          )),
          const SizedBox(height: 16),
        ],
      ),
    );
  }

  void _showMusclePicker() {
    final muscles = _local.muscles.where((m) => m.nameEn.isNotEmpty).toList();
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.6,
        maxChildSize: 0.9,
        expand: false,
        builder: (_, sc) => Column(
          children: [
            const SizedBox(height: 12),
            Container(width: 40, height: 4, decoration: BoxDecoration(color: AppColors.textHint, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Text('Chọn nhóm cơ', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Expanded(
              child: ListView(
                controller: sc,
                children: [
                  ListTile(
                    leading: const Icon(Icons.all_inclusive),
                    title: const Text('Tất cả nhóm cơ'),
                    selected: _selectedMuscleId == null,
                    selectedColor: AppColors.primary,
                    onTap: () {
                      setState(() { _selectedMuscleId = null; _selectedMuscleLabel = null; _applyFilter(); });
                      Navigator.pop(context);
                    },
                  ),
                  ...muscles.map((m) => ListTile(
                    leading: Icon(m.isFront ? Icons.accessibility_new : Icons.accessibility, size: 20),
                    title: Text(m.nameEn),
                    subtitle: Text(m.isFront ? 'Mặt trước' : 'Mặt sau', style: const TextStyle(fontSize: 11)),
                    trailing: Text(
                      '${_local.getByMuscle(m.id).length}',
                      style: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
                    ),
                    selected: _selectedMuscleId == m.id,
                    selectedColor: AppColors.primary,
                    onTap: () {
                      setState(() {
                        _selectedMuscleId = m.id;
                        _selectedMuscleLabel = m.nameEn;
                        _applyFilter();
                      });
                      Navigator.pop(context);
                    },
                  )),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _addToJournal(WgerExercise exercise) async {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    final result = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(exercise.name, style: const TextStyle(fontSize: 16)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: durationController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Thời gian (phút)', suffixText: 'phút'),
              autofocus: true,
            ),
            const SizedBox(height: 10),
            const Text('Calo ước tính dựa trên cân nặng của bạn',
                style: TextStyle(fontSize: 11, color: AppColors.textSecondary)),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Hủy')),
          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Thêm')),
        ],
      ),
    );

    if (result == true && user != null && mounted) {
      final duration = int.tryParse(durationController.text) ?? 30;
      final calories = 5.0 * user.weight * (duration / 60.0);
      Provider.of<ExerciseProvider>(context, listen: false).addExercise(
        ExerciseModel(
          id: DateTime.now().millisecondsSinceEpoch.toString(),
          userId: user.id,
          name: exercise.name,
          date: DateTime.now(),
          duration: duration,
          caloriesBurned: calories,
          type: _mapCategory(exercise.categoryName),
          intensity: 'medium',
        ),
      );
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text('Đã thêm "${exercise.name}" vào nhật ký'),
        backgroundColor: AppColors.success,
        duration: const Duration(seconds: 2),
      ));
    }
  }

  String _mapCategory(String cat) {
    final c = cat.toLowerCase();
    if (c.contains('cardio')) {
      return 'cardio';
    }
    if (c.contains('arms') || c.contains('chest') || c.contains('back') ||
        c.contains('legs') || c.contains('shoulders') || c.contains('abs') ||
        c.contains('calves')) {
      return 'strength';
    }
    return 'sports';
  }
}
