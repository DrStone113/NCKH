import 'package:flutter/foundation.dart';
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
        final GoogleSignInAuthentication googleAuth = await googleUser.authentication;
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
        gender: 'male',
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
