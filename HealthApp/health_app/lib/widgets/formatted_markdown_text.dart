import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

/// Component tự động phân tích và định dạng lại văn bản Markdown từ Chatbot (Headers, Bold, Bullet points, Sub-bullets, Code)
class FormattedMarkdownText extends StatelessWidget {
  final String text;
  final TextStyle? style;
  final Color? textColor;

  const FormattedMarkdownText({
    super.key,
    required this.text,
    this.style,
    this.textColor,
  });

  @override
  Widget build(BuildContext context) {
    final baseStyle = style ??
        TextStyle(
          fontSize: 14,
          color: textColor ?? AppColors.textPrimary,
          height: 1.5,
        );

    final lines = text.split('\n');
    final widgets = <Widget>[];

    int index = 0;
    while (index < lines.length) {
      final line = lines[index];
      final trimmed = line.trim();

      if (trimmed.isEmpty) {
        widgets.add(const SizedBox(height: 4));
        index++;
        continue;
      }

      // Check Headings (#, ##, ###, ####)
      if (trimmed.startsWith('# ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 4),
          child: Text(
            trimmed.substring(2).trim(),
            style: baseStyle.copyWith(
              fontSize: (baseStyle.fontSize ?? 14) + 6,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
          ),
        ));
        index++;
        continue;
      }
      if (trimmed.startsWith('## ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 4),
          child: Text(
            trimmed.substring(3).trim(),
            style: baseStyle.copyWith(
              fontSize: (baseStyle.fontSize ?? 14) + 4,
              fontWeight: FontWeight.bold,
              color: AppColors.primary,
            ),
          ),
        ));
        index++;
        continue;
      }
      if (trimmed.startsWith('### ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 8, bottom: 4),
          child: _buildRichText(
            trimmed.substring(4).trim(),
            baseStyle.copyWith(
              fontSize: (baseStyle.fontSize ?? 14) + 2,
              fontWeight: FontWeight.bold,
            ),
          ),
        ));
        index++;
        continue;
      }
      if (trimmed.startsWith('#### ')) {
        widgets.add(Padding(
          padding: const EdgeInsets.only(top: 6, bottom: 2),
          child: _buildRichText(
            trimmed.substring(5).trim(),
            baseStyle.copyWith(
              fontSize: (baseStyle.fontSize ?? 14) + 1,
              fontWeight: FontWeight.bold,
            ),
          ),
        ));
        index++;
        continue;
      }

      // Check Bullet Lists (* , - , + , 1. , etc.)
      final indentCount = _calculateIndent(line);
      final bulletMatch =
          RegExp(r'^(\s*)([\*\-\+]|\d+[\.\)])\s+(.*)$').firstMatch(line);

      if (bulletMatch != null) {
        final bulletSymbol = bulletMatch.group(2)!;
        final contentText = bulletMatch.group(3)!;
        final isSubBullet = indentCount >= 2;

        final bulletIcon =
            (bulletSymbol == '*' || bulletSymbol == '-' || bulletSymbol == '+')
                ? (isSubBullet ? '◦' : '•')
                : '$bulletSymbol';

        widgets.add(Padding(
          padding: EdgeInsets.only(
            left: (isSubBullet ? 16.0 : 4.0) +
                (indentCount > 4 ? (indentCount - 2) * 4.0 : 0.0),
            top: 2,
            bottom: 2,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: isSubBullet ? 14 : 16,
                child: Text(
                  bulletIcon,
                  style: baseStyle.copyWith(
                    fontWeight: FontWeight.bold,
                    color: isSubBullet
                        ? AppColors.textSecondary
                        : AppColors.primary,
                  ),
                ),
              ),
              Expanded(
                child: _buildRichText(contentText, baseStyle),
              ),
            ],
          ),
        ));
        index++;
        continue;
      }

      // Regular paragraph line
      widgets.add(Padding(
        padding: const EdgeInsets.only(top: 1, bottom: 1),
        child: _buildRichText(trimmed, baseStyle),
      ));
      index++;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: widgets,
    );
  }

  int _calculateIndent(String line) {
    int spaces = 0;
    for (int i = 0; i < line.length; i++) {
      if (line[i] == ' ') {
        spaces++;
      } else if (line[i] == '\t') {
        spaces += 4;
      } else {
        break;
      }
    }
    return spaces;
  }

  Widget _buildRichText(String rawText, TextStyle baseStyle) {
    final spans = _parseInlineSpans(rawText, baseStyle);
    return RichText(
      text: TextSpan(children: spans),
    );
  }

  List<InlineSpan> _parseInlineSpans(String rawText, TextStyle baseStyle) {
    final spans = <InlineSpan>[];

    // Accurate regex for Markdown inline elements:
    // 1. **bold**
    // 2. `code`
    // 3. *italic* (single asterisk not flanked by asterisks)
    // 4. _italic_ (single underscore not flanked by underscores)
    final regex = RegExp(
        r'(\*\*(?:[^*]|\*[^*])+\*\*|`[^`]+`|(?<!\*)\*[^*]+\*(?!\*)|(?<!_)_[^_]+_(?!_))');

    int start = 0;
    for (final match in regex.allMatches(rawText)) {
      if (match.start > start) {
        spans.add(TextSpan(
          text: rawText.substring(start, match.start),
          style: baseStyle,
        ));
      }

      final textMatch = match.group(0)!;
      if (textMatch.startsWith('**') &&
          textMatch.endsWith('**') &&
          textMatch.length >= 4) {
        final content = textMatch.substring(2, textMatch.length - 2);
        spans.add(TextSpan(
          text: content,
          style: baseStyle.copyWith(fontWeight: FontWeight.bold),
        ));
      } else if (textMatch.startsWith('`') &&
          textMatch.endsWith('`') &&
          textMatch.length >= 2) {
        final content = textMatch.substring(1, textMatch.length - 1);
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
            decoration: BoxDecoration(
              color: Colors.black.withOpacity(0.06),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              content,
              style: baseStyle.copyWith(
                fontFamily: 'monospace',
                fontSize: (baseStyle.fontSize ?? 14) * 0.9,
              ),
            ),
          ),
        ));
      } else if ((textMatch.startsWith('*') && textMatch.endsWith('*')) ||
          (textMatch.startsWith('_') && textMatch.endsWith('_'))) {
        final content = textMatch.substring(1, textMatch.length - 1);
        spans.add(TextSpan(
          text: content,
          style: baseStyle.copyWith(fontStyle: FontStyle.italic),
        ));
      } else {
        spans.add(TextSpan(text: textMatch, style: baseStyle));
      }

      start = match.end;
    }

    if (start < rawText.length) {
      spans.add(TextSpan(
        text: rawText.substring(start),
        style: baseStyle,
      ));
    }

    return spans;
  }
}
