import 'package:flutter_test/flutter_test.dart';
import 'package:health_app/firebase_options.dart';

void main() {
  test('Android Firebase options match the registered com.example.app client',
      () {
    expect(
      DefaultFirebaseOptions.android.appId,
      '1:474333392741:android:9cef1d4548afe2bda23b8c',
    );
    expect(
      DefaultFirebaseOptions.android.apiKey,
      'AIzaSyB3X9kRzFUB1iLj9o9lPpEzpU5NklQzh3c',
    );
    expect(DefaultFirebaseOptions.android.projectId, 'healthcare-191d8');
  });
}
