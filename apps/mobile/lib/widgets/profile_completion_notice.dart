import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../features/auth/screens/workout_account_intake_screen.dart';
import '../features/settings/screens/profile_settings_screen.dart';
import '../models/profile_readiness.dart';
import '../providers/user_provider.dart';

/// An actionable checklist, without assuming missing safety answers are "no".
class ProfileCompletionNotice extends StatelessWidget {
  const ProfileCompletionNotice({
    super.key,
    required this.scope,
    this.issue,
  });

  final ProfileContextScope scope;
  final String? issue;

  @override
  Widget build(BuildContext context) {
    final user = context.watch<UserProvider>().currentUser;
    if (user == null) return const SizedBox.shrink();
    final readiness = ProfileReadiness.assess(user, scope: scope);
    if (!readiness.hasMissingFields && issue == null) {
      return const SizedBox.shrink();
    }
    return Material(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              issue ??
                  (readiness.canSend
                      ? 'Bổ sung hồ sơ để chatbot tư vấn phù hợp hơn.'
                      : 'Hồ sơ còn thiếu thông tin cần thiết để bắt đầu chat.'),
              key: const Key('chat-profile-issue'),
            ),
            if (readiness.hasMissingFields) ...[
              Text(
                readiness.missingFields.values.take(3).join(' · ') +
                    (readiness.missingFields.length > 3 ? '…' : ''),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton(
                  key: const Key('complete-chat-profile'),
                  onPressed: () => _showChecklist(context, readiness),
                  child: const Text('Bổ sung hồ sơ'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _showChecklist(
      BuildContext context, ProfileReadiness readiness) async {
    final section = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Thông tin cần bổ sung',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 12),
              Flexible(
                child: SingleChildScrollView(
                  child: Column(
                    children: [
                      for (final entry in readiness.missingFields.entries)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          title: Text(entry.value),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => Navigator.pop(sheetContext, entry.key),
                        ),
                    ],
                  ),
                ),
              ),
              const Text(
                  'Thông tin chưa rõ hoặc không cung cấp vẫn được giữ là chưa biết; chatbot sẽ không tự điền.'),
            ],
          ),
        ),
      ),
    );
    if (section == null || !context.mounted) return;
    final user = context.read<UserProvider>().currentUser;
    if (user == null) return;
    final domainForm = section == 'health_profile' ||
        section.startsWith('nutrition_profile.') ||
        section == 'workout_profile';
    var support = user.healthProfile?.primarySupport;
    if (section == 'workout_profile') {
      support = support == 'EXERCISE' ? 'EXERCISE' : 'BOTH';
    } else if (section.startsWith('nutrition_profile.')) {
      support =
          support == 'EXERCISE' || support == 'BOTH' ? 'BOTH' : 'NUTRITION';
    }
    await Navigator.of(context).push(MaterialPageRoute<void>(
      builder: (routeContext) => domainForm
          ? WorkoutAccountIntakeScreen(
              initialSupport: support,
              onSaved: () => Navigator.of(routeContext).pop(),
            )
          : ProfileSettingsScreen(
              isAccountSetup: user.needsBasicProfileIntake,
              onSaved: () => Navigator.of(routeContext).pop(),
            ),
    ));
  }
}
