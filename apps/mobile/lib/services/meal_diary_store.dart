import 'package:cloud_firestore/cloud_firestore.dart';

import '../constants/firestore_collections.dart';
import '../models/meal_model.dart';

abstract interface class MealDiaryStore {
  Future<void> save(MealModel meal);

  Future<MealModel?> read(String mealId);

  Future<List<MealModel>> readForUser(String userId);

  Future<void> delete(String mealId);
}

class FirestoreMealDiaryStore implements MealDiaryStore {
  FirebaseFirestore get _firestore => FirebaseFirestore.instance;

  @override
  Future<void> save(MealModel meal) async {
    await _firestore
        .collection(FirestoreCollections.mealDiary)
        .doc(meal.id)
        .set(meal.toMap());
  }

  @override
  Future<MealModel?> read(String mealId) async {
    final doc = await _firestore
        .collection(FirestoreCollections.mealDiary)
        .doc(mealId)
        .get(const GetOptions(source: Source.server));
    final data = doc.data();
    return doc.exists && data != null ? MealModel.fromMap(data) : null;
  }

  @override
  Future<List<MealModel>> readForUser(String userId) async {
    final snapshot = await _firestore
        .collection(FirestoreCollections.mealDiary)
        .where('userId', isEqualTo: userId)
        .get(const GetOptions(source: Source.server));
    return snapshot.docs.map((doc) => MealModel.fromMap(doc.data())).toList();
  }

  @override
  Future<void> delete(String mealId) async {
    await _firestore
        .collection(FirestoreCollections.mealDiary)
        .doc(mealId)
        .delete();
  }
}
