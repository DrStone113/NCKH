import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/wger_service.dart';
import '../services/wger_cache_service.dart';
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
  final WgerCacheService _cacheService = WgerCacheService();
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
    // Check if cache is available
    if (_cacheService.hasCachedData) {
      debugPrint('📦 Using cached wger data');
      setState(() {
        _exercises = _cacheService.cachedExercises;
        _categories = _cacheService.cachedCategories;
        _muscles = _cacheService.cachedMuscles;
        _currentPage = 4; // Cache có 3 pages rồi, page tiếp theo là 4
        _hasMore = true;
        _isLoading = false;
        _usingLocalFallback = false;
      });
      return;
    }

    // If cache is being fetched, wait a bit
    if (_cacheService.isFetching) {
      debugPrint('⏳ Waiting for cache to be ready...');
      setState(() => _isLoading = true);
      
      // Wait up to 5 seconds for cache
      for (int i = 0; i < 10; i++) {
        await Future.delayed(const Duration(milliseconds: 500));
        if (_cacheService.hasCachedData) {
          debugPrint('✅ Cache ready!');
          setState(() {
            _exercises = _cacheService.cachedExercises;
            _categories = _cacheService.cachedCategories;
            _muscles = _cacheService.cachedMuscles;
            _currentPage = 4;
            _hasMore = true;
            _isLoading = false;
            _usingLocalFallback = false;
          });
          return;
        }
      }
    }

    // If no cache available, fetch fresh data
    setState(() {
      _isLoading = true;
      _hasError = false;
      _usingLocalFallback = false;
      _exercises.clear();
      _currentPage = 1;
      _hasMore = true;
    });

    try {
      // Try to get from cache service (will fetch if needed)
      final results = await Future.wait([
        Future.value(_cacheService.cachedCategories.isNotEmpty 
            ? _cacheService.cachedCategories 
            : <WgerExerciseCategory>[]),
        Future.value(_cacheService.cachedMuscles.isNotEmpty 
            ? _cacheService.cachedMuscles 
            : <WgerMuscle>[]),
        _cacheService.getExercises(),
      ]);

      if (mounted) {
        setState(() {
          _categories = results[0] as List<WgerExerciseCategory>;
          _muscles = results[1] as List<WgerMuscle>;
          _exercises = results[2] as List<WgerExercise>;
          _currentPage = 4; // Assuming cache has 3 pages
          _hasMore = true;
          _isLoading = false;
        });
      }
    } catch (e) {
      // Fall back to local exercise database
      debugPrint('⚠️ wger API unavailable, using local fallback: $e');
      if (mounted) {
        setState(() {
          _usingLocalFallback = true;
          _isLoading = false;
          _hasError = false;
        });
      }
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
      final response = await _cacheService.loadMoreExercises(
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
        // hasMore dựa vào count thực tế thay vì next URL (next trỏ wger.de gây CORS)
        _hasMore = _exercises.length < response.count && response.results.isNotEmpty;
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
      _isLoading = true;
    });

    try {
      // Try to get filtered data from cache first
      final filtered = await _cacheService.getExercises(
        categoryId: categoryId,
        muscleId: muscleId,
      );

      if (mounted) {
        setState(() {
          _exercises = filtered;
          _currentPage = 2; // Start from page 2 for pagination
          _hasMore = true;
          _isLoading = false;
        });
      }
    } catch (e) {
      debugPrint('❌ Error applying filter: $e');
      if (mounted) {
        setState(() {
          _isLoading = false;
          _hasError = true;
          _errorMessage = 'Lỗi khi lọc bài tập';
        });
      }
    }
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
    return Container(
      decoration: const BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          // Drag Handle
          Container(
            margin: const EdgeInsets.only(top: 12, bottom: 8),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.textHint.withOpacity(0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          
          Expanded(
            child: SingleChildScrollView(
              controller: scrollController,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Hero Image Section
                  Stack(
                    children: [
                      // Image
                      if (exercise.imageUrl != null)
                        Image.network(
                          exercise.imageUrl!,
                          height: 250,
                          width: double.infinity,
                          fit: BoxFit.cover,
                          errorBuilder: (context, error, stackTrace) => _buildFallbackHeroImage(exercise),
                        )
                      else
                        _buildFallbackHeroImage(exercise),
                      
                      // Gradient Overlay
                      Positioned.fill(
                        child: Container(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topCenter,
                              end: Alignment.bottomCenter,
                              colors: [
                                Colors.transparent,
                                AppColors.background.withOpacity(0.8),
                              ],
                            ),
                          ),
                        ),
                      ),
                      
                      // Close Button
                      Positioned(
                        top: 12,
                        right: 12,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.black.withOpacity(0.5),
                            shape: BoxShape.circle,
                          ),
                          child: IconButton(
                            icon: const Icon(Icons.close, color: Colors.white),
                            onPressed: () => Navigator.pop(context),
                          ),
                        ),
                      ),
                      
                      // Title Overlay
                      Positioned(
                        left: 20,
                        right: 20,
                        bottom: 20,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                              decoration: BoxDecoration(
                                color: AppColors.primary,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                exercise.categoryName.toUpperCase(),
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  letterSpacing: 0.5,
                                ),
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              exercise.name,
                              style: const TextStyle(
                                fontSize: 26,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                                shadows: [
                                  Shadow(
                                    color: Colors.black54,
                                    offset: Offset(0, 2),
                                    blurRadius: 4,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  
                  // Content Section
                  Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Quick Stats Row
                        Row(
                          children: [
                            if (exercise.muscles.isNotEmpty)
                              Expanded(
                                child: _buildStatCard(
                                  icon: Icons.fitness_center,
                                  label: 'Nhóm cơ',
                                  value: '${exercise.muscles.length}',
                                  color: AppColors.success,
                                ),
                              ),
                            const SizedBox(width: 12),
                            if (exercise.equipment.isNotEmpty)
                              Expanded(
                                child: _buildStatCard(
                                  icon: Icons.build_circle,
                                  label: 'Thiết bị',
                                  value: '${exercise.equipment.length}',
                                  color: AppColors.primary,
                                ),
                              ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _buildStatCard(
                                icon: Icons.local_fire_department,
                                label: 'Cường độ',
                                value: 'Trung bình',
                                color: AppColors.warning,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 24),

                        // Primary Muscles Section
                        if (exercise.muscles.isNotEmpty) ...[
                          _buildSectionHeader(
                            icon: Icons.fitness_center,
                            title: 'Nhóm cơ chính',
                            color: AppColors.success,
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: exercise.muscles.map((muscle) => _buildMuscleChip(
                              muscle.nameEn,
                              AppColors.success,
                              isPrimary: true,
                            )).toList(),
                          ),
                          const SizedBox(height: 20),
                        ],

                        // Secondary Muscles Section
                        if (exercise.musclesSecondary.isNotEmpty) ...[
                          _buildSectionHeader(
                            icon: Icons.fitness_center_outlined,
                            title: 'Nhóm cơ phụ',
                            color: AppColors.textSecondary,
                          ),
                          const SizedBox(height: 12),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: exercise.musclesSecondary.map((muscle) => _buildMuscleChip(
                              muscle.nameEn,
                              AppColors.textSecondary,
                              isPrimary: false,
                            )).toList(),
                          ),
                          const SizedBox(height: 20),
                        ],

                        // Equipment Section
                        if (exercise.equipment.isNotEmpty) ...[
                          _buildSectionHeader(
                            icon: Icons.build_circle,
                            title: 'Thiết bị cần thiết',
                            color: AppColors.primary,
                          ),
                          const SizedBox(height: 12),
                          ...exercise.equipment.map((equip) => Container(
                            margin: const EdgeInsets.only(bottom: 8),
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppColors.cardDark,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.primary.withOpacity(0.3)),
                            ),
                            child: Row(
                              children: [
                                Container(
                                  padding: const EdgeInsets.all(8),
                                  decoration: BoxDecoration(
                                    color: AppColors.primary.withOpacity(0.15),
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: const Icon(
                                    Icons.build_circle,
                                    size: 20,
                                    color: AppColors.primary,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Text(
                                  equip.name,
                                  style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),
                          )),
                          const SizedBox(height: 20),
                        ],

                        // Description Section
                        if (exercise.description.isNotEmpty) ...[
                          _buildSectionHeader(
                            icon: Icons.description,
                            title: 'Hướng dẫn thực hiện',
                            color: AppColors.info,
                          ),
                          const SizedBox(height: 12),
                          Container(
                            padding: const EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: AppColors.cardDark,
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(color: AppColors.surfaceLight),
                            ),
                            child: Text(
                              exercise.description.replaceAll(RegExp(r'<[^>]*>'), ''),
                              style: const TextStyle(
                                color: AppColors.textPrimary,
                                height: 1.6,
                                fontSize: 14,
                              ),
                            ),
                          ),
                          const SizedBox(height: 24),
                        ],

                        // Add to Journal Button
                        SizedBox(
                          width: double.infinity,
                          height: 54,
                          child: ElevatedButton(
                            onPressed: () {
                              Navigator.pop(context);
                              _addToJournal(exercise);
                            },
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppColors.primary,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                              elevation: 0,
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: const [
                                Icon(Icons.add_circle, size: 22),
                                SizedBox(width: 8),
                                Text(
                                  'Thêm vào nhật ký',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFallbackHeroImage(WgerExercise exercise) {
    final gradients = {
      'Arms': [const Color(0xFF667eea), const Color(0xFF764ba2)],
      'Legs': [const Color(0xFFf093fb), const Color(0xFFf5576c)],
      'Abs': [const Color(0xFF4facfe), const Color(0xFF00f2fe)],
      'Chest': [const Color(0xFFfa709a), const Color(0xFFfee140)],
      'Back': [const Color(0xFF30cfd0), const Color(0xFF330867)],
      'Shoulders': [const Color(0xFFa8edea), const Color(0xFFfed6e3)],
      'Cardio': [const Color(0xFFff9a56), const Color(0xFFff6a88)],
    };
    
    final colors = gradients.entries
        .firstWhere(
          (entry) => exercise.categoryName.contains(entry.key),
          orElse: () => MapEntry('default', [AppColors.primary, AppColors.primary.withOpacity(0.6)]),
        )
        .value;
    
    return Container(
      height: 250,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors,
        ),
      ),
      child: Center(
        child: Icon(
          Icons.fitness_center,
          size: 80,
          color: Colors.white.withOpacity(0.3),
        ),
      ),
    );
  }

  Widget _buildStatCard({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 24),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              color: color.withOpacity(0.8),
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader({
    required IconData icon,
    required String title,
    required Color color,
  }) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withOpacity(0.15),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(icon, size: 18, color: color),
        ),
        const SizedBox(width: 10),
        Text(
          title,
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _buildMuscleChip(String name, Color color, {required bool isPrimary}) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(isPrimary ? 0.15 : 0.08),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: color.withOpacity(isPrimary ? 0.4 : 0.2),
          width: isPrimary ? 1.5 : 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            isPrimary ? Icons.circle : Icons.circle_outlined,
            size: 8,
            color: color,
          ),
          const SizedBox(width: 6),
          Text(
            name,
            style: TextStyle(
              color: color,
              fontSize: 13,
              fontWeight: isPrimary ? FontWeight.w600 : FontWeight.w500,
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
          // Cache status indicator
          if (_cacheService.hasCachedData && !_usingLocalFallback)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppColors.success.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: const [
                      Icon(Icons.offline_bolt, size: 14, color: AppColors.success),
                      SizedBox(width: 4),
                      Text(
                        'Cached',
                        style: TextStyle(fontSize: 11, color: AppColors.success),
                      ),
                    ],
                  ),
                ),
              ),
            ),
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
    final typeIcons = {
      'cardio': Icons.directions_run,
      'strength': Icons.fitness_center,
      'flexibility': Icons.self_improvement,
      'sports': Icons.sports_soccer,
    };
    final color = typeColors[exercise.type] ?? AppColors.primary;
    final icon = typeIcons[exercise.type] ?? Icons.fitness_center;

    return GestureDetector(
      onTap: () => _addLocalExerciseToJournal(exercise),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppColors.cardDark,
              color.withOpacity(0.05),
            ],
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withOpacity(0.3), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: color.withOpacity(0.1),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              // Icon with MET value
              Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [color, color.withOpacity(0.7)],
                  ),
                  borderRadius: BorderRadius.circular(14),
                  boxShadow: [
                    BoxShadow(
                      color: color.withOpacity(0.3),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(icon, color: Colors.white, size: 24),
                    const SizedBox(height: 2),
                    Text(
                      '${exercise.metValue.toStringAsFixed(1)}',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 14),
              
              // Content
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      exercise.name,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      exercise.description,
                      style: const TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                        height: 1.3,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              
              // Type badge and add button
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: color.withOpacity(0.3)),
                    ),
                    child: Text(
                      typeLabels[exercise.type] ?? exercise.type,
                      style: TextStyle(
                        fontSize: 10,
                        color: color,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.15),
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.add_circle,
                      size: 20,
                      color: color,
                    ),
                  ),
                ],
              ),
            ],
          ),
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
        // Refresh cache
        await _cacheService.refreshCache();
        // Reload data
        setState(() {
          _exercises.clear();
          _currentPage = 1;
          _hasMore = true;
          _selectedCategoryId = null;
          _selectedMuscleId = null;
        });
        await _loadInitialData();
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
      margin: const EdgeInsets.only(bottom: 16),
      height: 180,
      decoration: BoxDecoration(
        color: AppColors.cardDark,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Stack(
        children: [
          // Shimmer effect
          Positioned.fill(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(20),
              child: Container(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: [
                      AppColors.surface,
                      AppColors.surfaceLight,
                      AppColors.surface,
                    ],
                  ),
                ),
              ),
            ),
          ),
          Positioned(
            left: 16,
            right: 16,
            bottom: 16,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 80,
                  height: 20,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  width: double.infinity,
                  height: 24,
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const SizedBox(height: 6),
                Container(
                  width: 150,
                  height: 16,
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
        margin: const EdgeInsets.only(bottom: 16),
        height: 180,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.15),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: Stack(
            children: [
              // Background Image with Gradient Overlay
              Positioned.fill(
                child: exercise.imageUrl != null
                    ? Image.network(
                        exercise.imageUrl!,
                        fit: BoxFit.cover,
                        errorBuilder: (context, error, stackTrace) => _buildFallbackBackground(exercise),
                      )
                    : _buildFallbackBackground(exercise),
              ),
              
              // Gradient Overlay
              Positioned.fill(
                child: Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        Colors.transparent,
                        Colors.black.withOpacity(0.5),
                        Colors.black.withOpacity(0.85),
                      ],
                      stops: const [0.0, 0.5, 1.0],
                    ),
                  ),
                ),
              ),
              
              // Content
              Positioned(
                left: 16,
                right: 16,
                bottom: 16,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Category Badge
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: AppColors.primary.withOpacity(0.9),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        exercise.categoryName.toUpperCase(),
                        style: const TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          letterSpacing: 0.5,
                        ),
                      ),
                    ),
                    const SizedBox(height: 8),
                    
                    // Exercise Name
                    Text(
                      exercise.name,
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 18,
                        color: Colors.white,
                        shadows: [
                          Shadow(
                            color: Colors.black45,
                            offset: Offset(0, 1),
                            blurRadius: 3,
                          ),
                        ],
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                    const SizedBox(height: 6),
                    
                    // Muscles Row
                    if (exercise.muscles.isNotEmpty)
                      Row(
                        children: [
                          const Icon(
                            Icons.fitness_center,
                            size: 14,
                            color: Colors.white70,
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: Text(
                              exercise.muscles.map((m) => m.nameEn).take(3).join(' • '),
                              style: const TextStyle(
                                fontSize: 12,
                                color: Colors.white70,
                                fontWeight: FontWeight.w500,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                          const Icon(
                            Icons.arrow_forward_ios,
                            size: 14,
                            color: Colors.white70,
                          ),
                        ],
                      ),
                  ],
                ),
              ),
              
              // Equipment Badge (top right)
              if (exercise.equipment.isNotEmpty)
                Positioned(
                  top: 12,
                  right: 12,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.black.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: Colors.white24),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.build_circle, size: 12, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(
                          exercise.equipment.first.name,
                          style: const TextStyle(
                            fontSize: 10,
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFallbackBackground(WgerExercise exercise) {
    // Generate gradient based on category
    final gradients = {
      'Arms': [const Color(0xFF667eea), const Color(0xFF764ba2)],
      'Legs': [const Color(0xFFf093fb), const Color(0xFFf5576c)],
      'Abs': [const Color(0xFF4facfe), const Color(0xFF00f2fe)],
      'Chest': [const Color(0xFFfa709a), const Color(0xFFfee140)],
      'Back': [const Color(0xFF30cfd0), const Color(0xFF330867)],
      'Shoulders': [const Color(0xFFa8edea), const Color(0xFFfed6e3)],
      'Cardio': [const Color(0xFFff9a56), const Color(0xFFff6a88)],
    };
    
    final colors = gradients.entries
        .firstWhere(
          (entry) => exercise.categoryName.contains(entry.key),
          orElse: () => MapEntry('default', [AppColors.primary, AppColors.primary.withOpacity(0.6)]),
        )
        .value;
    
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors,
        ),
      ),
      child: Center(
        child: Icon(
          Icons.fitness_center,
          size: 64,
          color: Colors.white.withOpacity(0.3),
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
