"""
actions.py — Custom Actions cho Health Advice Chatbot (Rasa 3.x).

Gồm 4 actions:
  - ActionEmergencyAlert  : Phát hiện từ khóa khẩn cấp, trả về số cấp cứu.
  - ActionHealthAdvice    : Tìm kiếm ngữ nghĩa trong Knowledge Base.
  - ActionNutritionInfo   : Tra cứu thông tin dinh dưỡng (API + fallback DB).
  - ActionExerciseInfo    : Tra cứu thông tin bài tập (API + fallback DB).

Mọi phản hồi liên quan sức khỏe đều kèm DISCLAIMER bắt buộc.
"""

import logging
import os
import requests
from typing import Any, Dict, List, Optional, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher

from .db_client import DBClient
from .embedding_model import EmbeddingModel
from .semantic_retriever import SemanticRetriever

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

DISCLAIMER = "\n\n⚠️ Thông tin chỉ mang tính chất tham khảo, hãy tham vấn bác sĩ chuyên khoa."

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "knowledge_base", "health_kb.db")

EMERGENCY_KEYWORDS_VI = [
    "đau ngực", "khó thở", "mất ý thức", "ngất", "đột quỵ",
    "nhồi máu", "co giật", "chảy máu nhiều", "tai nạn",
]

EMERGENCY_KEYWORDS_EN = [
    "chest pain", "shortness of breath", "unconscious",
    "stroke", "heart attack", "seizure", "severe bleeding",
]

EMERGENCY_KEYWORDS = EMERGENCY_KEYWORDS_VI + EMERGENCY_KEYWORDS_EN

# ---------------------------------------------------------------------------
# Lazy initialization — module-level singletons
# ---------------------------------------------------------------------------

_db_client: Optional[DBClient] = None
_embed_model: Optional[EmbeddingModel] = None


def _get_db() -> DBClient:
    """Trả về DBClient singleton, khởi tạo nếu chưa có."""
    global _db_client
    if _db_client is None:
        logger.info("Initializing DBClient with path: %s", DB_PATH)
        _db_client = DBClient(DB_PATH)
        _db_client.init_db()
    return _db_client


def _get_embed_model() -> EmbeddingModel:
    """Trả về EmbeddingModel singleton, khởi tạo nếu chưa có."""
    global _embed_model
    if _embed_model is None:
        logger.info("Initializing EmbeddingModel...")
        _embed_model = EmbeddingModel()
    return _embed_model


# ---------------------------------------------------------------------------
# ActionEmergencyAlert
# ---------------------------------------------------------------------------


class ActionEmergencyAlert(Action):
    """Phát hiện triệu chứng khẩn cấp và trả về số điện thoại cấp cứu."""

    def name(self) -> Text:
        return "action_emergency_alert"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message: str = tracker.latest_message.get("text", "") or ""
        message_lower = user_message.lower()

        detected_keywords = [kw for kw in EMERGENCY_KEYWORDS if kw in message_lower]

        if detected_keywords:
            response = (
                "🚨 KHẨN CẤP! Gọi ngay 115 (cấp cứu) hoặc 113 (cảnh sát)!\n\n"
                "Vui lòng gọi ngay:\n"
                "• 115 — Cấp cứu y tế\n"
                "• 113 — Cảnh sát / Hỗ trợ khẩn cấp\n\n"
                f"Triệu chứng phát hiện: {', '.join(detected_keywords)}\n\n"
                "Trong khi chờ cấp cứu:\n"
                "• Giữ bình tĩnh, không di chuyển nạn nhân nếu không cần thiết\n"
                "• Đảm bảo đường thở thông thoáng\n"
                "• Thông báo địa chỉ chính xác cho nhân viên cấp cứu"
            )
        else:
            response = (
                "🚨 Nếu đây là tình huống khẩn cấp, gọi ngay 115 (cấp cứu) hoặc 113!\n\n"
                "• 115 — Cấp cứu y tế\n"
                "• 113 — Cảnh sát\n"
                "• 114 — Cứu hỏa"
            )

        dispatcher.utter_message(text=response)
        return []


# ---------------------------------------------------------------------------
# ActionHealthAdvice
# ---------------------------------------------------------------------------


class ActionHealthAdvice(Action):
    """Tìm kiếm ngữ nghĩa trong Knowledge Base và trả về tư vấn sức khỏe."""

    def name(self) -> Text:
        return "action_health_advice"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        user_message: str = tracker.latest_message.get("text", "") or ""
        logger.info("ActionHealthAdvice triggered. Query: %s", user_message[:100])

        try:
            db = _get_db()
            embed_model = _get_embed_model()
            retriever = SemanticRetriever(db, embed_model)

            result = retriever.retrieve(user_message)
            answer = result.get("answer")
            similarity = result.get("similarity_score", 0.0)

            logger.debug("Retrieval: similarity=%.4f, has_answer=%s", similarity, answer is not None)

            if answer is not None:
                response = answer + DISCLAIMER
            else:
                response = (
                    "Tôi chưa tìm thấy thông tin phù hợp. "
                    "Vui lòng tham vấn bác sĩ chuyên khoa."
                    + DISCLAIMER
                )

        except Exception as exc:
            logger.error("ActionHealthAdvice failed: %s", exc, exc_info=True)
            response = (
                "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn. "
                "Vui lòng thử lại sau hoặc tham vấn bác sĩ chuyên khoa."
                + DISCLAIMER
            )

        dispatcher.utter_message(text=response)
        return []


# ---------------------------------------------------------------------------
# ActionNutritionInfo
# ---------------------------------------------------------------------------


class ActionNutritionInfo(Action):
    """Tra cứu thông tin dinh dưỡng qua Nutritionix API hoặc fallback DB."""

    def name(self) -> Text:
        return "action_nutrition_info"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        food_item: str = (
            next(tracker.get_latest_entity_values("food_item"), None)
            or tracker.latest_message.get("text", "")
            or ""
        ).strip()

        logger.info("ActionNutritionInfo triggered. food_item='%s'", food_item)

        if not food_item:
            dispatcher.utter_message(
                text="Vui lòng cho tôi biết tên thực phẩm bạn muốn tra cứu." + DISCLAIMER
            )
            return []

        response = self._try_nutritionix_api(food_item) or self._fallback_db_nutrition(food_item)
        dispatcher.utter_message(text=response)
        return []

    def _try_nutritionix_api(self, food_item: str) -> Optional[str]:
        app_id = os.environ.get("NUTRITIONIX_APP_ID")
        api_key = os.environ.get("NUTRITIONIX_API_KEY")
        if not app_id or not api_key:
            return None
        try:
            resp = requests.post(
                "https://trackapi.nutritionix.com/v2/natural/nutrients",
                json={"query": food_item},
                headers={"x-app-id": app_id, "x-app-key": api_key, "Content-Type": "application/json"},
                timeout=5,
            )
            resp.raise_for_status()
            foods = resp.json().get("foods", [])
            if not foods:
                return None
            f = foods[0]
            return (
                f"🥗 {f.get('food_name', food_item).title()} ({f.get('serving_qty', 1)} {f.get('serving_unit', 'phần')})\n\n"
                f"• Năng lượng: {f.get('nf_calories', 'N/A')} kcal\n"
                f"• Protein: {f.get('nf_protein', 'N/A')} g\n"
                f"• Carbohydrate: {f.get('nf_total_carbohydrate', 'N/A')} g\n"
                f"• Chất béo: {f.get('nf_total_fat', 'N/A')} g\n"
                f"• Chất xơ: {f.get('nf_dietary_fiber', 'N/A')} g\n"
                f"\n(Nguồn: Nutritionix)" + DISCLAIMER
            )
        except Exception as exc:
            logger.warning("Nutritionix API failed for '%s': %s", food_item, exc)
            return None

    def _fallback_db_nutrition(self, food_item: str) -> str:
        try:
            results = _get_db().search_nutrition(food_item)
            if not results:
                return (
                    f"Không tìm thấy thông tin dinh dưỡng cho '{food_item}'. "
                    "Vui lòng thử lại với tên khác." + DISCLAIMER
                )
            f = results[0]
            response = (
                f"🥗 {f.get('description', food_item)}\n\n"
                f"• Năng lượng: {f.get('kilocalories', 'N/A')} kcal\n"
                f"• Protein: {f.get('protein_g', 'N/A')} g\n"
                f"• Carbohydrate: {f.get('carbohydrate_g', 'N/A')} g\n"
                f"• Chất béo: {f.get('fat_total_g', 'N/A')} g\n"
                f"• Chất xơ: {f.get('fiber_g', 'N/A')} g\n"
                f"\n(Nguồn: USDA)" + DISCLAIMER
            )
            if len(results) > 1:
                response += f"\n\n💡 Tìm thấy {len(results)} kết quả. Hiển thị kết quả đầu tiên."
            return response
        except Exception as exc:
            logger.error("DB fallback nutrition failed: %s", exc, exc_info=True)
            return "Xin lỗi, đã xảy ra lỗi khi tra cứu dinh dưỡng. Vui lòng thử lại." + DISCLAIMER


# ---------------------------------------------------------------------------
# ActionExerciseInfo
# ---------------------------------------------------------------------------


class ActionExerciseInfo(Action):
    """Tra cứu thông tin bài tập qua WGER API hoặc fallback DB."""

    def name(self) -> Text:
        return "action_exercise_info"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:
        exercise_type: str = (
            next(tracker.get_latest_entity_values("exercise_type"), None)
            or tracker.latest_message.get("text", "")
            or ""
        ).strip()

        logger.info("ActionExerciseInfo triggered. exercise_type='%s'", exercise_type)

        if not exercise_type:
            dispatcher.utter_message(
                text="Vui lòng cho tôi biết loại bài tập bạn muốn tra cứu." + DISCLAIMER
            )
            return []

        response = self._try_wger_api(exercise_type) or self._fallback_db_exercises(exercise_type)
        dispatcher.utter_message(text=response)
        return []

    def _try_wger_api(self, exercise_type: str) -> Optional[str]:
        wger_url = os.environ.get("WGER_API_URL", "https://wger.de/api/v2")
        try:
            resp = requests.get(
                f"{wger_url}/exercise/search/",
                params={"term": exercise_type, "language": "english", "format": "json"},
                timeout=5,
            )
            resp.raise_for_status()
            suggestions = resp.json().get("suggestions", [])
            if not suggestions:
                return None
            first = suggestions[0]
            name = first.get("value", exercise_type)
            category = first.get("data", {}).get("category", "N/A")
            return (
                f"🏋️ {name}\n\n• Danh mục: {category}\n\n(Nguồn: WGER)" + DISCLAIMER
            )
        except Exception as exc:
            logger.warning("WGER API failed for '%s': %s", exercise_type, exc)
            return None

    def _fallback_db_exercises(self, exercise_type: str) -> str:
        try:
            results = _get_db().search_exercises(exercise_type)
            if not results:
                return (
                    f"Không tìm thấy thông tin về bài tập '{exercise_type}'. "
                    "Vui lòng thử lại với tên khác." + DISCLAIMER
                )
            e = results[0]
            desc = e.get("description") or ""
            response = (
                f"🏋️ {e.get('name', exercise_type)}\n\n"
                f"• Danh mục: {e.get('category') or 'N/A'}\n"
                f"• Nhóm cơ: {e.get('muscle_group') or 'N/A'}\n"
                f"• Thiết bị: {e.get('equipment') or 'N/A'}\n"
                f"• Độ khó: {e.get('difficulty') or 'N/A'}\n"
            )
            if desc:
                response += f"\n📝 {desc[:200]}{'...' if len(desc) > 200 else ''}\n"
            response += "\n(Nguồn: Gym Exercises Dataset)"
            if len(results) > 1:
                response += f"\n\n💡 Tìm thấy {len(results)} kết quả. Hiển thị kết quả đầu tiên."
            response += DISCLAIMER
            return response
        except Exception as exc:
            logger.error("DB fallback exercises failed: %s", exc, exc_info=True)
            return "Xin lỗi, đã xảy ra lỗi khi tra cứu bài tập. Vui lòng thử lại." + DISCLAIMER
