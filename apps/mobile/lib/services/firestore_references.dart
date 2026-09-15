import 'package:cloud_firestore/cloud_firestore.dart';

import '../constants/firestore_collections.dart';
import '../models/user_model.dart';

/// Typed Firestore references shared by persistence providers.
///
/// Partial profile patches intentionally continue to use the raw collection
/// API because merge patches are not complete [UserModel] values. Full reads
/// and replacements cross this converter boundary instead of leaking
/// Firestore maps into consumers.
class FirestoreReferences {
  const FirestoreReferences._();

  static CollectionReference<UserModel> users([FirebaseFirestore? firestore]) {
    final database = firestore ?? FirebaseFirestore.instance;
    return database
        .collection(FirestoreCollections.users)
        .withConverter<UserModel>(
          fromFirestore: (snapshot, _) => UserModel.fromMap({
            ...?snapshot.data(),
            'id': snapshot.id,
          }),
          toFirestore: (user, _) => user.toMap(),
        );
  }
}
