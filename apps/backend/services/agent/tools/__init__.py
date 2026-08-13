"""Tool catalog registration for the redesigned chatbot agent."""

from __future__ import annotations

from functools import partial
from typing import Any

from services.agent.rag_service import QUERY_RAG_DESCRIPTOR, RAGService
from services.agent.tool_registry import ToolDescriptor, ToolRegistry
from services.agent.tools import dish, food, tdee, workout
from services.agent.tools.plan_tools import (
    APPEND_PLAN_ITEMS_DESCRIPTOR,
    CREATE_PLAN_DESCRIPTOR,
    append_plan_items,
    create_plan,
)
from services.agent.tools.web_knowledge import (
    SEARCH_MEDICAL_KNOWLEDGE_DESCRIPTOR,
    build_search_tool,
)


def _clone_descriptor(descriptor: ToolDescriptor, **overrides: Any) -> ToolDescriptor:
    return ToolDescriptor(
        name=overrides.get("name", descriptor.name),
        description=overrides.get("description", descriptor.description),
        parameters_schema=overrides.get("parameters_schema", descriptor.parameters_schema),
        side=overrides.get("side", descriptor.side),
        fn=overrides.get("fn", descriptor.fn),
        idempotent=overrides.get("idempotent", descriptor.idempotent),
        timeout_ms=overrides.get("timeout_ms", descriptor.timeout_ms),
    )


def register_server_tools(
    registry: ToolRegistry,
    rag_service: RAGService | None = None,
    db_session: Any | None = None,
    web_service: Any | None = None,
) -> None:
    """Register all server-side tool descriptors."""
    registry.register(dish.TOOL_DESCRIPTOR)
    registry.register(workout.TOOL_DESCRIPTOR)
    registry.register(tdee.TOOL_DESCRIPTOR)
    registry.register(
        _clone_descriptor(
            food.TOOL_DESCRIPTOR,
            fn=partial(food.search_food_nutrition, rag_service=rag_service, db=db_session),
        )
    )

    if db_session is not None:
        registry.register(_clone_descriptor(CREATE_PLAN_DESCRIPTOR, fn=partial(create_plan, db_session)))
        registry.register(_clone_descriptor(APPEND_PLAN_ITEMS_DESCRIPTOR, fn=partial(append_plan_items, db_session)))
    else:
        registry.register(CREATE_PLAN_DESCRIPTOR)
        registry.register(APPEND_PLAN_ITEMS_DESCRIPTOR)

    if rag_service is not None and db_session is not None:
        async def query_rag(query: str, top_k: int = 5):
            return await rag_service.query(query, top_k, db=db_session)

        registry.register(_clone_descriptor(QUERY_RAG_DESCRIPTOR, fn=query_rag))
    else:
        registry.register(QUERY_RAG_DESCRIPTOR)

    # Web knowledge lookup. Registered unconditionally — the providers need no
    # API key — but ingestion only wires up when there is a DB session to write
    # to, so search still works in tests and offline setups.
    if web_service is None:
        from services.agent.web_search import WebKnowledgeService

        web_service = WebKnowledgeService()

    ingest_service = None
    if db_session is not None:
        from services.agent.knowledge_ingest import KnowledgeIngestService

        ingest_service = KnowledgeIngestService(db_session, rag_service)

    registry.register(
        _clone_descriptor(
            SEARCH_MEDICAL_KNOWLEDGE_DESCRIPTOR,
            fn=build_search_tool(web_service, ingest_service),
        )
    )


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_DATE = {"type": "string", "format": "date"}
_REQUEST_ID = {"type": "string", "minLength": 1}


def register_client_tools(registry: ToolRegistry) -> None:
    """Register all 15 Flutter/client-side tool descriptors across 3 domain modules.

    Descriptions are written as *decision rules* ("gọi khi …"), not as labels.
    Small instruction-tuned models pick tools almost entirely from this text,
    so a one-word description like "Ghi cân nặng" leaves them guessing about
    when the tool applies. Every ``request_id`` is documented inline for the
    same reason — a missing one used to surface as ``INVALID_ARGS``.
    """
    client_tools: list[ToolDescriptor] = [
        # Domain 1: Dinh dưỡng (Nutrition)
        ToolDescriptor("get_user_profile", "Đọc hồ sơ người dùng (tuổi, giới tính, chiều cao, cân nặng, mục tiêu, mức vận động). GỌI ĐẦU TIÊN trước mọi lời khuyên cá nhân hóa, tính TDEE hay lập kế hoạch. Không hỏi người dùng những thông tin này — ứng dụng đã lưu sẵn.", _schema({}), "client", idempotent=True),
        ToolDescriptor("get_today_meals", "Đọc các bữa ăn đã ghi trong ngày hôm nay kèm calo và macro. Gọi khi cần biết người dùng đã nạp bao nhiêu, còn dư bao nhiêu, hoặc trước khi gợi ý bữa tiếp theo.", _schema({}), "client", idempotent=True),
        ToolDescriptor("get_meal_log_range", "Đọc nhật ký ăn uống trong một khoảng ngày (định dạng YYYY-MM-DD). Gọi khi người dùng hỏi về tuần này, tháng qua, hoặc khi cần phân tích xu hướng ăn uống nhiều ngày.", _schema({"from_date": _DATE, "to_date": _DATE}, ["from_date", "to_date"]), "client", idempotent=True),
        ToolDescriptor(
            "log_meal",
            "Ghi một bữa ăn vào nhật ký. Gọi ngay khi người dùng kể đã ăn gì (vd 'trưa nay mình ăn phở bò') hoặc khi họ muốn lưu thực đơn gợi ý. request_id là chuỗi ngẫu nhiên duy nhất do bạn tự sinh cho mỗi lần ghi.",
            _schema({
                "meal_type": {
                    "type": "string",
                    "enum": ["breakfast", "lunch", "dinner", "snack"],
                    "description": "breakfast=sáng, lunch=trưa, dinner=tối, snack=bữa phụ"
                },
                "dish_name": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Tên món tiếng Việt, vd 'phở bò tái'"
                },
                "serving_grams": {
                    "type": "number",
                    "description": "Tổng khối lượng món ăn tính bằng gram (nếu có)"
                },
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Tên nguyên liệu"},
                            "serving_grams": {"type": "number", "description": "Khối lượng nguyên liệu (g)"},
                            "calories": {"type": "number", "description": "Lượng calo (kcal)"},
                            "protein": {"type": "number", "description": "Đạm (g)"},
                            "carbs": {"type": "number", "description": "Tinh bột (g)"},
                            "fat": {"type": "number", "description": "Chất béo (g)"}
                        },
                        "required": ["name", "serving_grams", "calories", "protein", "carbs", "fat"],
                        "additionalProperties": False
                    },
                    "description": "Danh sách các nguyên liệu/thành phần dinh dưỡng chi tiết của món ăn (lấy từ kết quả tool suggest_dish hoặc search_food_nutrition)."
                },
                "request_id": _REQUEST_ID
            }, ["meal_type", "dish_name", "request_id"]),
            "client",
            idempotent=False
        ),

        # Domain 2: Thể chất (Physical Fitness)
        ToolDescriptor("get_today_exercises", "Đọc các bài tập đã ghi hôm nay kèm thời lượng và calo đốt. Gọi khi cần đối chiếu calo nạp vào / đốt ra, hoặc trước khi gợi ý buổi tập tiếp theo.", _schema({}), "client", idempotent=True),
        ToolDescriptor("get_exercise_log_range", "Đọc nhật ký tập luyện trong khoảng ngày (YYYY-MM-DD). Gọi khi phân tích tần suất tập, khối lượng tập nhiều ngày, hoặc khi người dùng hỏi 'tuần này mình tập thế nào'.", _schema({"from_date": _DATE, "to_date": _DATE}, ["from_date", "to_date"]), "client", idempotent=True),
        ToolDescriptor("get_weight_history", "Đọc lịch sử cân nặng N ngày gần nhất. BẮT BUỘC gọi khi người dùng nói cân không giảm / không tăng / bị chững, để xem xu hướng thật thay vì đoán.", _schema({"days": {"type": "integer", "minimum": 1, "maximum": 365, "description": "Số ngày cần xem, vd 30 cho một tháng"}}, ["days"]), "client", idempotent=True),
        ToolDescriptor("log_exercise", "Ghi một buổi tập vào nhật ký. Gọi ngay khi người dùng kể vừa tập gì (vd 'sáng nay chạy 30 phút'). request_id là chuỗi ngẫu nhiên duy nhất bạn tự sinh.", _schema({"exercise_name": {"type": "string", "minLength": 1, "description": "Tên bài tập, vd 'chạy bộ', 'squat'"}, "duration_min": {"type": "integer", "minimum": 1, "description": "Thời lượng tính bằng phút"}, "description": {"type": "string", "description": "Mô tả chi tiết hoặc danh sách các động tác trong buổi tập"}, "request_id": _REQUEST_ID}, ["exercise_name", "duration_min", "request_id"]), "client", idempotent=False),
        ToolDescriptor("log_weight", "Ghi số cân nặng mới. Gọi khi người dùng báo cân nặng hiện tại (vd 'sáng nay mình 68kg'). date theo định dạng YYYY-MM-DD, mặc định là hôm nay.", _schema({"value_kg": {"type": "number", "minimum": 30, "maximum": 300}, "date": _DATE, "request_id": _REQUEST_ID}, ["value_kg", "date", "request_id"]), "client", idempotent=False),

        # Domain 3: Sức khỏe tinh thần & Lifestyle (Mental & Lifestyle)
        ToolDescriptor("get_lifestyle_logs", "Đọc chỉ số giấc ngủ, stress, lượng nước và tâm trạng hôm nay. Gọi khi người dùng nhắc tới mệt mỏi, mất ngủ, căng thẳng, hoặc khi phân tích lý do cân nặng chững lại.", _schema({}), "client", idempotent=True),
        ToolDescriptor("log_lifestyle", "Ghi nhận tâm trạng, giấc ngủ, stress hoặc lượng nước. Gọi khi người dùng chia sẻ 'đêm qua ngủ 5 tiếng', 'hôm nay stress quá', 'mình vừa uống 500ml'. type quyết định các trường cần điền: mood→mood_score+mood_label, sleep_stress→sleep_hours+stress_score, water→water_ml.", _schema({"type": {"type": "string", "enum": ["mood", "sleep_stress", "water"]}, "mood_score": {"type": "integer", "minimum": 1, "maximum": 5, "description": "1=rất tệ, 5=rất tốt"}, "mood_label": {"type": "string"}, "sleep_hours": {"type": "number"}, "stress_score": {"type": "integer", "minimum": 1, "maximum": 5, "description": "1=thoải mái, 5=căng thẳng nặng"}, "water_ml": {"type": "number"}, "notes": {"type": "string"}, "request_id": _REQUEST_ID}, ["type", "request_id"]), "client", idempotent=False),
        ToolDescriptor("set_lifestyle_reminder", "Đặt nhắc nhở thói quen (uống nước, đi ngủ, tập luyện). Chỉ gọi khi người dùng thực sự yêu cầu nhắc, đừng tự ý đặt. time theo định dạng HH:MM 24 giờ.", _schema({"title": {"type": "string", "minLength": 1}, "rem_type": {"type": "string", "description": "water | sleep | workout | meal"}, "time": {"type": "string", "description": "HH:MM, vd '21:30'"}, "note": {"type": "string"}, "request_id": _REQUEST_ID}, ["title", "time", "request_id"]), "client", idempotent=False),

        # General & Navigation
        ToolDescriptor("get_active_plan", "Đọc kế hoạch dài hạn đang chạy và tiến độ của nó. Gọi trước khi tạo kế hoạch mới (để không tạo trùng) hoặc khi người dùng hỏi về tiến độ.", _schema({}), "client", idempotent=True),
        ToolDescriptor("mark_plan_item_complete", "Đánh dấu một mục trong kế hoạch là đã hoàn thành. Cần item_id lấy từ get_active_plan.", _schema({"item_id": {"type": "string", "minLength": 1}, "request_id": _REQUEST_ID}, ["item_id", "request_id"]), "client", idempotent=False),
        ToolDescriptor("navigate_to_screen", "Mở một màn hình trong ứng dụng giúp người dùng. Chỉ gọi khi họ muốn đi tới đâu đó ('mở trang dinh dưỡng'), không dùng để trả lời câu hỏi thông tin.", _schema({"screen": {"type": "string", "minLength": 1, "description": "dashboard | nutrition | workout | profile | plan"}, "params": {"type": "object"}, "request_id": _REQUEST_ID}, ["screen", "request_id"]), "client", idempotent=False),
    ]
    for descriptor in client_tools:
        registry.register(descriptor)


# NOTE: these names must match the descriptors registered above / in
# ``services.agent.tools.*``. Previously this map referenced ``dish_composition``
# and ``workout_recommendation``, neither of which exists — the real names are
# ``suggest_dish`` and ``suggest_workout``.
DOMAIN_MODULE_MAP = {
    "nutrition": [
        "get_today_meals", "get_meal_log_range", "log_meal",
        "calculate_tdee", "search_food_nutrition", "suggest_dish"
    ],
    "fitness": [
        "get_today_exercises", "get_exercise_log_range", "log_exercise",
        "log_weight", "get_weight_history", "suggest_workout"
    ],
    "lifestyle": [
        "get_lifestyle_logs", "log_lifestyle", "set_lifestyle_reminder"
    ],
    "general": [
        "get_user_profile", "get_active_plan", "create_plan",
        "append_plan_items", "query_rag", "search_medical_knowledge",
        "navigate_to_screen", "mark_plan_item_complete"
    ]
}


__all__ = ["register_client_tools", "register_server_tools", "DOMAIN_MODULE_MAP"]

