// File generated from Firebase Console configuration
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;

/// Default [FirebaseOptions] for use with your Firebase apps.
///
/// Example:
/// ```dart
/// import 'firebase_options.dart';
/// // ...
/// await Firebase.initializeApp(
///   options: DefaultFirebaseOptions.currentPlatform,
/// );
/// ```
class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      case TargetPlatform.macOS:
        return macos;
      case TargetPlatform.windows:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for windows - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      case TargetPlatform.linux:
        throw UnsupportedError(
          'DefaultFirebaseOptions have not been configured for linux - '
          'you can reconfigure this by running the FlutterFire CLI again.',
        );
      default:
        throw UnsupportedError(
          'DefaultFirebaseOptions are not supported for this platform.',
        );
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyDdPEY1qvG2fhDZbQwNKKVAMS2zS8iKhDk',
    appId: '1:474333392741:web:0ad44b7c221c6f05a23b8c',
    messagingSenderId: '474333392741',
    projectId: 'healthcare-191d8',
    authDomain: 'healthcare-191d8.firebaseapp.com',
    storageBucket: 'healthcare-191d8.firebasestorage.app',
    measurementId: 'G-1QE26CWYMW',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyB3X9kRzFUB1iLj9o9lPpEzpU5NklQzh3c',
    appId: '1:474333392741:android:9cef1d4548afe2bda23b8c',
    messagingSenderId: '474333392741',
    projectId: 'healthcare-191d8',
    storageBucket: 'healthcare-191d8.firebasestorage.app',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyDdPEY1qvG2fhDZbQwNKKVAMS2zS8iKhDk',
    appId: '1:474333392741:ios:0ad44b7c221c6f05a23b8c',
    messagingSenderId: '474333392741',
    projectId: 'healthcare-191d8',
    storageBucket: 'healthcare-191d8.firebasestorage.app',
    iosBundleId: 'com.example.healthApp',
  );

  static const FirebaseOptions macos = FirebaseOptions(
    apiKey: 'AIzaSyDdPEY1qvG2fhDZbQwNKKVAMS2zS8iKhDk',
    appId: '1:474333392741:ios:0ad44b7c221c6f05a23b8c',
    messagingSenderId: '474333392741',
    projectId: 'healthcare-191d8',
    storageBucket: 'healthcare-191d8.firebasestorage.app',
    iosBundleId: 'com.example.healthApp',
  );
}
