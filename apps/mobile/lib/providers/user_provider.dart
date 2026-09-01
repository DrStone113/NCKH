import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/user_model.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../constants/firestore_collections.dart';
import '../models/app_state_value.dart';

class UserProvider with ChangeNotifier {
  static const _notSet = Object();
  UserModel? _currentUser;
  bool _isInitialized = false;
  DataStatus _profileStatus = DataStatus.notLoaded;
  DateTime? _profileReadAt;

  UserModel? get currentUser => _currentUser;
  bool get isAuthenticated => _currentUser != null;
  bool get isInitialized => _isInitialized;
  DataStatus get profileStatus => _profileStatus;
  DateTime? get profileReadAt => _profileReadAt;
  bool get needsWorkoutAccountIntake =>
      _currentUser?.needsWorkoutAccountIntake ?? false;
  bool get needsAccountHealthIntake =>
      _currentUser?.needsAccountHealthIntake ?? false;

  UserProvider() {
    _restoreSession();
  }

  /// Tự động restore session từ Firebase Auth khi app khởi động
  Future<void> _restoreSession() async {
    try {
      final firebaseUser = FirebaseAuth.instance.currentUser;
      if (firebaseUser != null) {
        debugPrint('🔄 Restoring session for: ${firebaseUser.email}');
        final doc = await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(firebaseUser.uid)
            .get();
        if (doc.exists) {
          _currentUser = UserModel.fromMap(doc.data() as Map<String, dynamic>);
          _profileStatus = DataStatus.known;
          _profileReadAt = DateTime.now();
          debugPrint('✅ Session restored: ${_currentUser!.name}');
        }
      }
    } catch (e) {
      _profileStatus = DataStatus.error;
      debugPrint('⚠️ Session restore failed: $e');
    } finally {
      _isInitialized = true;
      notifyListeners();
    }
  }

  /// Demo mode - set fake user for UI testing without Firebase
  void setDemoUser() {
    _currentUser = UserModel(
      id: 'demo',
      email: 'demo@health.app',
      name: 'Nguyễn Văn A',
      age: 25,
      height: 170,
      weight: 68,
      targetWeight: 65,
      activityLevel: 'moderate',
      healthGoal: 'maintain',
      createdAt: DateTime.now(),
    );
    _profileStatus = DataStatus.notLoaded;
    _profileReadAt = null;
    notifyListeners();
  }

  Future<void> signUp(String email, String password, UserModel userData) async {
    try {
      final auth = FirebaseAuth.instance;
      final firestore = FirebaseFirestore.instance;

      UserCredential credential = await auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );

      final user = UserModel(
        id: credential.user!.uid,
        email: userData.email,
        name: userData.name,
        age: userData.age,
        gender: userData.gender,
        equationSex: userData.equationSex,
        nutritionSafetyProfile: userData.nutritionSafetyProfile,
        height: userData.height,
        weight: userData.weight,
        targetWeight: userData.targetWeight,
        activityLevel: userData.activityLevel,
        healthGoal: userData.healthGoal,
        nutritionProfile: userData.nutritionProfile,
        workoutProfile: userData.workoutProfile,
        healthProfile: userData.healthProfile,
        createdAt: DateTime.now(),
      );

      await firestore
          .collection(FirestoreCollections.users)
          .doc(user.id)
          .set(user.toMap());
      _currentUser = user;
      _profileStatus = DataStatus.known;
      _profileReadAt = DateTime.now();
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  Future<void> signIn(String email, String password) async {
    try {
      final auth = FirebaseAuth.instance;
      UserCredential credential = await auth.signInWithEmailAndPassword(
        email: email.trim(),
        password: password.trim(),
      );

      if (credential.user != null) {
        await _syncFirebaseUser(credential.user!);
      }
    } catch (e) {
      rethrow;
    }
  }

  final GoogleSignIn _googleSignIn = GoogleSignIn();

  Future<void> signInWithGoogle() async {
    try {
      if (kIsWeb) {
        final googleProvider = GoogleAuthProvider();
        googleProvider.addScope('email');
        googleProvider.addScope('profile');

        final UserCredential userCredential =
            await FirebaseAuth.instance.signInWithPopup(googleProvider);
        if (userCredential.user != null) {
          await _syncFirebaseUser(userCredential.user!);
        }
      } else {
        // Native Android / iOS Firebase Google Sign In
        final GoogleSignInAccount? googleUser = await _googleSignIn.signIn();
        if (googleUser == null) {
          debugPrint('⚠️ Google Sign in cancelled by user');
          return;
        }
        final GoogleSignInAuthentication googleAuth =
            await googleUser.authentication;
        final OAuthCredential credential = GoogleAuthProvider.credential(
          accessToken: googleAuth.accessToken,
          idToken: googleAuth.idToken,
        );

        final UserCredential userCredential =
            await FirebaseAuth.instance.signInWithCredential(credential);
        if (userCredential.user != null) {
          await _syncFirebaseUser(userCredential.user!);
        }
      }
    } catch (e) {
      debugPrint('❌ Firebase Google Sign in error: $e');
      rethrow;
    }
  }

  Future<void> _syncFirebaseUser(User user) async {
    final firestore = FirebaseFirestore.instance;
    final userDoc = await firestore
        .collection(FirestoreCollections.users)
        .doc(user.uid)
        .get();

    if (userDoc.exists && userDoc.data() != null) {
      _currentUser = UserModel.fromMap(userDoc.data() as Map<String, dynamic>);
    } else {
      _currentUser = UserModel(
        id: user.uid,
        email: user.email ?? '',
        name: user.displayName ?? 'User',
        age: 25,
        height: 170,
        weight: 68,
        targetWeight: 65,
        activityLevel: 'moderate',
        healthGoal: 'maintain',
        createdAt: DateTime.now(),
      );
      try {
        await firestore
            .collection(FirestoreCollections.users)
            .doc(user.uid)
            .set(_currentUser!.toMap());
      } catch (e) {
        debugPrint('⚠️ Firestore set user failed: $e');
      }
    }
    notifyListeners();
  }

  Future<void> signOut() async {
    try {
      await FirebaseAuth.instance.signOut();
    } catch (_) {}
    _currentUser = null;
    _profileStatus = DataStatus.notLoaded;
    _profileReadAt = null;
    notifyListeners();
  }

  Future<void> updateProfile(UserModel updatedUser) async {
    try {
      // Demo mode không có Firebase app/document thật. Vẫn cập nhật state để
      // toàn bộ màn hình có thể kiểm thử và dùng đầy đủ chức năng cài đặt.
      if (updatedUser.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(updatedUser.id)
            .set(updatedUser.toMap(), SetOptions(merge: true));
      }
      _currentUser = updatedUser;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  /// Persist an explicit workout-intake answer captured by the chatbot.
  ///
  /// The patch is merged into the existing typed profile before writing, so a
  /// response about pain cannot erase the previously stored availability or
  /// equipment. A Firestore write must succeed before the caller may tell the
  /// user that the answer was remembered.
  Future<WriteResult<WorkoutProfile>> updateWorkoutProfileFromChat(
    Map<String, dynamic> patch, {
    required String mode,
  }) async {
    final user = _currentUser;
    if (user == null) {
      return const WriteResult.rejected('WORKOUT_PROFILE_USER_UNAVAILABLE');
    }

    WorkoutProfile updatedProfile;
    try {
      updatedProfile = WorkoutProfile.applyChatUpdate(
        user.workoutProfile,
        patch,
        mode: mode,
      );
    } on ArgumentError {
      return const WriteResult.rejected('INVALID_WORKOUT_PROFILE_PATCH');
    }

    final updatedUser = user.copyWith(workoutProfile: updatedProfile);
    try {
      if (user.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(user.id)
            .set(
          {'workout_profile': updatedProfile.toJson()},
          SetOptions(merge: true),
        );
      }
      _currentUser = updatedUser;
      _profileStatus =
          user.id == 'demo' ? DataStatus.notLoaded : DataStatus.known;
      _profileReadAt = user.id == 'demo' ? null : DateTime.now();
      notifyListeners();
      return WriteResult.persisted(updatedProfile);
    } catch (e) {
      return const WriteResult.error('WORKOUT_PROFILE_PERSISTENCE_ERROR');
    }
  }

  /// Save the unified V2 nutrition, workout and safety intake. A failed
  /// Firestore write leaves the in-memory user unchanged. Workout fields are
  /// validated only when the user selected exercise support, so a
  /// nutrition-only account is never forced through a workout form.
  Future<WriteResult<HealthProfile>> completeAccountHealthIntake({
    required String primarySupport,
    Map<String, dynamic> workoutAnswers = const <String, dynamic>{},
    Object? gender = _notSet,
    required String? allergyAndAvoidanceNote,
    required String? foodPreferenceNote,
    required String? nutritionGoalNote,
    String? nutritionGoal,
    List<String>? foodAllergies,
    List<String>? dietaryRestrictions,
    List<String>? preferredFoods,
    List<String>? dislikedFoods,
    List<String>? preferredCuisines,
    List<String>? mealPreferences,
    List<String>? foodExclusions,
    String? foodDislikesText,
    String? nutritionNotes,
  }) async {
    final user = _currentUser;
    if (user == null) {
      return const WriteResult.rejected('HEALTH_PROFILE_USER_UNAVAILABLE');
    }

    final normalizedSupport = primarySupport.trim().toUpperCase();
    final requiresWorkout =
        normalizedSupport == 'EXERCISE' || normalizedSupport == 'BOTH';
    WorkoutProfile? completedWorkoutProfile = user.workoutProfile;
    NutritionProfile completedNutritionProfile;
    HealthProfile completedHealthProfile;
    try {
      if (requiresWorkout) {
        completedWorkoutProfile = WorkoutProfile.completeAccountIntake(
          user.workoutProfile,
          workoutAnswers,
        );
      }
      completedNutritionProfile = NutritionProfile.completeAccountIntake(
        user.nutritionProfile,
        allergyAndAvoidanceNote: allergyAndAvoidanceNote,
        foodPreferenceNote: foodPreferenceNote,
        nutritionGoalNote: nutritionGoalNote,
        nutritionGoal: nutritionGoal,
        foodAllergies: foodAllergies,
        dietaryRestrictions: dietaryRestrictions,
        preferredFoods: preferredFoods,
        dislikedFoods: dislikedFoods,
        preferredCuisines: preferredCuisines,
        mealPreferences: mealPreferences,
        foodExclusions: foodExclusions,
        foodDislikesText: foodDislikesText,
        nutritionNotes: nutritionNotes,
      );
      final previousSafety = user.healthProfile?.safetyProfile;
      final safety = SafetyProfile(
        exerciseSafetyProfile: completedWorkoutProfile?.exerciseSafetyProfile ??
            previousSafety?.exerciseSafetyProfile,
        nutritionSafetySnapshot: user.nutritionSafetyProfile.toJson(),
        provenance: <String, String>{
          ...?previousSafety?.provenance,
          if (requiresWorkout)
            'exercise_safety_profile': 'EXPLICIT_UI_SELECTION',
          'nutrition_safety_snapshot': 'LEGACY',
        },
        freshness: <String, String>{
          ...?previousSafety?.freshness,
          'nutrition_safety_snapshot': 'STABLE_UNTIL_CHANGED',
          if (requiresWorkout) 'exercise_safety_profile': 'TIME_SENSITIVE',
          if (requiresWorkout) 'current_pain_status': 'CURRENT_OBSERVATION',
        },
      );
      completedHealthProfile = HealthProfile.completeAccountIntake(
        primarySupport: normalizedSupport,
        nutritionProfile: completedNutritionProfile,
        workoutProfile: completedWorkoutProfile,
        safetyProfile: safety,
      );
    } on ArgumentError {
      return const WriteResult.rejected('INVALID_ACCOUNT_HEALTH_INTAKE');
    }

    final updatedUser = user.copyWith(
      workoutProfile: completedWorkoutProfile,
      nutritionProfile: completedNutritionProfile,
      healthProfile: completedHealthProfile,
      gender: identical(gender, _notSet) ? user.gender : gender,
    );
    try {
      if (user.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(user.id)
            .set(
          {
            // Keep legacy consumers on the stable top-level paths while new
            // clients read the versioned health_profile envelope.
            if (completedWorkoutProfile != null)
              'workout_profile': completedWorkoutProfile.toJson(),
            'nutrition_profile': completedNutritionProfile.toJson(),
            'health_profile': completedHealthProfile.toJson(),
            if (!identical(gender, _notSet)) 'gender': gender,
          },
          SetOptions(merge: true),
        );
      }
      _currentUser = updatedUser;
      _profileStatus =
          user.id == 'demo' ? DataStatus.notLoaded : DataStatus.known;
      _profileReadAt = user.id == 'demo' ? null : DateTime.now();
      notifyListeners();
      return WriteResult.persisted(completedHealthProfile);
    } catch (_) {
      return const WriteResult.error('HEALTH_PROFILE_PERSISTENCE_ERROR');
    }
  }

  /// Persist one explicit nutrition correction without restarting account
  /// intake. The caller must provide a typed patch matching exactly what the
  /// user stated; free text stays raw and unknown mappings are rejected.
  Future<WriteResult<NutritionProfile>> updateNutritionProfileFromChat(
    Map<String, dynamic> patch,
  ) async {
    final user = _currentUser;
    if (user == null) {
      return const WriteResult.rejected('NUTRITION_PROFILE_USER_UNAVAILABLE');
    }
    NutritionProfile updatedNutrition;
    try {
      updatedNutrition = NutritionProfile.applyExplicitUpdate(
        user.nutritionProfile,
        patch,
      );
    } on ArgumentError {
      return const WriteResult.rejected('INVALID_NUTRITION_PROFILE_PATCH');
    }
    final oldHealth = user.healthProfile;
    final updatedHealth = oldHealth == null
        ? null
        : HealthProfile(
            schemaVersion: oldHealth.schemaVersion,
            primarySupport: oldHealth.primarySupport,
            nutritionProfile: updatedNutrition,
            workoutProfile: oldHealth.workoutProfile,
            safetyProfile: oldHealth.safetyProfile,
            completedAt: oldHealth.completedAt,
          );
    final updatedUser = user.copyWith(
      nutritionProfile: updatedNutrition,
      healthProfile: updatedHealth,
    );
    try {
      if (user.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(user.id)
            .set(
          {
            'nutrition_profile': updatedNutrition.toJson(),
            if (updatedHealth != null) 'health_profile': updatedHealth.toJson(),
          },
          SetOptions(merge: true),
        );
      }
      _currentUser = updatedUser;
      _profileStatus =
          user.id == 'demo' ? DataStatus.notLoaded : DataStatus.known;
      _profileReadAt = user.id == 'demo' ? null : DateTime.now();
      notifyListeners();
      return WriteResult.persisted(updatedNutrition);
    } catch (_) {
      return const WriteResult.error('NUTRITION_PROFILE_PERSISTENCE_ERROR');
    }
  }

  Future<void> updateWeight(double newWeight) async {
    if (_currentUser == null) return;
    try {
      final updated = _currentUser!.copyWith(weight: newWeight);

      if (_currentUser!.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(updated.id)
            .update({'weight': newWeight});

        await FirebaseFirestore.instance
            .collection(FirestoreCollections.bodyMetrics)
            .add({
          'userId': updated.id,
          'weight': newWeight,
          'bmi': updated.bmi,
          'recordedAt': DateTime.now().toIso8601String(),
        });
      }

      _currentUser = updated;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  /// Refresh the profile from its authoritative document before a chatbot read.
  Future<bool> refreshCurrentUser() async {
    final user = _currentUser;
    if (user == null) {
      _profileStatus = DataStatus.missing;
      return false;
    }
    if (user.id == 'demo') {
      _profileStatus = DataStatus.notLoaded;
      _profileReadAt = null;
      return false;
    }
    try {
      final doc = await FirebaseFirestore.instance
          .collection(FirestoreCollections.users)
          .doc(user.id)
          .get(const GetOptions(source: Source.server));
      final data = doc.data();
      if (!doc.exists || data == null) {
        _profileStatus = DataStatus.missing;
        return false;
      }
      _currentUser = UserModel.fromMap(data);
      _profileStatus = DataStatus.known;
      _profileReadAt = DateTime.now();
      notifyListeners();
      return true;
    } catch (e) {
      _profileStatus = DataStatus.error;
      return false;
    }
  }

  /// Synchronize profile weight only after a weight-history measurement has
  /// persisted. This method deliberately does not append another measurement.
  Future<WriteResult<UserModel>> synchronizeWeightFromMeasurement(
    double newWeight,
  ) async {
    final user = _currentUser;
    if (user == null || newWeight <= 0) {
      return const WriteResult.rejected('INVALID_PROFILE_WEIGHT');
    }
    final updated = user.copyWith(weight: newWeight);
    if (user.id == 'demo') {
      return const WriteResult.rejected(
          'PROFILE_WEIGHT_PERSISTENCE_UNAVAILABLE');
    }
    try {
      await FirebaseFirestore.instance
          .collection(FirestoreCollections.users)
          .doc(user.id)
          .update({'weight': newWeight});
      _currentUser = updated;
      _profileStatus = DataStatus.known;
      _profileReadAt = DateTime.now();
      notifyListeners();
      return WriteResult.persisted(updated);
    } catch (e) {
      return const WriteResult.error('PROFILE_WEIGHT_SYNC_ERROR');
    }
  }

  Future<void> updateHeight(double newHeight) async {
    if (_currentUser == null) return;
    try {
      final updated = _currentUser!.copyWith(height: newHeight);

      if (_currentUser!.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(updated.id)
            .update({'height': newHeight});
      }

      _currentUser = updated;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  Future<void> updateAge(int newAge) async {
    if (_currentUser == null) return;
    try {
      final updated = _currentUser!.copyWith(age: newAge);

      if (_currentUser!.id != 'demo') {
        await FirebaseFirestore.instance
            .collection(FirestoreCollections.users)
            .doc(updated.id)
            .update({'age': newAge});
      }

      _currentUser = updated;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }
}
