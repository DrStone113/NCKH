import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

typedef RecommendationFeedbackHandler = Future<void> Function(
  String eventType,
  String? reasonCode,
);

/// Lightweight N3.2 feedback UI. It is rendered only for a server-issued
/// shadow recommendation identifier; normal meal cards remain uncluttered.
class RecommendationFeedbackBar extends StatefulWidget {
  final RecommendationFeedbackHandler onFeedback;
  final VoidCallback? onChangeDish;
  final List<String> publicReasonCodes;

  const RecommendationFeedbackBar({
    super.key,
    required this.onFeedback,
    this.onChangeDish,
    this.publicReasonCodes = const [],
  });

  @override
  State<RecommendationFeedbackBar> createState() =>
      _RecommendationFeedbackBarState();
}

class _RecommendationFeedbackBarState extends State<RecommendationFeedbackBar> {
  String? _submitted;
  String? _feedbackError;
  bool _working = false;

  Future<void> _submit(String eventType, [String? reasonCode]) async {
    if (_working) return;
    setState(() {
      _working = true;
      _feedbackError = null;
    });
    try {
      await widget.onFeedback(eventType, reasonCode);
      if (mounted) setState(() => _submitted = eventType);
    } catch (_) {
      // A client acknowledgement is meaningful only after the durable API
      // operation succeeds. Keep the action retryable and never imply success.
      if (mounted) {
        setState(
            () => _feedbackError = 'Không thể lưu phản hồi. Vui lòng thử lại.');
      }
    } finally {
      if (mounted) setState(() => _working = false);
    }
  }

  Future<void> _reject() async {
    final reason = await showModalBottomSheet<String?>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Món này chưa hợp vì…',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 6),
              const Text(
                'Tuỳ chọn — bạn có thể bỏ qua lý do.',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 8),
              ..._reasons.map(
                (reason) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(reason.$2),
                  onTap: () => Navigator.pop(context, reason.$1),
                ),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, 'OTHER'),
                child: const Text('Bỏ qua lý do'),
              ),
            ],
          ),
        ),
      ),
    );
    if (reason != null) await _submit('REJECTED', reason);
  }

  void _whyThisDish() {
    final reasons = widget.publicReasonCodes
        .map(_publicReason)
        .whereType<String>()
        .toList(growable: false);
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Vì sao món này?',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              const SizedBox(height: 10),
              if (reasons.isEmpty)
                const Text(
                    'Món được chọn sau khi kiểm tra các điều kiện phù hợp.')
              else
                ...reasons.map((reason) => Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text('• $reason'),
                    )),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(10, 0, 10, 9),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 2,
            runSpacing: 2,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _action(
                key: const Key('recommendation-like'),
                semanticsLabel: 'n3-feedback-like',
                icon: Icons.thumb_up_outlined,
                label: _submitted == 'LIKED' ? 'Đã thích' : 'Thích',
                onPressed: () => _submit('LIKED'),
              ),
              _action(
                key: const Key('recommendation-dislike'),
                semanticsLabel: 'n3-feedback-reject',
                icon: Icons.thumb_down_outlined,
                label: 'Không hợp',
                onPressed: _reject,
              ),
              _action(
                key: const Key('recommendation-save'),
                semanticsLabel: 'n3-feedback-save',
                icon: Icons.bookmark_add_outlined,
                label: _submitted == 'SAVED' ? 'Đã lưu' : 'Lưu lại',
                onPressed: () => _submit('SAVED'),
              ),
              if (widget.onChangeDish != null)
                _action(
                  key: const Key('recommendation-change'),
                  semanticsLabel: 'n3-feedback-substitute',
                  icon: Icons.refresh_rounded,
                  label: 'Đổi món',
                  onPressed: widget.onChangeDish!,
                ),
              if (widget.publicReasonCodes.isNotEmpty)
                _action(
                  key: const Key('recommendation-why'),
                  semanticsLabel: 'n3-feedback-why',
                  icon: Icons.help_outline_rounded,
                  label: 'Vì sao?',
                  onPressed: _whyThisDish,
                ),
            ],
          ),
          if (_feedbackError != null)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Semantics(
                key: const Key('recommendation-feedback-error'),
                label: 'n3-feedback-error',
                liveRegion: true,
                child: Text(
                  _feedbackError!,
                  style: const TextStyle(
                    fontSize: 11,
                    color: AppColors.error,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  Widget _action({
    required Key key,
    required String semanticsLabel,
    required IconData icon,
    required String label,
    required VoidCallback onPressed,
  }) {
    return Semantics(
      label: semanticsLabel,
      button: true,
      child: TextButton.icon(
        key: key,
        onPressed: _working ? null : onPressed,
        icon: Icon(icon, size: 15),
        label: Text(label),
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize: const Size(48, 48),
          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 4),
          textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
        ),
      ),
    );
  }
}

const _reasons = <(String, String)>[
  ('DO_NOT_LIKE', 'Không thích món này'),
  ('NOT_TODAY', 'Không phải hôm nay'),
  ('TOO_EXPENSIVE', 'Hơi vượt ngân sách'),
  ('TOO_HARD_TO_COOK', 'Khó hoặc mất thời gian nấu'),
  ('INGREDIENT_UNAVAILABLE', 'Thiếu nguyên liệu'),
  ('TOO_REPETITIVE', 'Gần đây bị lặp lại'),
  ('PORTION_TOO_LARGE', 'Khẩu phần hơi nhiều'),
  ('PORTION_TOO_SMALL', 'Khẩu phần hơi ít'),
];

String? _publicReason(String code) => switch (code) {
      'NUTRITION_REMAINING_FIT' => 'Phù hợp lượng dinh dưỡng còn lại.',
      'CONFIRMED_PREFERENCE_MATCH' => 'Phù hợp sở thích bạn đã xác nhận.',
      'INFERRED_PREFERENCE_MATCH' =>
        'Phù hợp với các phản hồi gần đây của bạn.',
      'DIVERSITY_PROTEIN_ROTATION' ||
      'DIVERSITY_DISH_ROTATION' =>
        'Giúp đổi món hoặc nguồn đạm gần đây.',
      'PORTION_ADAPTABLE' => 'Có thể điều chỉnh khẩu phần phù hợp.',
      'STAGING_SOURCE' ||
      'RUNTIME_EXTERNAL_SOURCE' =>
        'Công thức đang ở chế độ thử nghiệm; dinh dưỡng được tính lại từ nguồn chuẩn.',
      'CANONICAL_SOURCE' => 'Dùng công thức trong thư viện chuẩn.',
      _ => null,
    };
