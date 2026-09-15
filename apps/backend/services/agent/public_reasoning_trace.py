"""Safe, user-facing trace of how a chat request was handled.

This module deliberately has no input path from an LLM response.  A public
trace is assembled only from allowlisted application events; it is not a
sanitised version of a model's chain of thought, tool payload, prompt, or
debug output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Final, Iterable
from uuid import uuid4


PUBLIC_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "PROFILE_CONTEXT_USED",
        "TODAY_NUTRITION_CHECKED",
        "DIETARY_CONSTRAINTS_CHECKED",
        "TRAINING_HISTORY_CHECKED",
        "BODY_PROGRESS_CHECKED",
        "LIFESTYLE_LOGS_CHECKED",
        "FOOD_CATALOG_SEARCHED",
        "NUTRITION_DATA_SEARCHED",
        "EXTERNAL_RECIPE_SEARCHED",
        "WORKOUT_CATALOG_SEARCHED",
        "RECOMMENDATION_SELECTED",
        "RECOMMENDATION_NUTRITION_FIT",
        "RECOMMENDATION_PREFERENCE_FIT",
        "RECOMMENDATION_DIVERSITY_APPLIED",
        "RECOMMENDATION_PORTION_ADAPTED",
        "RECOMMENDATION_STAGING_SOURCE",
        "CALCULATION_COMPLETED",
        "CONFIRMATION_RECEIVED",
        "PERSISTENCE_IN_PROGRESS",
        "PERSISTENCE_CONFIRMED",
        "CLARIFICATION_REQUIRED",
        "SAFETY_CHECK_APPLIED",
        "ACTIVE_PLAN_READ",
        "PLAN_VALIDATED",
        "PLAN_REVISION_CREATED",
        "WEEKLY_SCHEDULE_CHECKED",
        "WEEKLY_SESSIONS_SCHEDULED",
        "PLAN_VERSION_CONFIRMED",
    }
)

_PUBLIC_COPY: Final[dict[str, tuple[str, str]]] = {
    "PROFILE_CONTEXT_USED": (
        "Đã kiểm tra thông tin liên quan",
        "Mình dùng các thông tin hồ sơ đã xác nhận để trả lời phù hợp hơn.",
    ),
    "TODAY_NUTRITION_CHECKED": (
        "Đã đối chiếu nhật ký hôm nay",
        "Mình kiểm tra dữ liệu đã ghi để tránh gợi ý trùng lặp.",
    ),
    "DIETARY_CONSTRAINTS_CHECKED": (
        "Đã kiểm tra giới hạn ăn uống",
        "Các hạn chế đã xác nhận được đưa vào khi chọn gợi ý.",
    ),
    "TRAINING_HISTORY_CHECKED": (
        "Đã kiểm tra lịch sử tập luyện",
        "Mình đối chiếu mức độ và lịch tập đã có trước khi đề xuất.",
    ),
    "BODY_PROGRESS_CHECKED": (
        "Đã xem dữ liệu cân nặng",
        "Mình dùng các số đo đã ghi để trả lời đúng phạm vi bạn hỏi.",
    ),
    "LIFESTYLE_LOGS_CHECKED": (
        "Đã xem nhật ký lối sống",
        "Mình đối chiếu các ghi nhận như giấc ngủ, mức căng thẳng và lượng nước.",
    ),
    "FOOD_CATALOG_SEARCHED": (
        "Đã tìm trong danh mục món ăn",
        "Mình chỉ dùng các lựa chọn có trong dữ liệu ứng dụng.",
    ),
    "NUTRITION_DATA_SEARCHED": (
        "Đã tra thông tin dinh dưỡng",
        "Mình dùng số liệu thực phẩm có trong dữ liệu của ứng dụng.",
    ),
    "EXTERNAL_RECIPE_SEARCHED": (
        "Đã tìm nguồn công thức ngoài",
        "Mình đã tra nguồn được phép và giữ nguyên nhãn xác minh của kết quả.",
    ),
    "WORKOUT_CATALOG_SEARCHED": (
        "Đã tìm trong thư viện bài tập",
        "Mình chỉ dùng các bài tập có trong dữ liệu ứng dụng.",
    ),
    "RECOMMENDATION_SELECTED": (
        "Đã chọn gợi ý phù hợp",
        "Gợi ý được chọn dựa trên các dữ liệu đã kiểm tra ở trên.",
    ),
    "RECOMMENDATION_NUTRITION_FIT": (
        "Phù hợp mục tiêu dinh dưỡng còn lại",
        "Gợi ý này được đối chiếu với phần dinh dưỡng còn lại trong ngày.",
    ),
    "RECOMMENDATION_PREFERENCE_FIT": (
        "Phù hợp khẩu vị đã xác nhận",
        "Mình dùng phản hồi hoặc sở thích bạn đã xác nhận, sau các kiểm tra an toàn.",
    ),
    "RECOMMENDATION_DIVERSITY_APPLIED": (
        "Đã cân nhắc sự đa dạng",
        "Mình tránh lặp lại món hoặc nguồn đạm vừa xuất hiện khi có lựa chọn phù hợp.",
    ),
    "RECOMMENDATION_PORTION_ADAPTED": (
        "Có thể điều chỉnh khẩu phần",
        "Khẩu phần được tính lại từ nguyên liệu chuẩn trong giới hạn công thức phù hợp.",
    ),
    "RECOMMENDATION_STAGING_SOURCE": (
        "Nguồn công thức đang được đánh giá",
        "Công thức này là dữ liệu thử nghiệm; dinh dưỡng vẫn được tính từ dữ liệu chuẩn.",
    ),
    "CALCULATION_COMPLETED": (
        "Đã hoàn tất tính toán",
        "Kết quả được tính từ các thông tin đã xác nhận.",
    ),
    "CONFIRMATION_RECEIVED": (
        "Đã nhận xác nhận của bạn",
        "Mình tiếp tục với đúng lựa chọn bạn vừa xác nhận.",
    ),
    "PERSISTENCE_IN_PROGRESS": (
        "Đang lưu thay đổi",
        "Mình đang ghi nhận thông tin vào hồ sơ hoặc nhật ký của bạn.",
    ),
    "PERSISTENCE_CONFIRMED": (
        "Đã lưu thay đổi",
        "Thông tin đã được hệ thống xác nhận là đã lưu.",
    ),
    "CLARIFICATION_REQUIRED": (
        "Cần làm rõ thêm",
        "Mình cần thêm một thông tin để đưa ra gợi ý an toàn và phù hợp.",
    ),
    "SAFETY_CHECK_APPLIED": (
        "Đã áp dụng kiểm tra an toàn",
        "Mình đã cân nhắc các giới hạn sức khỏe đã được xác nhận.",
    ),
    "ACTIVE_PLAN_READ": (
        "Đã đọc kế hoạch hiện tại",
        "Mình dùng đúng phiên bản kế hoạch đang hoạt động, không tạo lại kế hoạch mới.",
    ),
    "PLAN_VALIDATED": (
        "Đã kiểm tra toàn bộ kế hoạch",
        "Các giới hạn và tham chiếu có cấu trúc đã được kiểm tra trước khi hiển thị.",
    ),
    "PLAN_REVISION_CREATED": (
        "Đã tạo bản chỉnh sửa",
        "Thay đổi được tạo thành một phiên bản mới để giữ lại lịch sử bản cũ.",
    ),
    "WEEKLY_SCHEDULE_CHECKED": (
        "Đã kiểm tra lịch tuần",
        "Ngày rảnh, ngày không thể tập và thời lượng được kiểm tra trước khi lên lịch.",
    ),
    "WEEKLY_SESSIONS_SCHEDULED": (
        "Đã lập lịch các buổi tập",
        "Mỗi buổi trong lịch chỉ dùng một phiên E4 hợp lệ; lịch dự kiến chưa phải lịch sử đã tập.",
    ),
    "PLAN_VERSION_CONFIRMED": (
        "Đã xác nhận phiên bản kế hoạch",
        "Phiên bản hiển thị được giữ nguyên khi chuyển sang bước lưu hoặc kích hoạt.",
    ),
}

_WRITE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "log_meal",
        "log_exercise",
        "log_weight",
        "log_lifestyle",
        "set_lifestyle_reminder",
        "update_nutrition_profile",
        "update_workout_profile",
        "create_plan",
        "create_long_term_plan",
        "append_plan_items",
        "mark_plan_item_complete",
        "save_workout_plan",
        "log_workout_result",
        "save_plan",
        "set_plan_status",
    }
)

_READ_EVENT_BY_TOOL: Final[dict[str, tuple[str, ...]]] = {
    "get_user_profile": ("PROFILE_CONTEXT_USED",),
    "get_today_meals": ("TODAY_NUTRITION_CHECKED",),
    "get_meal_log_range": ("TODAY_NUTRITION_CHECKED",),
    "search_food_nutrition": ("NUTRITION_DATA_SEARCHED",),
    "search_dish_catalog": ("FOOD_CATALOG_SEARCHED",),
    "search_recipe_web": ("EXTERNAL_RECIPE_SEARCHED",),
    "suggest_dish": ("FOOD_CATALOG_SEARCHED", "RECOMMENDATION_SELECTED"),
    "get_today_exercises": ("TRAINING_HISTORY_CHECKED",),
    "get_exercise_log_range": ("TRAINING_HISTORY_CHECKED",),
    "get_weight_history": ("BODY_PROGRESS_CHECKED",),
    "get_lifestyle_logs": ("LIFESTYLE_LOGS_CHECKED",),
    "suggest_workout": (
        "TRAINING_HISTORY_CHECKED",
        "SAFETY_CHECK_APPLIED",
        "WORKOUT_CATALOG_SEARCHED",
        "RECOMMENDATION_SELECTED",
    ),
    "build_personalized_workout": (
        "TRAINING_HISTORY_CHECKED",
        "SAFETY_CHECK_APPLIED",
        "WORKOUT_CATALOG_SEARCHED",
        "RECOMMENDATION_SELECTED",
    ),
    "get_workout_substitutions": (
        "SAFETY_CHECK_APPLIED",
        "WORKOUT_CATALOG_SEARCHED",
        "RECOMMENDATION_SELECTED",
    ),
    "calculate_tdee": ("CALCULATION_COMPLETED",),
    "build_nutrition_plan": (
        "DIETARY_CONSTRAINTS_CHECKED",
        "FOOD_CATALOG_SEARCHED",
        "CALCULATION_COMPLETED",
        "PLAN_VALIDATED",
    ),
    "build_workout_schedule": (
        "TRAINING_HISTORY_CHECKED",
        "SAFETY_CHECK_APPLIED",
        "WORKOUT_CATALOG_SEARCHED",
        "WEEKLY_SCHEDULE_CHECKED",
        "WEEKLY_SESSIONS_SCHEDULED",
        "PLAN_VALIDATED",
    ),
    "get_plan": ("ACTIVE_PLAN_READ",),
    "get_active_plan_v2": ("ACTIVE_PLAN_READ",),
    "revise_plan": ("PLAN_REVISION_CREATED", "PLAN_VALIDATED"),
    "save_plan": ("PLAN_VERSION_CONFIRMED",),
}


@dataclass(frozen=True, slots=True)
class PublicTraceStep:
    public_event_type: str
    title: str
    summary: str
    order: int
    timestamp: str
    fact_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "public_event_type": self.public_event_type,
            "title": self.title,
            "summary": self.summary,
            "timestamp": self.timestamp,
            "order": self.order,
        }
        if self.fact_refs:
            payload["fact_refs"] = list(self.fact_refs)
        return payload


@dataclass(slots=True)
class PublicReasoningTrace:
    """Bounded allowlist-only trace safe to send to the user interface."""

    trace_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "IN_PROGRESS"
    steps: list[PublicTraceStep] = field(default_factory=list)
    _seen_events: set[str] = field(default_factory=set, repr=False)

    def add(self, public_event_type: str) -> bool:
        """Add a known public event, dropping unknown and duplicate events.

        There is intentionally no text parameter.  This prevents callers from
        accidentally passing LLM output, a tool argument, or a debug message
        into the public data model.
        """

        if (
            public_event_type not in PUBLIC_EVENT_TYPES
            or public_event_type in self._seen_events
            or len(self.steps) >= 6
        ):
            return False
        title, summary = _PUBLIC_COPY[public_event_type]
        self.steps.append(
            PublicTraceStep(
                public_event_type=public_event_type,
                title=title,
                summary=summary,
                order=len(self.steps) + 1,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        self._seen_events.add(public_event_type)
        return True

    def mark_completed(self) -> None:
        self.status = "COMPLETED"

    def mark_clarification_required(self) -> None:
        self.add("CLARIFICATION_REQUIRED")
        self.status = "CLARIFICATION_REQUIRED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "status": self.status,
            "steps": [step.to_dict() for step in self.steps],
        }


def record_tool_started(trace: PublicReasoningTrace, tool_name: str) -> None:
    """Record only the safe persistence state for a known write action."""

    if tool_name in _WRITE_TOOLS:
        trace.add("PERSISTENCE_IN_PROGRESS")


def record_tool_result(
    trace: PublicReasoningTrace, tool_name: str, *, ok: bool
) -> None:
    """Translate a trusted dispatcher outcome into fixed public events."""

    if not ok:
        trace.mark_clarification_required()
        return
    for public_event_type in _READ_EVENT_BY_TOOL.get(tool_name, ()):
        trace.add(public_event_type)
    if tool_name in _WRITE_TOOLS:
        trace.add("PERSISTENCE_CONFIRMED")


def record_recommendation_reason_codes(
    trace: PublicReasoningTrace, reason_codes: Iterable[str]
) -> None:
    """Translate N3.2 structured reason codes into allowlisted public copy.

    Scores, weights, candidate-set details and private profile attributes are
    intentionally not accepted by this function.
    """

    mapping = {
        "NUTRITION_REMAINING_FIT": "RECOMMENDATION_NUTRITION_FIT",
        "CONFIRMED_PREFERENCE_MATCH": "RECOMMENDATION_PREFERENCE_FIT",
        "INFERRED_PREFERENCE_MATCH": "RECOMMENDATION_PREFERENCE_FIT",
        "DIVERSITY_PROTEIN_ROTATION": "RECOMMENDATION_DIVERSITY_APPLIED",
        "DIVERSITY_DISH_ROTATION": "RECOMMENDATION_DIVERSITY_APPLIED",
        "PORTION_ADAPTABLE": "RECOMMENDATION_PORTION_ADAPTED",
        "STAGING_SOURCE": "RECOMMENDATION_STAGING_SOURCE",
        "RUNTIME_EXTERNAL_SOURCE": "RECOMMENDATION_STAGING_SOURCE",
    }
    for code in reason_codes:
        event = mapping.get(str(code))
        if event:
            trace.add(event)


def record_initial_context(trace: PublicReasoningTrace, user_context: Any) -> None:
    """Expose only that confirmed context was used, never its values."""

    if isinstance(user_context, dict) and user_context:
        trace.add("PROFILE_CONTEXT_USED")
        restrictions = user_context.get("dietary_restrictions") or user_context.get(
            "dietaryRestrictions"
        )
        if restrictions:
            trace.add("DIETARY_CONSTRAINTS_CHECKED")


__all__ = [
    "PUBLIC_EVENT_TYPES",
    "PublicReasoningTrace",
    "PublicTraceStep",
    "record_initial_context",
    "record_recommendation_reason_codes",
    "record_tool_result",
    "record_tool_started",
]
