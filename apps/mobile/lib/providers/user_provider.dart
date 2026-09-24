import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/user_model.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../constants/firestore_collections.dart';
import '../models/app_state_value.dart';
import '../services/firestore_references.dart';

class UserProvider with ChangeNotifier {
  static const _notSet = Object();
  // Only the isolated browser-acceptance build enables this.  It makes the
  // already existing demo account complete its otherwise lengthy onboarding;
  // it is not a production login bypass and remains false in normal builds.
  static const bool _planV2E2EDemo = bool.fromEnvironment('PLAN_V2_E2E_DEMO');
  UserModel? _currentUser;
  bool _isInitialized = false;
  DataStatus _profileStatus = DataStatus.notLoaded;
  DateTime? _profileReadAt;
  StreamSubscription<User?>? _authSubscription;
  String? _firebaseUserId;
  int _sessionGeneration = 0;
  bool _profileLoading = false;

  UserModel? get currentUser => _currentUser;
  bool get isAuthenticated => _currentUser != null;
  bool get isFirebaseAuthenticated => _firebaseUserId != null;
  bool get isProfileLoading => _profileLoading;
  bool get hasProfileError =>
      isFirebaseAuthenticated &&
      !_profileLoading &&
      _profileStatus == DataStatus.error;
  bool get isInitialized => _isInitialized;
  DataStatus get profileStatus => _profileStatus;
  DateTime? get profileReadAt => _profileReadAt;
  bool get needsWorkoutAccountIntake =>
      _currentUser?.needsWorkoutAccountIntake ?? false;
  bool get needsAccountHealthIntake =>
      _currentUser?.needsAccountHealthIntake ?? false;
  bool get needsBasicProfileIntake =>
      _currentUser?.needsBasicProfileIntake ?? false;

  UserProvider() {
    if (_planV2E2EDemo) {
      // The acceptance build has an explicit bearer-backed test principal.
      // Recreate only its local display session after a browser refresh so the
      // test can verify server read-back/reconnect rather than Firebase state.
      setDemoUser();
      _isInitialized = true;
    } else {
      _watchSession();
    }
  }

  /// Keep application identity aligned with Firebase, including expiry/signout.
  void _watchSession() {
    try {
      _authSubscription = FirebaseAuth.instance.authStateChanges().listen(
        _applyFirebaseSession,
        onError: (Object error, StackTrace stackTrace) {
          debugPrint('Session observer failed: $error');
          _clearFirebaseSession(status: DataStatus.error);
        },
      );
    } catch (e) {
      debugPrint('Session observer unavailable: $e');
      _clearFirebaseSession(status: DataStatus.error);
    }
  }

  Future<void> _applyFirebaseSession(User? firebaseUser) async {
    if (firebaseUser == null) {
      _clearFirebaseSession();
      return;
    }
    final generation = ++_sessionGeneration;
    _firebaseUserId = firebaseUser.uid;
    _profileLoading = true;
    _profileStatus = DataStatus.notLoaded;
    _isInitialized = true;
    notifyListeners();
    try {
      debugPrint('Restoring Firebase session for: ${firebaseUser.email}');
      await _syncFirebaseUser(firebaseUser, generation: generation);
      if (!_isCurrentFirebaseSession(firebaseUser.uid, generation)) return;
      _profileLoading = false;
      _isInitialized = true;
      notifyListeners();
    } catch (e) {
      if (!_isCurrentFirebaseSession(firebaseUser.uid, generation)) return;
      _profileLoading = false;
      _profileStatus = DataStatus.error;
      _isInitialized = true;
      debugPrint('Session restore failed: $e');
      notifyListeners();
    }
  }

  Future<void> retryProfileBootstrap() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user != null) await _applyFirebaseSession(user);
  }

  void _clearFirebaseSession({DataStatus status = DataStatus.notLoaded}) {
    _sessionGeneration++;
    _firebaseUserId = null;
    _profileLoading = false;
    _currentUser = null;
    _profileStatus = status;
    _profileReadAt = null;
    _isInitialized = true;
    notifyListeners();
  }

  /// Demo mode - set fake user for UI testing without Firebase
  void setDemoUser() {
    unawaited(_authSubscription?.cancel());
    _authSubscription = null;
    final nutritionProfile = _planV2E2EDemo
        ? NutritionProfile.completeAccountIntake(
            null,
            allergyAndAvoidanceNote: null,
            foodPreferenceNote: null,
            nutritionGoalNote: null,
            nutritionGoal: 'MAINTAIN',
          )
        : null;
    final healthProfile = nutritionProfile == null
        ? null
        : HealthProfile.completeAccountIntake(
            primarySupport: 'NUTRITION',
            nutritionProfile: nutritionProfile,
          );
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
      nutritionProfile: nutritionProfile,
      healthProfile: healthProfile,
      basicProfileCompletedAt: _planV2E2EDemo ? DateTime.now() : null,
      createdAt: DateTime.now(),
    );
    _profileStatus = DataStatus.notLoaded;
    _profileReadAt = null;
    notifyListeners();
  }

  Future<void> signUp(String email, String password, {String name = ''}) async {
    try {
      if (_authSubscription == null && !_planV2E2EDemo) _watchSession();
      final auth = FirebaseAuth.instance;
      final firestore = FirebaseFirestore.instance;

      UserCredential credential = await auth.createUserWithEmailAndPassword(
        email: email,
        password: password,
      );

      final user = UserModel.newAccount(
        id: credential.user!.uid,
        email: credential.user!.email ?? email,
        name: name,
      );

      await FirestoreReferences.users(firestore).doc(user.id).set(user);
      // The auth stream owns projection into application session state.
    } catch (e) {
      rethrow;
    }
  }

  Future<void> signIn(String email, String password) async {
    try {
      if (_authSubscription == null && !_planV2E2EDemo) _watchSession();
      final auth = FirebaseAuth.instance;
      await auth.signInWithEmailAndPassword(
        email: email.trim(),
        password: password.trim(),
      );
    } catch (e) {
      rethrow;
    }
  }

  final GoogleSignIn _googleSignIn = GoogleSignIn();

  Future<void> signInWithGoogle() async {
    try {
      if (_authSubscription == null && !_planV2E2EDemo) _watchSession();
      if (kIsWeb) {
        final googleProvider = GoogleAuthProvider();
        googleProvider.addScope('email');
        googleProvider.addScope('profile');

        await FirebaseAuth.instance.signInWithPopup(googleProvider);
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
        await FirebaseAuth.instance.signInWithCredential(credential);
      }
    } catch (e) {
      debugPrint('❌ Firebase Google Sign in error: $e');
      rethrow;
    }
  }

  bool _isCurrentFirebaseSession(String uid, int generation) =>
      _firebaseUserId == uid && _sessionGeneration == generation;

  Future<void> _syncFirebaseUser(User user, {int? generation}) async {
    final firestore = FirebaseFirestore.instance;
    final userDoc =
        await FirestoreReferences.users(firestore).doc(user.uid).get();

    final UserModel syncedUser;
    if (userDoc.exists && userDoc.data() != null) {
      syncedUser = userDoc.data()!;
    } else {
      syncedUser = UserModel.newAccount(
        id: user.uid,
        email: user.email ?? '',
        name: user.displayName ?? '',
      );
      await FirestoreReferences.users(firestore).doc(user.uid).set(syncedUser);
    }
    if (generation != null &&
        !_isCurrentFirebaseSession(user.uid, generation)) {
      return;
    }
    _currentUser = syncedUser;
    _profileStatus = DataStatus.known;
    _profileReadAt = DateTime.now();
    notifyListeners();
  }

  Future<void> signOut() async {
    await FirebaseAuth.instance.signOut();
    _clearFirebaseSession();
  }

  Future<void> updateProfile(UserModel updatedUser) async {
    try {
      // Demo mode không có Firebase app/document thật. Vẫn cập nhật state để
      // toàn bộ màn hình có thể kiểm thử và dùng đầy đủ chức năng cài đặt.
      if (updatedUser.id != 'demo') {
        await FirestoreReferences.users()
            .doc(updatedUser.id)
            .set(updatedUser, SetOptions(merge: true));
      }
      _currentUser = updatedUser;
      _profileStatus =
          updatedUser.id == 'demo' ? DataStatus.notLoaded : DataStatus.known;
      _profileReadAt = updatedUser.id == 'demo' ? null : DateTime.now();
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  Future<void> completeBasicProfile(UserModel updatedUser) async {
    if (_currentUser == null || updatedUser.id != _currentUser!.id) {
      throw ArgumentError('BASIC_PROFILE_USER_MISMATCH');
    }
    if (!updatedUser.hasValidBasicProfile) {
      throw ArgumentError('INVALID_BASIC_PROFILE');
    }
    await updateProfile(updatedUser.copyWith(
      basicProfileCompletedAt: DateTime.now(),
    ));
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
      final doc = await FirestoreReferences.users()
          .doc(user.id)
          .get(const GetOptions(source: Source.server));
      final data = doc.data();
      if (_currentUser?.id != user.id) return false;
      if (!doc.exists || data == null) {
        _profileStatus = DataStatus.missing;
        return false;
      }
      _currentUser = data;
      _profileStatus = DataStatus.known;
      _profileReadAt = DateTime.now();
      notifyListeners();
      return true;
    } catch (e) {
      if (_currentUser?.id != user.id) return false;
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

  @override
  void dispose() {
    _authSubscription?.cancel();
    super.dispose();
  }
}
