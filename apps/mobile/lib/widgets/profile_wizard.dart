import 'package:flutter/material.dart';
import '../theme/app_theme.dart';
import 'health_surface.dart';

class ProfileStepHeader extends StatelessWidget {
  const ProfileStepHeader(
      {super.key,
      required this.step,
      required this.total,
      required this.title,
      required this.subtitle});
  final int step, total;
  final String title, subtitle;
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Bước $step/$total',
            style: const TextStyle(
                fontWeight: FontWeight.w700, color: AppColors.textSecondary)),
        const SizedBox(height: 12),
        Semantics(
            label: 'Tiến độ hồ sơ, bước $step trên $total',
            child: Row(
                children: List.generate(
                    total,
                    (i) => Expanded(
                            child: Container(
                          height: 5,
                          margin:
                              EdgeInsets.only(right: i == total - 1 ? 0 : 6),
                          decoration: BoxDecoration(
                              color: i < step
                                  ? AppColors.primary
                                  : AppColors.surfaceHover,
                              borderRadius: BorderRadius.circular(10)),
                        ))))),
        const SizedBox(height: 28),
        Text(title,
            style: const TextStyle(
                fontSize: 30,
                height: 1.15,
                letterSpacing: -.9,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 12),
        Text(subtitle,
            style: const TextStyle(
                fontSize: 15, height: 1.5, color: AppColors.textSecondary)),
        const SizedBox(height: 24),
      ]);
}

class ProfileOptionCard<T> extends StatelessWidget {
  const ProfileOptionCard(
      {super.key,
      required this.value,
      required this.selected,
      required this.title,
      required this.onSelected,
      this.icon = Icons.check_circle_outline,
      this.subtitle});
  final T value;
  final bool selected;
  final String title;
  final String? subtitle;
  final IconData icon;
  final ValueChanged<T>? onSelected;
  @override
  Widget build(BuildContext context) => Semantics(
      selected: selected,
      button: true,
      child: Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Material(
          color: selected ? AppColors.primary : AppColors.surface,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(18),
              side: BorderSide(
                  color:
                      selected ? AppColors.primary : AppColors.surfaceHover)),
          child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: onSelected == null ? null : () => onSelected!(value),
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Row(children: [
                  Icon(icon,
                      size: 24,
                      color: selected ? Colors.white : AppColors.primary),
                  const SizedBox(width: 14),
                  Expanded(
                      child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                        Text(title,
                            style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: 15,
                                color: selected
                                    ? Colors.white
                                    : AppColors.textPrimary)),
                        if (subtitle != null)
                          Text(subtitle!,
                              style: TextStyle(
                                  color: selected
                                      ? Colors.white70
                                      : AppColors.textSecondary))
                      ])),
                  const SizedBox(width: 8),
                  Icon(
                      selected
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      size: 20,
                      color: selected ? Colors.white : AppColors.textSecondary),
                ]),
              )),
        ),
      ));
}

class ProfileSummaryCard extends StatelessWidget {
  const ProfileSummaryCard(
      {super.key,
      required this.title,
      required this.values,
      this.onEdit,
      this.icon = Icons.person_outline});
  final String title;
  final Map<String, String> values;
  final VoidCallback? onEdit;
  final IconData icon;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: HealthSurface(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(icon, size: 22),
          const SizedBox(width: 10),
          Expanded(
              child: Text(title,
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w800))),
          if (onEdit != null)
            IconButton(
                tooltip: 'Chỉnh sửa $title',
                onPressed: onEdit,
                icon: const Icon(Icons.edit_outlined, size: 20))
        ]),
        const Divider(height: 24),
        for (final entry in values.entries)
          Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(entry.key,
                        style: const TextStyle(
                            fontSize: 12, color: AppColors.textSecondary)),
                    const SizedBox(height: 4),
                    Text(entry.value,
                        style: const TextStyle(
                            fontWeight: FontWeight.w600, height: 1.4)),
                  ])),
      ])));
}

class ProfileWelcome extends StatelessWidget {
  const ProfileWelcome({super.key, required this.onStart});
  final VoidCallback onStart;
  @override
  Widget build(BuildContext context) => SafeArea(
      child: Center(
          child: SingleChildScrollView(
              padding: const EdgeInsets.all(28),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 480),
                child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 24),
                      Center(
                          child: SizedBox(
                              width: 210,
                              height: 210,
                              child:
                                  Stack(alignment: Alignment.center, children: [
                                Container(
                                    width: 190,
                                    height: 190,
                                    decoration: const BoxDecoration(
                                        color: Color(0xFFEAF0E9),
                                        shape: BoxShape.circle)),
                                Transform.rotate(
                                    angle: -.12,
                                    child: Container(
                                        width: 125,
                                        height: 150,
                                        decoration: BoxDecoration(
                                            color: Colors.white,
                                            borderRadius:
                                                BorderRadius.circular(28),
                                            boxShadow: AppShadows.card),
                                        child: const Icon(Icons.spa_outlined,
                                            size: 70,
                                            color: AppColors.primary))),
                                const Positioned(
                                    right: 1,
                                    bottom: 20,
                                    child: CircleAvatar(
                                        radius: 28,
                                        backgroundColor: Color(0xFFFFE9DC),
                                        child: Icon(Icons.favorite_outline,
                                            color: AppColors.primary,
                                            size: 26))),
                              ]))),
                      const SizedBox(height: 40),
                      const Text('Hồ sơ sức khỏe\ncủa bạn',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 36,
                              fontWeight: FontWeight.w800,
                              letterSpacing: -1.2,
                              height: 1.15)),
                      const SizedBox(height: 18),
                      const Text(
                          'Hoàn thiện một vài thông tin để chatbot có thể tư vấn phù hợp hơn.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 16,
                              height: 1.6,
                              color: AppColors.textSecondary)),
                      const SizedBox(height: 36),
                      FilledButton(
                          onPressed: onStart,
                          style: FilledButton.styleFrom(
                              minimumSize: const Size.fromHeight(56),
                              backgroundColor: AppColors.primary),
                          child: const Text('Bắt đầu')),
                      const SizedBox(height: 18),
                      const Text('Bạn luôn có thể chỉnh sửa lại trong Hồ sơ.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 12, color: AppColors.textSecondary)),
                      const SizedBox(height: 24),
                    ]),
              ))));
}
