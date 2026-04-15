import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import '../models/user_model.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../constants/firestore_collections.dart';

class UserProvider with ChangeNotifier {
  UserModel? _currentUser;

  UserModel? get currentUser => _currentUser;
  bool get isAuthenticated => _currentUser != null;

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
    final GoogleSignIn googleSignIn = GoogleSignIn(
      clientId: '474333392741-sq62656jfsrje0ee4cikouo6fgot1hp1.apps.googleusercontent.com',
      scopes: ['email', 'profile'],
    );
    
    // Ngắt kết nối để xóa cache và buộc chọn lại tài khoản
    try {
      await googleSignIn.disconnect();
    } catch (_) {
      // Ignore nếu chưa có kết nối nào
    }
    
    // Đăng nhập với Google - sẽ hiển thị màn hình chọn tài khoản
    final GoogleSignInAccount? googleUser = await googleSignIn.signIn();
    
    if (googleUser == null) {
      throw Exception('Đăng nhập bị hủy');
    }

    // Lấy thông tin xác thực
    final GoogleSignInAuthentication googleAuth = await googleUser.authentication;

    // Tạo credential cho Firebase
    final credential = GoogleAuthProvider.credential(
      accessToken: googleAuth.accessToken,
      idToken: googleAuth.idToken,
    );

    // Đăng nhập vào Firebase
    final UserCredential userCredential = 
        await FirebaseAuth.instance.signInWithCredential(credential);

    final firestore = FirebaseFirestore.instance;
    final userDoc = await firestore
        .collection(FirestoreCollections.users)
        .doc(userCredential.user!.uid)
        .get();

    if (userDoc.exists) {
      _currentUser = UserModel.fromMap(userDoc.data() as Map<String, dynamic>);
    } else {
      // User mới, tạo profile tạm thời KHÔNG lưu vào Firestore
      // Để màn hình onboarding thu thập thông tin đầy đủ
      _currentUser = UserModel(
        id: userCredential.user!.uid,
        email: googleUser.email,
        name: googleUser.displayName ?? 'User',
        age: 0, // Đặt 0 để trigger onboarding
        gender: 'male',
        height: 0, // Đặt 0 để trigger onboarding
        weight: 0,
        targetWeight: 0,
        activityLevel: 'moderate',
        healthGoal: 'maintain',
        createdAt: DateTime.now(),
      );
      
      // KHÔNG lưu vào Firestore ở đây
      // Sẽ lưu sau khi hoàn thành onboarding
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
