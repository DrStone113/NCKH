"""
Conversation flow — thu thập thông tin từ người dùng trước khi gửi AI.
Xử lý hoàn toàn local, không cần LLM cho các bước hỏi thông tin.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FlowType(str, Enum):
    EXERCISE = "exercise"
    NUTRITION = "nutrition"
    NONE = "none"


@dataclass
class FlowState:
    flow_type: FlowType = FlowType.NONE
    step: int = 0
    collected: dict = field(default_factory=dict)

    def is_active(self) -> bool:
        return self.flow_type != FlowType.NONE

    def is_complete(self) -> bool:
        if self.flow_type == FlowType.EXERCISE:
            return all(k in self.collected for k in ["muscle_group", "duration"])
        if self.flow_type == FlowType.NUTRITION:
            return all(k in self.collected for k in ["meal_type"])
        return False

    def build_enriched_message(self) -> str:
        """Tạo message đầy đủ thông tin để gửi AI."""
        if self.flow_type == FlowType.EXERCISE:
            muscle = self.collected.get("muscle_group", "toàn thân")
            duration = self.collected.get("duration", "30")
            equipment = self.collected.get("equipment", "không có dụng cụ")
            location = self.collected.get("location", "tại nhà")
            level = self.collected.get("level", "trung bình")
            return (
                f"Tạo bài tập {muscle} trong {duration} phút, "
                f"tập {location}, {equipment}, trình độ {level}."
            )
        if self.flow_type == FlowType.NUTRITION:
            meal_type = self.collected.get("meal_type", "bữa trưa")
            goal_cal = self.collected.get("calories", "")
            diet = self.collected.get("diet", "")
            parts = [f"Gợi ý {meal_type} lành mạnh"]
            if goal_cal:
                parts.append(f"khoảng {goal_cal} calo")
            if diet:
                parts.append(diet)
            return ", ".join(parts) + "."
        return ""


# ─── Exercise flow steps ────────────────────────────────────────────────────

_EXERCISE_STEPS = [
    {
        "key": "muscle_group",
        "question": "💪 Bạn muốn tập nhóm cơ nào?",
        "options": ["Toàn thân", "Ngực", "Tay", "Chân", "Lưng", "Vai", "Bụng & Core"],
        "values":  ["toàn thân", "ngực", "tay", "chân", "lưng", "vai", "bụng và core"],
        "parse": lambda t: _match_options(t, {
            r"toàn thân|tất cả|full body": "toàn thân",
            r"ngực|chest": "ngực",
            r"tay|arm|bicep|tricep": "tay",
            r"chân|leg|squat|lunge": "chân",
            r"lưng|back": "lưng",
            r"vai|shoulder": "vai",
            r"bụng|core|ab": "bụng và core",
        }),
    },
    {
        "key": "equipment",
        "question": "🏋️ Bạn có dụng cụ tập không?",
        "options": ["Không có", "Tạ đơn", "Dây kháng lực", "Phòng gym đầy đủ"],
        "values":  ["không có dụng cụ", "tạ tay", "dây kháng lực", "đầy đủ dụng cụ gym"],
        "parse": lambda t: _match_options(t, {
            r"không|none|bodyweight": "không có dụng cụ",
            r"tạ|dumbbell|barbell": "tạ tay",
            r"dây|band|resistance": "dây kháng lực",
            r"gym|phòng gym|đầy đủ": "đầy đủ dụng cụ gym",
        }),
    },
    {
        "key": "duration",
        "question": "⏱ Bạn có bao nhiêu thời gian?",
        "options": ["30 phút", "45 phút", "60 phút"],
        "values":  ["30",      "45",      "60"],
        "parse": lambda t: _extract_number(t, [30, 45, 60]),
    },
]

# ─── Nutrition flow steps ────────────────────────────────────────────────────

_NUTRITION_STEPS = [
    {
        "key": "meal_type",
        "question": "🍽 Đây là bữa ăn nào?",
        "options": ["🌅 Bữa sáng", "☀️ Bữa trưa", "🌙 Bữa tối", "🍎 Bữa phụ"],
        "values":  ["bữa sáng",   "bữa trưa",   "bữa tối",   "bữa phụ"],
        "parse": lambda t: _match_options(t, {
            r"sáng|breakfast|morning": "bữa sáng",
            r"trưa|lunch|noon": "bữa trưa",
            r"tối|dinner|evening": "bữa tối",
            r"phụ|snack|xế": "bữa phụ",
        }),
    },
    {
        "key": "diet",
        "question": "🥦 Bạn có yêu cầu đặc biệt không?",
        "options": ["Không có", "Ít carb", "Nhiều protein", "Chay / Thuần chay"],
        "values":  ["",         "ít carb", "nhiều protein", "ăn chay"],
        "parse": lambda t: _match_options(t, {
            r"không|bình thường|none": "",
            r"ít carb|low carb|keto": "ít carb",
            r"protein|đạm|thịt": "nhiều protein",
            r"chay|vegan|vegetarian": "ăn chay",
        }),
        "optional": True,  # Có thể bỏ qua
    },
]


# ─── Helpers ────────────────────────────────────────────────────────────────

def _match_options(text: str, patterns: dict) -> Optional[str]:
    text = text.lower().strip()
    for pattern, value in patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            return value
    # Không match số thứ tự ở đây, để caller xử lý
    return None


def _extract_number(text: str, valid: list[int]) -> Optional[str]:
    text = text.lower().strip()
    # Match số trực tiếp
    nums = re.findall(r'\d+', text)
    for n in nums:
        n_int = int(n)
        if n_int in valid:
            return str(n_int)
        # Gần nhất
        closest = min(valid, key=lambda x: abs(x - n_int))
        if abs(closest - n_int) <= 10:
            return str(closest)
    # Match từ khóa
    if re.search(r'ngắn|nhanh|ít', text):
        return str(valid[0])
    if re.search(r'dài|nhiều|lâu', text):
        return str(valid[-1])
    return None


def _try_parse_option_index(text: str, count: int) -> Optional[int]:
    """Thử parse số thứ tự từ text (1-based)."""
    text = text.strip()
    # Kiểm tra xem text có phải là số không
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < count:
            return idx
    return None


# ─── Main class ─────────────────────────────────────────────────────────────

class ConversationFlowManager:
    """
    Quản lý conversation flow per session.
    Thread-safe vì mỗi session có state riêng.
    """

    def __init__(self):
        self._states: dict[str, FlowState] = {}

    def get_state(self, session_id: str) -> FlowState:
        return self._states.get(session_id, FlowState())

    def clear_state(self, session_id: str):
        self._states.pop(session_id, None)

    def start_exercise_flow(self, session_id: str) -> dict:
        """Bắt đầu flow thu thập thông tin bài tập."""
        state = FlowState(flow_type=FlowType.EXERCISE, step=0)
        self._states[session_id] = state
        return self._get_step_response(state, _EXERCISE_STEPS)

    def start_nutrition_flow(self, session_id: str) -> dict:
        """Bắt đầu flow thu thập thông tin bữa ăn."""
        state = FlowState(flow_type=FlowType.NUTRITION, step=0)
        self._states[session_id] = state
        return self._get_step_response(state, _NUTRITION_STEPS)

    def process_answer(self, session_id: str, answer: str) -> dict:
        """
        Xử lý câu trả lời của user trong flow.
        Returns:
            {
                "status": "continue" | "complete" | "cancelled",
                "message": str,          # câu hỏi tiếp theo hoặc thông báo
                "options": list[str],    # options cho step tiếp theo
                "enriched_message": str, # chỉ khi status == "complete"
                "suggestions": list[str],
            }
        """
        state = self._states.get(session_id)
        if not state or not state.is_active():
            return {"status": "not_in_flow"}

        steps = _EXERCISE_STEPS if state.flow_type == FlowType.EXERCISE else _NUTRITION_STEPS

        # Kiểm tra cancel
        if re.search(r'\b(thôi|hủy|cancel|bỏ qua|không cần)\b', answer, re.IGNORECASE):
            self.clear_state(session_id)
            return {
                "status": "cancelled",
                "message": "Đã hủy. Bạn muốn làm gì khác không?",
                "options": [],
                "suggestions": ["Tạo bài tập", "Gợi ý bữa ăn", "Tính calo"],
            }

        current_step = steps[state.step]

        # Parse answer
        parsed = None

        # Thử parse theo index (1, 2, 3...)
        idx = _try_parse_option_index(answer, len(current_step["options"]))
        if idx is not None:
            parsed = current_step["values"][idx]
        else:
            # Thử parse theo keyword
            parsed = current_step["parse"](answer)

        # Nếu không parse được và step là optional → bỏ qua
        if parsed is None and current_step.get("optional"):
            parsed = current_step["values"][0]  # default

        if parsed is None:
            # Không hiểu, hỏi lại
            return {
                "status": "continue",
                "message": f"Xin lỗi, tôi chưa hiểu. {current_step['question']}",
                "options": current_step["options"],
                "suggestions": [],
            }

        # Lưu giá trị
        state.collected[current_step["key"]] = parsed
        state.step += 1

        # Kiểm tra complete
        if state.is_complete() or state.step >= len(steps):
            enriched = state.build_enriched_message()
            self.clear_state(session_id)
            return {
                "status": "complete",
                "message": "",  # Không cần message, sẽ gọi LLM trực tiếp
                "options": [],
                "enriched_message": enriched,
                "suggestions": [],
            }

        # Tiếp tục step tiếp theo
        return self._get_step_response(state, steps)

    def _get_step_response(self, state: FlowState, steps: list) -> dict:
        step = steps[state.step]
        total = len(steps)
        progress = f"({state.step + 1}/{total})"

        # Build message với progress
        msg = f"{step['question']} {progress}"

        # Thêm hint về options
        options_text = " | ".join(
            f"{i+1}. {opt}" for i, opt in enumerate(step["options"])
        )

        return {
            "status": "continue",
            "message": msg,
            "options": step["options"],
            "options_text": options_text,
            "suggestions": step["options"],  # Dùng options làm suggestions
        }


# Singleton
flow_manager = ConversationFlowManager()
