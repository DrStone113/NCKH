"""
Intent classifier — phân loại ý định người dùng để routing thông minh.
Không cần LLM, dùng keyword matching + regex.
"""
import re
from enum import Enum


class Intent(str, Enum):
    GREETING = "greeting"           # Xin chào, hi, hello
    EXERCISE_REQUEST = "exercise"   # Tạo bài tập, gợi ý tập luyện
    NUTRITION_REQUEST = "nutrition" # Gợi ý bữa ăn, thực đơn, món ăn
    HEALTH_QUERY = "health"         # Câu hỏi về sức khỏe, triệu chứng
    PROGRESS_CHECK = "progress"     # Kiểm tra tiến độ, cân nặng
    CALCULATION = "calculation"     # Tính calo, BMI, TDEE
    GENERAL = "general"             # Câu hỏi chung


# Keyword patterns cho từng intent
_PATTERNS: dict[Intent, list[str]] = {
    Intent.GREETING: [
        r'\b(xin chào|chào|hello|hi|hey|alo|helo)\b',
        r'^(chào|hi|hello|hey)[\s!.]*$',
    ],
    # PROGRESS_CHECK phải đứng TRƯỚC EXERCISE_REQUEST để tránh false positive
    Intent.PROGRESS_CHECK: [
        r'\b(tiến độ|tiến trình|kết quả|progress)\b',
        r'\b(cân nặng hiện tại|đã giảm|đã tăng)\b',
        r'\b(hôm nay.*ăn|hôm nay.*tập|đã làm|đã ăn|đã tập)\b',
        r'\b(phân tích.*hôm nay|hôm nay.*phân tích|cho.*lời khuyên|nhận xét.*hôm nay)\b',
        r'hôm nay tôi đã',
        r'\b(báo cáo|tổng kết|review)\b',
    ],
    Intent.EXERCISE_REQUEST: [
        r'\b(tạo.*bài tập|gợi ý.*tập|lịch tập|chương trình tập)\b',
        r'\b(tập luyện|tập thể dục|workout|luyện tập|tập gym|tập thể thao)\b',
        r'\b(cardio|strength|yoga|chạy bộ|hít đất|squat|plank|push.?up)\b',
        r'\b(tập.*cơ|nhóm cơ|ngực|lưng|chân|vai|tay|bụng)\b',
        r'\b(đốt calo|giảm mỡ|tăng cơ|tăng sức mạnh)\b',
        r'\b(bài tập)\b',
    ],
    Intent.NUTRITION_REQUEST: [
        r'\b(bữa ăn|thực đơn|món ăn|ăn gì|dinh dưỡng|nutrition)\b',
        r'\b(bữa sáng|bữa trưa|bữa tối|bữa phụ|snack)\b',
        r'\b(tạo.*thực đơn|gợi ý.*ăn|lên thực đơn|meal plan)\b',
        r'\b(rau|thịt|cá|trứng|sữa|hoa quả|ngũ cốc)\b',
    ],
    Intent.HEALTH_QUERY: [
        r'\b(triệu chứng|đau|mệt|khó chịu|bệnh|sức khỏe)\b',
        r'\b(đau đầu|đau lưng|đau bụng|mệt mỏi|chóng mặt)\b',
        r'\b(huyết áp|tim mạch|tiểu đường|béo phì)\b',
        r'\b(nên.*không|có.*không|có hại|có tốt)\b',
    ],
    Intent.CALCULATION: [
        r'\b(tính|calculate|bmi|tdee|bmr)\b',
        r'\b(tính.*calo|cần.*calo|đốt.*calo|nạp.*calo)\b',
        r'\b(chỉ số|chỉ số cơ thể|body mass)\b',
    ],
}

# Intents cần RAG (tìm kiếm dữ liệu wger)
_NEEDS_RAG = {Intent.EXERCISE_REQUEST, Intent.NUTRITION_REQUEST, Intent.HEALTH_QUERY, Intent.PROGRESS_CHECK}

# Intents không cần gọi LLM (xử lý local)
_LOCAL_RESPONSES: dict[Intent, str] = {
    Intent.GREETING: (
        "Xin chào! 👋 Tôi là trợ lý sức khỏe AI của bạn.\n\n"
        "Tôi có thể giúp bạn:\n"
        "• 🏋️ Tạo bài tập và lịch tập luyện\n"
        "• 🥗 Gợi ý thực đơn và dinh dưỡng\n"
        "• 💪 Tính toán calo, BMI, TDEE\n"
        "• ❓ Tư vấn sức khỏe\n\n"
        "Bạn muốn bắt đầu với điều gì?"
    ),
}

# Suggestions mặc định cho từng intent
_DEFAULT_SUGGESTIONS: dict[Intent, list[str]] = {
    Intent.GREETING: [
        "Tạo bài tập hôm nay",
        "Gợi ý bữa sáng",
        "Tính calo của tôi",
        "Tư vấn giảm cân",
    ],
    Intent.EXERCISE_REQUEST: [
        "Tập toàn thân 30 phút",
        "Bài tập ngực",
        "Tập chân không dụng cụ",
        "Lịch tập cả tuần",
    ],
    Intent.NUTRITION_REQUEST: [
        "Thực đơn giảm cân",
        "Bữa ăn tăng cơ",
        "Tính calo bữa ăn",
        "Thực đơn 7 ngày",
    ],
    Intent.HEALTH_QUERY: [
        "Tôi nên tập gì?",
        "Chế độ ăn phù hợp",
        "Cách cải thiện sức khỏe",
    ],
    Intent.PROGRESS_CHECK: [
        "Gợi ý bữa ăn còn lại hôm nay",
        "Tôi nên tập thêm gì không?",
        "Tổng kết tuần này",
        "Điều chỉnh mục tiêu",
    ],
    Intent.CALCULATION: [
        "Tính BMI của tôi",
        "Tôi cần bao nhiêu calo?",
        "Calo trong bữa ăn",
    ],
    Intent.GENERAL: [
        "Tạo bài tập",
        "Gợi ý bữa ăn",
        "Tư vấn sức khỏe",
    ],
}


class IntentClassifier:
    def classify(self, message: str) -> Intent:
        """Phân loại intent từ message. Nhanh, không cần LLM."""
        text = message.lower().strip()

        for intent, patterns in _PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return intent

        return Intent.GENERAL

    def needs_rag(self, intent: Intent) -> bool:
        """Có cần tìm kiếm RAG không?"""
        return intent in _NEEDS_RAG

    def needs_llm(self, intent: Intent) -> bool:
        """Có cần gọi LLM không?"""
        return intent not in _LOCAL_RESPONSES

    def get_local_response(self, intent: Intent) -> str | None:
        """Lấy response local nếu không cần LLM."""
        return _LOCAL_RESPONSES.get(intent)

    def get_default_suggestions(self, intent: Intent) -> list[str]:
        """Lấy suggestions mặc định cho intent."""
        return _DEFAULT_SUGGESTIONS.get(intent, _DEFAULT_SUGGESTIONS[Intent.GENERAL])


# Singleton
intent_classifier = IntentClassifier()
