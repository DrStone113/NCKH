import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../constants/ai_chatbot_config.dart';

class TestChatScreen extends StatefulWidget {
  const TestChatScreen({super.key});

  @override
  State<TestChatScreen> createState() => _TestChatScreenState();
}

class _TestChatScreenState extends State<TestChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final List<String> _messages = [];
  WebSocketChannel? _channel;
  bool _isConnected = false;
  String _status = 'Chưa kết nối';

  @override
  void initState() {
    super.initState();
    _connect();
  }

  void _connect() {
    try {
      debugPrint('🔌 Connecting to ${AIChatbotConfig.wsUrl}');
      _channel = WebSocketChannel.connect(
        Uri.parse(AIChatbotConfig.wsUrl),
      );

      _channel!.stream.listen(
        (message) {
          debugPrint('📥 Received: $message');
          final data = jsonDecode(message);
          if (data['type'] == 'token') {
            setState(() {
              if (_messages.isEmpty || !_messages.last.startsWith('Bot: ')) {
                _messages.add('Bot: ${data['content']}');
              } else {
                _messages[_messages.length - 1] += data['content'];
              }
            });
          } else if (data['type'] == 'done') {
            debugPrint('✅ Done');
          }
        },
        onError: (error) {
          debugPrint('❌ Error: $error');
          setState(() {
            _status = 'Lỗi: $error';
            _isConnected = false;
          });
        },
        onDone: () {
          debugPrint('🔌 Disconnected');
          setState(() {
            _status = 'Đã ngắt kết nối';
            _isConnected = false;
          });
        },
      );

      setState(() {
        _status = 'Đã kết nối';
        _isConnected = true;
        _messages.add('System: Đã kết nối thành công!');
      });
      debugPrint('✅ Connected');
    } catch (e) {
      debugPrint('❌ Connection failed: $e');
      setState(() {
        _status = 'Lỗi kết nối: $e';
        _isConnected = false;
      });
    }
  }

  void _sendMessage() {
    final text = _controller.text.trim();
    if (text.isEmpty || !_isConnected) return;

    debugPrint('📤 Sending: $text');

    setState(() {
      _messages.add('You: $text');
    });

    final request = {
      'type': 'chat',
      'session_id': 'test-session-123',
      'message': text,
      'user_context': {
        'age': 25,
        'gender': 'male',
        'height': 170,
        'weight': 70,
        'activity_level': 'moderate',
        'health_goal': 'maintain',
      },
    };

    try {
      _channel!.sink.add(jsonEncode(request));
      _controller.clear();
      debugPrint('✅ Message sent');
    } catch (e) {
      debugPrint('❌ Send failed: $e');
      setState(() {
        _messages.add('System: Lỗi gửi tin nhắn: $e');
      });
    }
  }

  @override
  void dispose() {
    _channel?.sink.close();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Test Chat'),
        backgroundColor: Colors.blue,
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            color: _isConnected ? Colors.green : Colors.red,
            child: Text(
              _status,
              style: const TextStyle(color: Colors.white),
            ),
          ),
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final msg = _messages[index];
                final isUser = msg.startsWith('You: ');
                return Align(
                  alignment:
                      isUser ? Alignment.centerRight : Alignment.centerLeft,
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isUser ? Colors.blue : Colors.grey[300],
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      msg,
                      style: TextStyle(
                        color: isUser ? Colors.white : Colors.black,
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          Container(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      hintText: 'Nhập tin nhắn...',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _sendMessage(),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isConnected ? _sendMessage : null,
                  child: const Text('Gửi'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
