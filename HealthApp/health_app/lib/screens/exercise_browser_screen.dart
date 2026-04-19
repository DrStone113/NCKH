import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/wger_service.dart';
import '../models/wger_models.dart';
import '../models/exercise_model.dart';
import '../providers/exercise_provider.dart';
import '../providers/user_provider.dart';
import '../theme/app_theme.dart';

class ExerciseBrowserScreen extends StatefulWidget {
  const ExerciseBrowserScreen({super.key});

  @override
  State<ExerciseBrowserScreen> createState() => _ExerciseBrowserScreenState();
}

class _ExerciseBrowserScreenState extends State<ExerciseBrowserScreen>
    with SingleTickerProviderStateMixin {
  final WgerService _wgerService = WgerService();
  final ScrollController _scrollController = ScrollController();
  late TabController _tabController;

  List<WgerExercise> _exercises = [];
  List<WgerExerciseCategory> _categories = [];
  List<WgerMuscle> _muscles = [];

  int _currentPage = 1;
  bool _isLoading = false;
  bool _hasMore = true;
  bool _hasError = false;
  String _errorMessage = '';
  bool _usingLocalFallback = false;

  int? _selectedCategoryId;
  int? _selectedMuscleId;

  // Local fallback search
  String _localSearchQuery = '';
  String _localFilterType = 'all';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _scrollController.addListener(_onScroll);
    _loadInitialData();
  }

  @override
  void dispose() {
    _tabController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >= _scrollController.position.maxScrollExtent - 200) {
      if (!_isLoading && _hasMore) {
        _loadMore();
      }
    }
  }

  Future<void> _loadInitialData() async {
    setState(() {
      _isLoading = true;
      _hasError = false;
      _usingLocalFallback = false;
    });

    try {
      // Load categories and muscles in parallel
      final results = await Future.wait([
        _wgerService.fetchExerciseCategories(),
        _wgerService.fetchMuscles(),
      ]);

      _categories = results[0] as List<WgerExerciseCategory>;
      _muscles = results[1] as List<WgerMuscle>;

      // Load first page of exercises
      await _loadMore();
    } catch (e) {
      // Fall back to local exercise database
      debugPrint('⚠️ wger API unavailable, using local fallback: $e');
      setState(() {
        _usingLocalFallback = true;
        _isLoading = false;
        _hasError = false;
      });
    }
  }

  Future<void> _loadMore() async {
    if (_isLoading || !_hasMore) return;

    setState(() {
      _isLoading = true;
      _hasError = false;
    });

    try {
      debugPrint('🔄 Loading exercises page $_currentPage...');
      final response = await _wgerService.fetchExercises(
        page: _currentPage,
        categoryId: _selectedCategoryId,
        muscleId: _selectedMuscleId,
      );

      debugPrint('✅ Loaded ${response.results.length} exercises (total: ${response.count})');
      debugPrint('   Has more: ${response.next != null}');
      
      if (response.results.isEmpty) {
        debugPrint('⚠️ No exercises returned from API');
      } else {
        debugPrint('   First exercise: ${response.results.first.name}');
      }

      setState(() {
        _exercises.addAll(response.results);
        _currentPage++;
        _hasMore = response.next != null;
        _isLoading = false;
        _usingLocalFallback = false;
      });
    } catch (e, stackTrace) {
      debugPrint('❌ Error loading exercises: $e');
      debugPrint('   Stack trace: $stackTrace');
      // If first load fails, switch to local fallback
      if (_exercises.isEmpty) {
        setState(() {
          _usingLocalFallback = true;
          _isLoading = false;
          _hasError = false;
        });
      } else {
        setState(() {
          _hasError = true;
          _errorMessage = e is WgerApiException ? e.message : 'Lỗi khi tải thêm dữ liệu';
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _applyFilter(int? categoryId, int? muscleId) async {
    setState(() {
      _selectedCategoryId = categoryId;
      _selectedMuscleId = muscleId;
      _exercises.clear();
      _currentPage = 1;
      _hasMore = true;
    });

    await _loadMore();
  }

  void _navigateToDetail(WgerExercise exercise) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppColors.surface,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.5,
        maxChildSize: 0.95,
        expand: false,
        builder: (context, scrollController) => _buildDetailSheet(exercise, scrollController),
      ),
    );
  }

  Widget _buildDetailSheet(WgerExercise exercise, ScrollController scrollController) {
    return SingleChildScrollView(
      controller: scrollController,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            children: [
              Expanded(
                child: Text(
                  exercise.name,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          const SizedBox(height: 8),
          
          // Category
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: AppColors.primary.withOpacity(0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              exercise.categoryName,
              style: const TextStyle(color: AppColors.primary, fontSize: 12),
            ),
          ),
          const SizedBox(height: 16),

          // Image
          if (exercise.imageUrl != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.network(
                exercise.imageUrl!,
                height: 200,
                width: double.infinity,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stackTrace) => Container(
                  height: 200,
                  color: AppColors.cardDark,
                  child: const Icon(Icons.fitness_center, size: 64, color: AppColors.textHint),
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],

          // Primary Muscles
          if (exercise.muscles.isNotEmpty) ...[
            const Text(
              'Nhóm cơ chính',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: exercise.muscles.map((muscle) => Chip(
                label: Text(muscle.nameEn),
                backgroundColor: AppColors.success.withOpacity(0.15),
                labelStyle: const TextStyle(color: AppColors.success, fontSize: 12),
              )).toList(),
            ),
            const SizedBox(height: 16),
          ],

          // Secondary Muscles
          if (exercise.musclesSecondary.isNotEmpty) ...[
            const Text(
              'Nhóm cơ phụ',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: exercise.musclesSecondary.map((muscle) => Chip(
                label: Text(muscle.nameEn),
                backgroundColor: AppColors.textSecondary.withOpacity(0.15),
                labelStyle: const TextStyle(color: AppColors.textSecondary, fontSize: 12),
              )).toList(),
            ),
            const SizedBox(height: 16),
          ],

          // Equipment
          if (exercise.equipment.isNotEmpty) ...[
            const Text(
              'Thiết bị cần thiết',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: exercise.equipment.map((equip) => Chip(
                label: Text(equip.name),
                backgroundColor: AppColors.primary.withOpacity(0.15),
                labelStyle: const TextStyle(color: AppColors.primary, fontSize: 12),
              )).toList(),
            ),
            const SizedBox(height: 16),
          ],

          // Description
          if (exercise.description.isNotEmpty) ...[
            const Text(
              'Hướng dẫn',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              exercise.description.replaceAll(RegExp(r'<[^>]*>'), ''), // Remove HTML tags
              style: const TextStyle(color: AppColors.textSecondary, height: 1.5),
            ),
            const SizedBox(height: 16),
          ],

          // Add to Journal Button
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              onPressed: () {
                Navigator.pop(context);
                _addToJournal(exercise);
              },
              icon: const Icon(Icons.add),
              label: const Text('Thêm vào nhật ký'),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _addToJournal(WgerExercise exercise) async {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(exercise.name),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: durationController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Thời gian (phút)',
                suffixText: 'phút',
              ),
              autofocus: true,
            ),
            const SizedBox(height: 12),
            const Text(
              'Ước tính calo sẽ được tính dựa trên cân nặng của bạn',
              style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Thêm'),
          ),
        ],
      ),
    );

    if (result == true && user != null) {
      final duration = int.tryParse(durationController.text) ?? 30;
      
      // Estimate calories based on exercise type and duration
      // Using a simple estimation: moderate intensity = 5 MET
      final estimatedCalories = 5.0 * user.weight * (duration / 60.0);
      
      final exerciseModel = ExerciseModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: user.id,
        name: exercise.name,
        date: DateTime.now(),
        duration: duration,
        caloriesBurned: estimatedCalories,
        type: _mapCategoryToType(exercise.categoryName),
        intensity: 'medium',
      );

      if (mounted) {
        Provider.of<ExerciseProvider>(context, listen: false).addExercise(exerciseModel);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã thêm "${exercise.name}" vào nhật ký'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  String _mapCategoryToType(String categoryName) {
    final lower = categoryName.toLowerCase();
    if (lower.contains('cardio') || lower.contains('endurance')) {
      return 'cardio';
    } else if (lower.contains('strength') || lower.contains('arms') || lower.contains('legs')) {
      return 'strength';
    } else if (lower.contains('stretch') || lower.contains('flexibility')) {
      return 'flexibility';
    } else {
      return 'sports';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Khám phá bài tập'),
        actions: [
          if (!_usingLocalFallback)
            IconButton(
              icon: const Icon(Icons.filter_list),
              onPressed: _showFilterDialog,
            ),
        ],
        bottom: _usingLocalFallback
            ? PreferredSize(
                preferredSize: const Size.fromHeight(48),
                child: Container(
                  color: AppColors.background,
                  child: TabBar(
                    controller: _tabController,
                    tabs: const [
                      Tab(text: 'Tất cả'),
                      Tab(text: 'Theo loại'),
                    ],
                  ),
                ),
              )
            : null,
      ),
      body: _usingLocalFallback ? _buildLocalFallbackBody() : _buildBody(),
    );
  }

  /// Build local fallback UI using ExerciseProvider's built-in database
  Widget _buildLocalFallbackBody() {
    return Column(
      children: [
        // Offline banner
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          color: AppColors.warning.withOpacity(0.1),
          child: Row(
            children: [
              const Icon(Icons.wifi_off, size: 16, color: AppColors.warning),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Không kết nối được wger API — đang dùng dữ liệu nội bộ',
                  style: TextStyle(fontSize: 12, color: AppColors.warning),
                ),
              ),
              TextButton(
                onPressed: () {
                  setState(() {
                    _exercises.clear();
                    _currentPage = 1;
                    _hasMore = true;
                  });
                  _loadInitialData();
                },
                style: TextButton.styleFrom(
                  foregroundColor: AppColors.warning,
                  padding: const EdgeInsets.symmetric(horizontal: 8),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: const Text('Thử lại', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        ),
        // Search bar
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
          child: TextField(
            decoration: const InputDecoration(
              hintText: 'Tìm bài tập...',
              prefixIcon: Icon(Icons.search, size: 20),
              contentPadding: EdgeInsets.symmetric(vertical: 10),
            ),
            onChanged: (val) => setState(() => _localSearchQuery = val),
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: TabBarView(
            controller: _tabController,
            children: [
              _buildLocalExerciseList(null),
              _buildLocalByTypeList(),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLocalExerciseList(String? typeFilter) {
    final allExercises = ExerciseProvider.exerciseDatabase;
    final filtered = allExercises.where((e) {
      final matchesType = typeFilter == null || e.type == typeFilter;
      final matchesSearch = _localSearchQuery.isEmpty ||
          e.name.toLowerCase().contains(_localSearchQuery.toLowerCase()) ||
          e.description.toLowerCase().contains(_localSearchQuery.toLowerCase());
      return matchesType && matchesSearch;
    }).toList();

    if (filtered.isEmpty) {
      return const Center(
        child: Text('Không tìm thấy bài tập', style: TextStyle(color: AppColors.textSecondary)),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: filtered.length,
      itemBuilder: (context, index) => _buildLocalExerciseCard(filtered[index]),
    );
  }

  Widget _buildLocalByTypeList() {
    final types = [
      {'type': 'cardio', 'label': 'Cardio', 'icon': Icons.directions_run, 'color': AppColors.cardio},
      {'type': 'strength', 'label': 'Sức mạnh', 'icon': Icons.fitness_center, 'color': AppColors.strength},
      {'type': 'flexibility', 'label': 'Linh hoạt', 'icon': Icons.self_improvement, 'color': AppColors.flexibility},
      {'type': 'sports', 'label': 'Thể thao', 'icon': Icons.sports_soccer, 'color': AppColors.sports},
    ];

    return ListView(
      padding: const EdgeInsets.all(16),
      children: types.map((t) {
        final exercises = ExerciseProvider.exerciseDatabase
            .where((e) => e.type == t['type'] as String)
            .where((e) => _localSearchQuery.isEmpty ||
                e.name.toLowerCase().contains(_localSearchQuery.toLowerCase()))
            .toList();

        if (exercises.isEmpty) return const SizedBox.shrink();

        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(bottom: 10, top: 4),
              child: Row(
                children: [
                  Container(
                    width: 32,
                    height: 32,
                    decoration: BoxDecoration(
                      color: (t['color'] as Color).withOpacity(0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(t['icon'] as IconData, size: 18, color: t['color'] as Color),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    t['label'] as String,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '${exercises.length} bài',
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
            ...exercises.map((e) => _buildLocalExerciseCard(e)),
            const SizedBox(height: 8),
          ],
        );
      }).toList(),
    );
  }

  Widget _buildLocalExerciseCard(ExerciseTemplate exercise) {
    final typeColors = {
      'cardio': AppColors.cardio,
      'strength': AppColors.strength,
      'flexibility': AppColors.flexibility,
      'sports': AppColors.sports,
    };
    final typeLabels = {
      'cardio': 'Cardio',
      'strength': 'Sức mạnh',
      'flexibility': 'Linh hoạt',
      'sports': 'Thể thao',
    };
    final color = typeColors[exercise.type] ?? AppColors.primary;

    return GestureDetector(
      onTap: () => _addLocalExerciseToJournal(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: AppColors.surfaceLight),
        ),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Center(
                child: Text(
                  '${exercise.metValue.toStringAsFixed(1)}',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: color),
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    exercise.name,
                    style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    exercise.description,
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: color.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    typeLabels[exercise.type] ?? exercise.type,
                    style: TextStyle(fontSize: 10, color: color, fontWeight: FontWeight.w600),
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

  Future<void> _addLocalExerciseToJournal(ExerciseTemplate exercise) async {
    final durationController = TextEditingController(text: '30');
    final user = Provider.of<UserProvider>(context, listen: false).currentUser;

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: Text(exercise.name),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: durationController,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(
                labelText: 'Thời gian (phút)',
                suffixText: 'phút',
              ),
              autofocus: true,
            ),
            const SizedBox(height: 12),
            Text(
              exercise.description,
              style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Hủy'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Thêm'),
          ),
        ],
      ),
    );

    if (result == true && user != null) {
      final duration = int.tryParse(durationController.text) ?? 30;
      final caloriesBurned = exercise.metValue * user.weight * (duration / 60.0);

      final exerciseModel = ExerciseModel(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        userId: user.id,
        name: exercise.name,
        exerciseTemplateId: exercise.id,
        date: DateTime.now(),
        duration: duration,
        caloriesBurned: caloriesBurned,
        type: exercise.type,
        intensity: exercise.metValue >= 7 ? 'high' : exercise.metValue >= 5 ? 'medium' : 'low',
      );

      if (mounted) {
        Provider.of<ExerciseProvider>(context, listen: false).addExercise(exerciseModel);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Đã thêm "${exercise.name}" vào nhật ký (${caloriesBurned.toStringAsFixed(0)} kcal)'),
            backgroundColor: AppColors.success,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  Widget _buildBody() {
    // Error state
    if (_hasError && _exercises.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, size: 64, color: AppColors.error),
              const SizedBox(height: 16),
              Text(
                _errorMessage,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _loadInitialData,
                icon: const Icon(Icons.refresh),
                label: const Text('Thử lại'),
              ),
              const SizedBox(height: 12),
              TextButton.icon(
                onPressed: () => setState(() => _usingLocalFallback = true),
                icon: const Icon(Icons.storage_outlined),
                label: const Text('Dùng dữ liệu nội bộ'),
              ),
            ],
          ),
        ),
      );
    }

    // Loading skeleton
    if (_isLoading && _exercises.isEmpty) {
      return ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: 6,
        itemBuilder: (context, index) => _buildSkeletonCard(),
      );
    }

    // Empty state
    if (_exercises.isEmpty && !_isLoading) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.fitness_center, size: 64, color: AppColors.textHint),
              const SizedBox(height: 16),
              const Text(
                'Không tìm thấy bài tập',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              const Text(
                'Thử thay đổi bộ lọc hoặc kéo xuống để làm mới',
                textAlign: TextAlign.center,
                style: TextStyle(color: AppColors.textSecondary),
              ),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _loadInitialData,
                icon: const Icon(Icons.refresh),
                label: const Text('Làm mới'),
              ),
            ],
          ),
        ),
      );
    }

    // Exercise list
    return RefreshIndicator(
      onRefresh: () async {
        setState(() {
          _exercises.clear();
          _currentPage = 1;
          _hasMore = true;
        });
        await _loadMore();
      },
      child: ListView.builder(
        controller: _scrollController,
        padding: const EdgeInsets.all(16),
        itemCount: _exercises.length + (_hasMore ? 1 : 0),
        itemBuilder: (context, index) {
          if (index == _exercises.length) {
            return _buildLoadingIndicator();
          }
          return _buildExerciseCard(_exercises[index]);
        },
      ),
    );
  }

  Widget _buildSkeletonCard() {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: AppColors.surface,
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: double.infinity,
                  height: 16,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  width: 120,
                  height: 12,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  width: 80,
                  height: 12,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingIndicator() {
    return const Padding(
      padding: EdgeInsets.all(16),
      child: Center(
        child: CircularProgressIndicator(),
      ),
    );
  }

  Widget _buildExerciseCard(WgerExercise exercise) {
    return GestureDetector(
      onTap: () => _navigateToDetail(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: AppColors.cardDark,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Row(
          children: [
            // Image
            ClipRRect(
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(14),
                bottomLeft: Radius.circular(14),
              ),
              child: exercise.imageUrl != null
                  ? Image.network(
                      exercise.imageUrl!,
                      width: 80,
                      height: 80,
                      fit: BoxFit.cover,
                      errorBuilder: (context, error, stackTrace) => Container(
                        width: 80,
                        height: 80,
                        color: AppColors.surface,
                        child: const Icon(Icons.fitness_center, color: AppColors.textHint),
                      ),
                    )
                  : Container(
                      width: 80,
                      height: 80,
                      color: AppColors.surface,
                      child: const Icon(Icons.fitness_center, color: AppColors.textHint),
                    ),
            ),
            const SizedBox(width: 12),
            
            // Content
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      exercise.name,
                      style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      exercise.categoryName,
                      style: const TextStyle(fontSize: 12, color: AppColors.primary),
                    ),
                    if (exercise.muscles.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        exercise.muscles.map((m) => m.nameEn).take(2).join(', '),
                        style: const TextStyle(fontSize: 11, color: AppColors.textSecondary),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
            ),
            
            // Arrow
            const Padding(
              padding: EdgeInsets.only(right: 12),
              child: Icon(Icons.chevron_right, color: AppColors.textHint),
            ),
          ],
        ),
      ),
    );
  }

  void _showFilterDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppColors.surface,
        title: const Text('Lọc bài tập'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Danh mục', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              DropdownButtonFormField<int?>(
                value: _selectedCategoryId,
                decoration: const InputDecoration(
                  hintText: 'Tất cả danh mục',
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
                dropdownColor: AppColors.surface,
                items: [
                  const DropdownMenuItem<int?>(
                    value: null,
                    child: Text('Tất cả danh mục'),
                  ),
                  ..._categories.map((cat) => DropdownMenuItem<int?>(
                    value: cat.id,
                    child: Text(cat.name),
                  )),
                ],
                onChanged: (value) {
                  setState(() {
                    _selectedCategoryId = value;
                  });
                },
              ),
              const SizedBox(height: 16),
              const Text('Nhóm cơ', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              DropdownButtonFormField<int?>(
                value: _selectedMuscleId,
                decoration: const InputDecoration(
                  hintText: 'Tất cả nhóm cơ',
                  contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                ),
                dropdownColor: AppColors.surface,
                items: [
                  const DropdownMenuItem<int?>(
                    value: null,
                    child: Text('Tất cả nhóm cơ'),
                  ),
                  ..._muscles.map((muscle) => DropdownMenuItem<int?>(
                    value: muscle.id,
                    child: Text(muscle.nameEn),
                  )),
                ],
                onChanged: (value) {
                  setState(() {
                    _selectedMuscleId = value;
                  });
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              setState(() {
                _selectedCategoryId = null;
                _selectedMuscleId = null;
              });
              Navigator.pop(context);
              _applyFilter(null, null);
            },
            child: const Text('Xóa bộ lọc'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _applyFilter(_selectedCategoryId, _selectedMuscleId);
            },
            child: const Text('Áp dụng'),
          ),
        ],
      ),
    );
  }
}
