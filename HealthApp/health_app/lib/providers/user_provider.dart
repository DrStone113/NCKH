import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/user_model.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../constants/firestore_collections.dart';

class UserProvider with ChangeNotifier {
  UserModel? _currentUser;
  bool _isInitialized = false;

  UserModel? get currentUser => _currentUser;
  bool get isAuthenticated => _currentUser != null;
  bool get isInitialized => _isInitialized;

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
          debugPrint('✅ Session restored: ${_currentUser!.name}');
        }
      }
    } catch (e) {
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
      gender: 'male',
      height: 170,
      weight: 68,
      targetWeight: 65,
      activityLevel: 'moderate',
      healthGoal: 'maintain',
      createdAt: DateTime.now(),
    );
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
        height: userData.height,
        weight: userData.weight,
        targetWeight: userData.targetWeight,
        activityLevel: userData.activityLevel,
        healthGoal: userData.healthGoal,
        createdAt: DateTime.now(),
      );

      await firestore.collection(FirestoreCollections.users).doc(user.id).set(user.toMap());
      _currentUser = user;
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  Future<void> signIn(String email, String password) async {
    try {
      final auth = FirebaseAuth.instance;
      final firestore = FirebaseFirestore.instance;

      UserCredential credential = await auth.signInWithEmailAndPassword(
        email: email,
        password: password,
      );

      DocumentSnapshot doc = await firestore
          .collection(FirestoreCollections.users)
          .doc(credential.user!.uid)
          .get();

      _currentUser = UserModel.fromMap(doc.data() as Map<String, dynamic>);
      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }

  Future<void> signInWithGoogle() async {
    try {
      // Dùng Firebase popup flow - hoạt động trên localhost và web
      final googleProvider = GoogleAuthProvider();
      googleProvider.addScope('email');
      googleProvider.addScope('profile');

      final UserCredential userCredential =
          await FirebaseAuth.instance.signInWithPopup(googleProvider);

      final firestore = FirebaseFirestore.instance;
      final userDoc = await firestore
          .collection(FirestoreCollections.users)
          .doc(userCredential.user!.uid)
          .get();

      if (userDoc.exists) {
        _currentUser = UserModel.fromMap(userDoc.data() as Map<String, dynamic>);
      } else {
        // User mới - trigger onboarding
        _currentUser = UserModel(
          id: userCredential.user!.uid,
          email: userCredential.user!.email ?? '',
          name: userCredential.user!.displayName ?? 'User',
          age: 0,
          gender: 'male',
          height: 0,
          weight: 0,
          targetWeight: 0,
          activityLevel: 'moderate',
          healthGoal: 'maintain',
          createdAt: DateTime.now(),
        );
      }

      notifyListeners();
    } catch (e) {
      rethrow;
    }
  }


  Future<void> signOut() async {
    try {
      await FirebaseAuth.instance.signOut();
    } catch (_) {}
    _currentUser = null;
    notifyListeners();
  }

  Future<void> updateProfile(UserModel updatedUser) async {
    try {
      // Dùng set với merge: true để tạo mới hoặc cập nhật
      await FirebaseFirestore.instance
          .collection(FirestoreCollections.users)
          .doc(updatedUser.id)
          .set(updatedUser.toMap(), SetOptions(merge: true));
      _currentUser = updatedUser;
      notifyListeners();
    } catch (e) {
      rethrow;
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

        await FirebaseFirestore.instance.collection(FirestoreCollections.bodyMetrics).add({
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
