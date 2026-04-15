import 'package:flutter/material.dart';
import '../utils/seed_data.dart';

class AdminSeedScreen extends StatefulWidget {
  const AdminSeedScreen({super.key});

  @override
  State<AdminSeedScreen> createState() => _AdminSeedScreenState();
}

class _AdminSeedScreenState extends State<AdminSeedScreen> {
  bool _isSeeding = false;
  String _message = '';

  Future<void> _runSeed() async {
    setState(() {
      _isSeeding = true;
      _message = 'Đang seed data...';
    });

    try {
      await SeedData.seedDatabase();
      setState(() {
        _isSeeding = false;
        _message = '✅ Seed data thành công!';
      });
    } catch (e) {
      setState(() {
        _isSeeding = false;
        _message = '❌ Lỗi: $e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Admin - Seed Database'),
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(
                Icons.storage,
                size: 80,
                color: Colors.blue,
              ),
              const SizedBox(height: 24),
              const Text(
                'Seed Database',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              const Text(
                'Tạo dữ liệu mẫu cho:\n• Bài tập\n• Món ăn\n• Triệu chứng\n• Thiếu hụt vi chất',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 16),
              ),
              const SizedBox(height: 32),
              if (_isSeeding)
                const CircularProgressIndicator()
              else
                ElevatedButton.icon(
                  onPressed: _runSeed,
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Chạy Seed Data'),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 32,
                      vertical: 16,
                    ),
                  ),
                ),
              const SizedBox(height: 24),
              if (_message.isNotEmpty)
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: _message.contains('✅')
                        ? Colors.green.withOpacity(0.1)
                        : Colors.red.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    _message,
                    style: TextStyle(
                      color: _message.contains('✅')
                          ? Colors.green
                          : Colors.red,
                      fontSize: 16,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
