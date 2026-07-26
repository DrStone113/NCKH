import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import '../models/health_models.dart';
import '../constants/rasa_config.dart';

class ChatProvider with ChangeNotifier {
  final List<ChatMessage> _messages = [];
  bool _isTyping = false;
  final String _sessionId = DateTime.now().millisecondsSinceEpoch.toString();

  List<ChatMessage> get messages => _messages;
  bool get isTyping => _isTyping;

  void initialize() {
    if (_messages.isEmpty) {
      _messages.add(ChatMessage(
        text: 'Xin chào! 👋 Tôi là trợ lý sức khỏe của bạn.\n\n'
            'Tôi có thể giúp bạn:\n'
            '• Phân tích triệu chứng thiếu hụt dinh dưỡng\n'
            '• Gợi ý thực phẩm bổ sung vi chất\n'
            '• Tư vấn chế độ ăn uống & tập luyện\n'
            '• Đánh giá tình trạng sức khỏe\n\n'
            'Hãy mô tả triệu chứng hoặc đặt câu hỏi!',
        isUser: false,
        quickReplies: ['Tôi hay mệt mỏi', 'Tư vấn giảm cân', 'Đau xương khớp', 'Hay bị chuột rút'],
      ));
    }
  }

  Future<void> sendMessage(String text, [dynamic user]) async {
    _messages.add(ChatMessage(text: text, isUser: true));
    _isTyping = true;
    notifyListeners();

    final response = await _fetchRasaResponse(text);
    _messages.add(response);
    _isTyping = false;
    notifyListeners();
  }

  Future<ChatMessage> _fetchRasaResponse(String userMessage) async {
    try {
      final response = await http
          .post(
            Uri.parse(RasaConfig.webhookUrl),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'sender': _sessionId, 'message': userMessage}),
          )
          .timeout(RasaConfig.requestTimeout);

      final List<dynamic> data = jsonDecode(response.body);

      if (data.isEmpty) {
        return ChatMessage(
          text: 'Xin lỗi, tôi không nhận được phản hồi. Vui lòng thử lại.',
          isUser: false,
        );
      }

      final botText = data
          .map((item) => (item['text'] as String?) ?? '')
          .where((t) => t.isNotEmpty)
          .join('\n\n');

      return ChatMessage(
        text: botText.isNotEmpty
            ? botText
            : 'Xin lỗi, tôi không nhận được phản hồi. Vui lòng thử lại.',
        isUser: false,
      );
    } on http.ClientException {
      return ChatMessage(
        text: 'Xin lỗi, không thể kết nối đến server. Vui lòng kiểm tra kết nối mạng.',
        isUser: false,
      );
    } catch (e) {
      if (e.toString().contains('TimeoutException')) {
        return ChatMessage(
          text: 'Xin lỗi, kết nối đến server bị timeout. Vui lòng thử lại sau.',
          isUser: false,
        );
      }
      return ChatMessage(
        text: 'Xin lỗi, không thể kết nối đến server. Vui lòng kiểm tra kết nối mạng.',
        isUser: false,
      );
    }
  }

  void clear() {
    _messages.clear();
    notifyListeners();
  }
}
