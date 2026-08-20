import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../../providers/ai_chat_provider.dart';
import '../../../providers/user_provider.dart';
import '../../../services/backend_api_service.dart';
import '../../../theme/app_theme.dart';
import '../../chat/screens/chatbot_screen.dart';

class ChatHistorySettingsScreen extends StatefulWidget {
  const ChatHistorySettingsScreen({super.key});

  @override
  State<ChatHistorySettingsScreen> createState() =>
      _ChatHistorySettingsScreenState();
}

class _ChatHistorySettingsScreenState extends State<ChatHistorySettingsScreen> {
  final BackendApiService _api = BackendApiService();
  List<Map<String, dynamic>> _sessions = const [];
  bool _isLoading = true;
  bool _isDeletingAll = false;
  String? _busySessionId;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _isLoading = true;
        _error = null;
      });
    }
    try {
      final userId = context.read<UserProvider>().currentUser?.id;
      final sessions = await _api.getChatSessions(userId: userId);
      if (!mounted) return;
      setState(() => _sessions = sessions);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _openSession(Map<String, dynamic> session) async {
    final sessionId = session['id']?.toString();
    if (sessionId == null || sessionId.isEmpty) return;
    setState(() => _busySessionId = sessionId);
    try {
      final messages = await _api.getSessionMessages(sessionId);
      if (!mounted) return;
      context.read<AIChatProvider>().loadExistingSession(sessionId, messages);
      await Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const ChatbotScreen()),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không thể mở hội thoại: $error')),
      );
    } finally {
      if (mounted) setState(() => _busySessionId = null);
    }
  }

  Future<bool> _confirmDelete({required bool all}) async {
    return await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(all ? 'Xóa toàn bộ lịch sử?' : 'Xóa hội thoại?'),
            content: Text(
              all
                  ? 'Tất cả cuộc trò chuyện sẽ bị xóa vĩnh viễn và không thể khôi phục.'
                  : 'Cuộc trò chuyện này sẽ bị xóa vĩnh viễn.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('Hủy'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.error,
                ),
                child: const Text('Xóa'),
              ),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _deleteSession(String sessionId) async {
    if (!await _confirmDelete(all: false)) return;
    setState(() => _busySessionId = sessionId);
    try {
      await _api.deleteChatSession(sessionId);
      if (!mounted) return;
      if (context.read<AIChatProvider>().currentSessionId == sessionId) {
        context.read<AIChatProvider>().startNewSession();
      }
      setState(() {
        _sessions = _sessions
            .where((session) => session['id']?.toString() != sessionId)
            .toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Đã xóa hội thoại')),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Không thể xóa hội thoại: $error')),
      );
    } finally {
      if (mounted) setState(() => _busySessionId = null);
    }
  }

  Future<void> _deleteAll() async {
    if (_sessions.isEmpty || !await _confirmDelete(all: true)) return;
    setState(() => _isDeletingAll = true);
    var deleted = 0;
    try {
      for (final session in List<Map<String, dynamic>>.from(_sessions)) {
        final id = session['id']?.toString();
        if (id == null || id.isEmpty) continue;
        await _api.deleteChatSession(id);
        deleted++;
      }
      if (!mounted) return;
      context.read<AIChatProvider>().startNewSession();
      setState(() => _sessions = const []);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Đã xóa $deleted cuộc trò chuyện')),
      );
    } catch (error) {
      if (!mounted) return;
      await _load();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Đã xóa $deleted cuộc trò chuyện, sau đó gặp lỗi: $error',
          ),
        ),
      );
    } finally {
      if (mounted) setState(() => _isDeletingAll = false);
    }
  }

  String _formatDate(dynamic raw) {
    final date = DateTime.tryParse(raw?.toString() ?? '')?.toLocal();
    if (date == null) return 'Không rõ thời gian';
    return DateFormat('HH:mm • dd/MM/yyyy').format(date);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Lịch sử hội thoại'),
        actions: [
          if (_sessions.isNotEmpty)
            IconButton(
              onPressed: _isDeletingAll ? null : _deleteAll,
              tooltip: 'Xóa toàn bộ',
              icon: _isDeletingAll
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.delete_sweep_outlined),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _buildBody(),
      ),
    );
  }

  Widget _buildBody() {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 80),
          const Icon(Icons.cloud_off_outlined, size: 52),
          const SizedBox(height: 14),
          const Text(
            'Không tải được lịch sử',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
          const SizedBox(height: 6),
          Text(
            _error!,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AppColors.textSecondary),
          ),
          const SizedBox(height: 18),
          Center(
            child: OutlinedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('Thử lại'),
            ),
          ),
        ],
      );
    }
    if (_sessions.isEmpty) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: const [
          SizedBox(height: 100),
          Icon(Icons.forum_outlined, size: 56, color: AppColors.textHint),
          SizedBox(height: 14),
          Text(
            'Chưa có cuộc trò chuyện nào',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
          ),
          SizedBox(height: 6),
          Text(
            'Các phiên chat với trợ lý sức khỏe sẽ xuất hiện tại đây.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.textSecondary),
          ),
        ],
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      itemCount: _sessions.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final session = _sessions[index];
        final id = session['id']?.toString() ?? '';
        final busy = _busySessionId == id;
        return Material(
          color: AppColors.surface,
          borderRadius: BorderRadius.circular(18),
          child: InkWell(
            onTap: busy ? null : () => _openSession(session),
            borderRadius: BorderRadius.circular(18),
            child: Container(
              padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(18),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Row(
                children: [
                  Container(
                    width: 42,
                    height: 42,
                    decoration: BoxDecoration(
                      color: AppColors.primary.withValues(alpha: 0.08),
                      borderRadius: BorderRadius.circular(13),
                    ),
                    child: const Icon(Icons.smart_toy_outlined),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          session['title']?.toString().trim().isNotEmpty == true
                              ? session['title'].toString()
                              : 'Cuộc trò chuyện mới',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          _formatDate(
                            session['last_active'] ?? session['created_at'],
                          ),
                          style: const TextStyle(
                            color: AppColors.textSecondary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (busy)
                    const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  else
                    IconButton(
                      onPressed: () => _deleteSession(id),
                      tooltip: 'Xóa hội thoại',
                      icon: const Icon(
                        Icons.delete_outline,
                        color: AppColors.error,
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
