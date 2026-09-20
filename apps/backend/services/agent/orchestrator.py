"""Agent orchestrator implementing the bounded ReAct loop.

v2 changes
----------
- **Per-turn routing** (:mod:`services.agent.turn_router`): chit-chat skips the
  tool catalog entirely and runs on the light model; complex analysis is
  escalated to the heavy model. Previously every turn paid the same price.
- **Live tool catalog in the prompt** so the model cannot invent tool names.
- **Readable tool errors.** The loop used to hand the model raw
  ``{"ok": false, "error": "INVALID_ARGS"}``, which small models answer with
  "hệ thống đang lỗi". Errors are now translated into an instruction telling
  the model what to do next, and a failed tool is retried once.
- **Memory consolidation actually runs.** ``updateRollingSummary`` existed but
  was never called from production code, so the bot never built long-term
  memory. It now fires as a background task after each completed turn.
- **Profile capture.** ``get_user_profile`` results are threaded back into the
  system prompt for the remainder of the turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from typing import Any

from config import settings
from services.agent.llm_client import GarbledOutputError, LLMUnavailableError, ToolCall
from services.agent.system_prompt import buildSystemPrompt
from services.agent.tool_dispatcher import ToolResult
from services.agent.turn_router import COMPLEX, TurnPlan, classify_turn
from services.agent.context_trace import ContextTraceRecorder
from services.agent.context_planner import ContextPlanner
from services.agent.context_planner.validation.collector import get_natural_collector
from services.agent.context_planner.validation.token_measurement import TokenCounter, measure_turn_tokens
from services.agent.cost_governor import limits_for_turn
from services.agent.answer_validators import validate_answer
from services.agent.inference_policy_v2 import (
    DiagonalLinUCBShadow,
    InferenceRoute,
    decide_inference,
)
from services.agent.public_reasoning_trace import (
    PublicReasoningTrace,
    record_initial_context,
    record_tool_result,
    record_tool_started,
)
from services.agent.debug_trace import (
    DebugTraceBuilder,
    classify_provider_token,
    elapsed_ms,
)
from services.agent.pending_user_action import PendingActionResolution, PendingUserAction, PendingUserActionStore, pending_user_actions
from services.agent.scope_guard import (
    SCOPE_GUARD_HISTORY_MARKER,
    SCOPE_GUARD_HISTORY_MARKERS,
    SCOPE_GUARD_MIXED_HISTORY_MARKER,
    ScopeGuard,
)

logger = logging.getLogger(__name__)
_shadow_context_planner = ContextPlanner()
_shadow_inference_bandit = DiagonalLinUCBShadow()


# Guidance handed to the model when a tool call fails, keyed by the stable
# error codes from ``ToolDispatcher``. Without this the model sees an opaque
# code and falls back on "hệ thống đang lỗi", which is exactly the behaviour
_ERROR_GUIDANCE: dict[str, str] = {
    "NO_DISH_FOUND": (
        "Không tìm thấy món ăn nào trong cơ sở dữ liệu phù hợp với yêu cầu này. "
        "Nếu người dùng đã nêu tên/từ khóa món cụ thể, trước hết dùng search_dish_catalog để quét toàn bộ catalog live. "
        "Chỉ khi matched_count=0 và tool search_recipe_web có sẵn mới gọi tool web đúng một lần. "
        "Trình bày nguyên liệu, tóm tắt cách làm và nguồn từ kết quả. Chỉ dùng dinh dưỡng khi kết quả là VERIFIED_SHADOW; "
        "với REFERENCE_ONLY phải nói rõ nguyên liệu chưa được quy đổi/đối chiếu đầy đủ và không tự bịa calo. "
        "Nếu tìm web cũng không có kết quả thì hãy đề xuất họ đổi từ khóa."
    ),
    "NO_WORKOUT_FOUND": (
        "Không tìm thấy bài tập phù hợp trong thư viện ứng dụng. "
        "Nếu người dùng hỏi về tên bài hoặc dữ liệu thư viện, dùng search_exercise_catalog để kiểm tra toàn catalog. "
        "Có thể giải thích bài nào tồn tại, nhưng không biến kết quả tra cứu thành khuyến nghị khi nó không qua cổng an toàn."
    ),
    "NO_FOOD_FOUND": (
        "Không tìm thấy thực phẩm này trong cơ sở dữ liệu dinh dưỡng. "
        "Hãy thông báo rõ ràng cho người dùng biết là chưa có dữ liệu dinh dưỡng cho món/nguyên liệu này."
    ),
    "UNKNOWN_TOOL": (
        "Tool này không tồn tại trong danh sách. Chỉ sử dụng các tool thực tế đã được cung cấp."
    ),
    "INVALID_ARGS": (
        "Tham số sai định dạng. Đọc lại schema của tool và gọi lại đúng một lần với tham số hợp lệ."
    ),
    "TIMEOUT": (
        "Không thể tải dữ liệu do quá thời gian chờ. Hãy thông báo rõ ràng là chưa lấy được thông tin này, "
        "tuyệt đối không tự suy diễn số liệu."
    ),
    "DISCONNECTED": (
        "Ứng dụng tạm thời không phản hồi. Hãy thông báo chưa lấy được dữ liệu này."
    ),
    "TOOL_INTERNAL_ERROR": (
        "Công cụ gặp sự cố khi xử lý dữ liệu. Thông báo trung thực rằng chưa xử lý được mục này, "
        "tuyệt đối không bịa đặt thông tin."
    ),
    "READ_ERROR": (
        "Không đọc được dữ liệu hiện tại từ nguồn lưu trữ. Hãy nói rõ dữ liệu chưa khả dụng; "
        "không dùng snapshot cũ như thể đó là dữ liệu mới."
    ),
    "WRITE_REJECTED": (
        "Yêu cầu ghi bị từ chối trước khi lưu. Không được nói đã lưu; hãy giải thích ngắn gọn "
        "rằng dữ liệu chưa được ghi nhận."
    ),
    "PERSISTENCE_ERROR": (
        "Nguồn lưu trữ không xác nhận được thao tác ghi. Tuyệt đối không nói 'đã lưu' hoặc "
        "'đã ghi nhận'; hãy thông báo thao tác thất bại."
    ),
}

_ERROR_RESPONSE_CONTRACT = (
    "Trả lời bằng tiếng Việt tự nhiên, ngắn gọn: nói đúng phần chưa làm được, xác nhận dữ liệu cũ "
    "chưa bị thay đổi nếu đây là thao tác ghi, rồi nêu một bước thử lại hữu ích. Không đổ lỗi cho "
    "người dùng; không nhắc tên tool, JSON, mã lỗi, catalog, schema hay quy trình nội bộ. "
)

# Tool errors worth one automatic retry. A timeout or a disconnect will not fix
# itself inside the same turn, so those are not retried.
_RETRYABLE_ERRORS: frozenset[str] = frozenset({"TOOL_INTERNAL_ERROR"})

_SUCCESS_RESULT_GUIDANCE: dict[str, str] = {
    "get_user_profile": (
        "Chỉ dùng những trường liên quan đến câu hỏi hiện tại; không đọc lại toàn bộ hồ sơ, "
        "không hỏi lại dữ kiện đã có, và không hỏi thai kỳ/cho con bú khi giới tính hồ sơ là nam."
    ),
    "search_dish_catalog": (
        "matched_count là kết quả sau khi đã quét toàn bộ dữ liệu món ăn. Nếu có kết quả, trả lời bằng đúng "
        "tên/nguyên liệu/dinh dưỡng được trả về; instructions rỗng nghĩa là dữ liệu hiện có chưa kèm cách làm, "
        "không được tự viết. Khi nói với người dùng, dùng cụm 'dữ liệu của ứng dụng', không dùng từ 'catalog'. "
        "Không gọi đây là khuyến nghị nếu chưa qua suggest_dish."
    ),
    "search_recipe_web": (
        "Cách làm và nguyên liệu từ nguồn ngoài phải ghi nguồn và trạng thái xác minh. Với "
        "purpose=instructions_only, chỉ dùng nguồn ngoài cho cách làm tham khảo; dinh dưỡng vẫn lấy "
        "từ món local và nói rõ hai công thức có thể khác nhau. Nếu nutrition_status không khả dụng, "
        "không gọi search_food_nutrition bằng tên cả món vì bảng đó chỉ chứa nguyên liệu và fuzzy match "
        "có thể trả thực phẩm không liên quan."
    ),
    "search_exercise_catalog": (
        "matched_count là kết quả sau khi đã quét toàn bộ dữ liệu bài tập. Chỉ dịch sát tên động tác và liều lượng "
        "thực sự có trong instructions.text; không tự thêm cách đặt người, kỹ thuật, lợi ích hay cảnh báo. "
        "Nếu review_status/quality_flags cho biết chưa duyệt, phải nói rõ. Đây chỉ là tra cứu: không gọi "
        "bài này phù hợp/an toàn cho người dùng và không mời lưu hoặc ghi nhật ký. Khi nói với người dùng, "
        "dùng cụm 'dữ liệu của ứng dụng', không dùng từ 'catalog'."
    ),
    "suggest_dish": (
        "Nêu đúng món và số liệu tool trả về, rồi giải thích ngắn vì sao phù hợp với yêu cầu hiện tại. "
        "Nếu người dùng chủ động muốn món này dù nó chưa tối ưu với mục tiêu, hãy tôn trọng lựa chọn, "
        "nêu một đánh đổi cụ thể và chỉ gợi ý một điều chỉnh nhỏ; không âm thầm đổi món và không phán xét. "
        "Không hỏi lưu lần nữa vì hệ thống sẽ thêm đúng một câu xác nhận."
    ),
    "suggest_workout": (
        "Dùng đúng danh sách, liều lượng và ước tính tool trả về; không tự thêm bài hoặc con số. "
        "Không mô tả buổi tập như hình phạt, món nợ hoặc cách đốt bù thức ăn; ưu tiên mục tiêu tập, "
        "mức sẵn sàng và cảm giác cơ thể hiện tại."
    ),
    "build_personalized_workout": (
        "Thẻ có cấu trúc là nguồn duy nhất cho bài, hiệp, lần, nghỉ và tải; không diễn giải lại bằng số khác."
    ),
    "get_today_meals": (
        "Phân biệt rõ chưa ghi nhận bữa ăn với đã ăn 0 kcal; trả lời đúng phạm vi hôm nay."
    ),
    "get_today_exercises": (
        "Phân biệt rõ chưa ghi nhận vận động với đã tập 0 phút; trả lời đúng phạm vi hôm nay."
    ),
    "get_lifestyle_logs": (
        "Phân biệt chưa ghi nhận với giá trị bằng 0. Phản hồi trung tính, không chẩn đoán hoặc phán xét "
        "giấc ngủ, căng thẳng, tâm trạng và thói quen từ một lần ghi nhận."
    ),
    "log_meal": (
        "Chỉ nói đã ghi bữa ăn khi kết quả xác nhận thành công; không khen/chê món ăn và không đề nghị "
        "tập để bù calo. Nếu đây mới là gợi ý hoặc kế hoạch thì không mô tả như bữa đã ăn."
    ),
    "log_exercise": (
        "Chỉ nói đã ghi vận động khi kết quả xác nhận thành công; không mô tả vận động như cách trả nợ "
        "cho thức ăn và không biến bài dự kiến thành buổi đã tập."
    ),
    "log_weight": (
        "Xác nhận ngắn gọn, trung tính và không phán xét con số cân nặng hoặc suy diễn tiến bộ từ một lần đo."
    ),
    "log_lifestyle": (
        "Xác nhận ngắn gọn, trung tính; không chẩn đoán hoặc suy diễn xu hướng từ một lần ghi nhận."
    ),
    "get_active_plan_v2": (
        "Nói rõ đây là kế hoạch đang dùng, không phải bằng chứng người dùng đã ăn hoặc đã tập các mục trong đó."
    ),
    "build_nutrition_plan": (
        "Nói rõ đây là bản nháp để xem và xác nhận, chưa phải nhật ký thực tế và chưa tự thay thế kế hoạch đang dùng."
    ),
    "build_workout_schedule": (
        "Nói rõ đây là bản nháp để xem và xác nhận, chưa phải buổi tập đã thực hiện và chưa tự thay thế lịch đang dùng."
    ),
}

_DEFAULT_SUCCESS_GUIDANCE = (
    "Trả lời thẳng yêu cầu hiện tại bằng tiếng Việt tự nhiên và ngắn gọn. Chỉ dùng dữ liệu trong "
    "kết quả; không nhắc tên tool, JSON, mã trạng thái nội bộ hay quy trình điều phối. Tôn trọng "
    "lựa chọn của người dùng, không phán xét, và phân biệt rõ gợi ý, dự kiến, đã thực hiện và đã lưu."
)

_DOMAIN_CUES: dict[str, tuple[str, ...]] = {
    "nutrition": (
        "an", "uong", "mon", "bua", "thuc don", "dinh duong", "calo",
        "kcal", "protein", "dam", "carb", "chat beo", "com", "pho", "bun",
        "chao", "thit", "rau", "trai cay", "di ung", "kieng", "giam can",
        "tang can", "khau phan", "nguyen lieu", "cach lam", "cong thuc",
    ),
    "fitness": (
        "tap", "bai tap", "workout", "gym", "chay", "di bo", "squat",
        "chong day", "ta", "hiep", "rep", "nhom co", "van dong", "can nang",
        "chung can", "cach tap", "dau goi", "dau vai", "dau lung",
    ),
    "lifestyle": (
        "ngu", "stress", "cang thang", "tam trang", "mood", "uong nuoc",
        "mat ngu", "met moi", "nhac nho",
    ),
}

_PROFILE_TOOL_NAMES: frozenset[str] = frozenset({"get_user_profile"})
_KNOWLEDGE_TOOL_NAMES: frozenset[str] = frozenset(
    {"query_rag", "search_medical_knowledge"}
)
_PLAN_CUES: tuple[str, ...] = (
    "ke hoach", "thuc don", "lich tap", "lo trinh", "giao an"
)

_NAVIGATION_CUES: tuple[str, ...] = (
    "mo trang", "mo man hinh", "di toi trang", "chuyen toi trang",
    "chuyen sang trang", "xem trang",
)
_REMINDER_CUES: tuple[str, ...] = (
    "nhac toi", "nhac minh", "dat nhac", "tao nhac", "hen gio", "nhac nho",
)
_RECOMMENDATION_CUES: tuple[str, ...] = (
    "goi y", "an gi", "mon nao", "tap gi", "bai tap nao", "doi mon",
    "muon an", "nen an", "nen tap",
)
_HISTORY_CUES: tuple[str, ...] = (
    "nhat ky", "hom nay da", "tuan nay da", "tuan qua", "thang nay da",
    "thang qua", "lich su", "xu huong", "con bao nhieu", "da an gi",
    "da tap gi",
)
_LOOKUP_CUES: tuple[str, ...] = (
    "bao nhieu calo", "bao nhieu kcal", "bao nhieu dam", "bao nhieu protein",
    "nguyen lieu", "cach lam", "cong thuc", "cach tap", "thuc hien the nao",
    "co trong ung dung", "tim mon", "tim bai",
)
_WEIGHT_TREND_CUES: tuple[str, ...] = (
    "can khong giam", "can khong tang", "chung can", "xu huong can nang",
    "tien do can nang", "vi sao can", "tai sao can",
)
_EXPLICIT_LOG_CUES: tuple[str, ...] = (
    "vua an", "moi an", "toi da an", "minh da an", "vua tap", "moi tap",
    "toi da tap", "minh da tap", "ghi lai", "ghi vao", "luu lai",
    "vua chay", "moi chay", "sang nay chay", "vua di bo", "moi di bo",
    "can nang hom nay", "hom nay toi nang", "hom nay minh nang",
    "dem qua ngu", "toi ngu", "minh ngu", "vua uong", "moi uong",
    "hom nay stress", "hom nay cang thang", "tam trang hom nay",
)
_PROFILE_UPDATE_CUES: tuple[str, ...] = (
    "toi di ung", "minh di ung", "toi khong an", "minh khong an",
    "toi thich an", "minh thich an", "toi khong thich", "minh khong thich",
    "toi bi dau khi tap", "minh bi dau khi tap", "toi co the tap",
    "minh co the tap", "toi thich tap", "minh thich tap", "toi thich chay",
    "minh thich chay", "toi dau goi", "minh dau goi", "toi dau vai",
    "minh dau vai", "toi dau lung", "minh dau lung",
)
_MEDICAL_OR_EVIDENCE_CUES: tuple[str, ...] = (
    "nghien cuu", "bang chung", "khoa hoc", "nguon nao", "benh", "thuoc",
    "tuong tac", "tac dung phu", "lieu luong", "tieu duong", "huyet ap",
    "mo mau", "gout", "da day", "than", "mang thai", "cho con bu",
    "dau nguc", "kho tho", "chong mat", "ngat", "co giat", "tu lam hai",
    "tu tu",
)

_NUTRITION_RECOMMENDATION_TOOLS: frozenset[str] = frozenset(
    {
        "get_user_profile", "get_today_meals", "suggest_dish",
        "search_dish_catalog", "get_active_plan_v2",
    }
)
_FITNESS_RECOMMENDATION_TOOLS: frozenset[str] = frozenset(
    {
        "get_user_profile", "get_today_exercises", "suggest_workout",
        "build_personalized_workout", "get_workout_substitutions",
        "search_exercise_catalog", "get_active_plan_v2",
    }
)
_NON_IDEMPOTENT_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "log_meal", "update_nutrition_profile", "save_workout_plan",
        "log_workout_result", "update_workout_profile", "log_exercise",
        "log_weight", "log_lifestyle", "set_lifestyle_reminder",
        "navigate_to_screen", "save_plan", "set_plan_status",
    }
)

_EXPLICIT_DISH_REQUEST_PREFIXES: tuple[str, ...] = (
    "toi muon an mon",
    "toi muon an",
    "minh muon an mon",
    "minh muon an",
    "em muon an mon",
    "em muon an",
    "anh muon an mon",
    "anh muon an",
    "chi muon an mon",
    "chi muon an",
    "muon an mon",
    "muon an",
    "toi them an",
    "minh them an",
    "them an",
)

_GENERIC_DISH_REQUESTS: frozenset[str] = frozenset(
    {
        "gi",
        "gi do",
        "mon gi",
        "mon nao",
        "do an",
        "thuc an",
        "bua sang",
        "bua trua",
        "bua toi",
        "mon au",
        "do au",
        "mon a",
        "do a",
        "mon viet",
        "do viet",
        "mon han",
        "mon nhat",
        "mon thai",
        "mon trung",
        "mon y",
    }
)


def _normalise_intent_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or "").casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = value.replace("đ", "d")
    value = "".join(
        char if char.isalnum() or char.isspace() else " " for char in value
    )
    return " ".join(value.split())


def _contains_intent_cue(normalized: str, cue: str) -> bool:
    return f" {cue} " in f" {normalized} "


def _extract_explicit_dish_query(user_text: str) -> str | None:
    """Extract a concrete dish from a narrow, explicit eating request.

    This intentionally does not try to be a general NER system. It only
    handles strong forms such as ``Tôi muốn ăn pizza`` so the orchestrator can
    enforce the catalog-first contract when a small model tries to answer from
    stale conversation history. Broad requests (``món Âu``, ``món gì`` or a
    macro target) continue through the normal recommendation tools.
    """

    raw_words = str(user_text or "").strip().strip(".!?,;:\"'“”‘’").split()
    normalized = _normalise_intent_text(user_text)
    normalized_words = normalized.split()
    if not raw_words or len(raw_words) != len(normalized_words):
        return None

    for prefix in _EXPLICIT_DISH_REQUEST_PREFIXES:
        prefix_words = prefix.split()
        if normalized_words[: len(prefix_words)] != prefix_words:
            continue
        query_words = raw_words[len(prefix_words) :]
        query_normalized_words = normalized_words[len(prefix_words) :]
        while query_normalized_words and query_normalized_words[-1] in {
            "nha",
            "nhe",
            "a",
        }:
            query_words.pop()
            query_normalized_words.pop()
        if query_normalized_words[-2:] == ["duoc", "khong"]:
            query_words = query_words[:-2]
            query_normalized_words = query_normalized_words[:-2]
        if not query_normalized_words or len(query_normalized_words) > 6:
            return None
        query_normalized = " ".join(query_normalized_words)
        if (
            query_normalized in _GENERIC_DISH_REQUESTS
            or any(token in {"gi", "nao"} for token in query_normalized_words)
            or query_normalized_words[0] in {"nhieu", "it", "phu", "lanh"}
            or "phu hop" in query_normalized
        ):
            return None
        return " ".join(query_words).strip()
    return None


_POSITIVE_DISH_QUERY_CUES: tuple[str, ...] = (
    "an",
    "muon an",
    "them an",
    "an lai",
    "goi y mon",
    "goi y bua",
    "cho toi mon",
    "cho xin mon",
    "tim mon",
    "doi sang",
    "doi thanh",
)

_NEGATIVE_DISH_QUERY_CUES: tuple[str, ...] = (
    "di ung",
    "khong an",
    "khong muon an",
    "khong co",
    "tranh",
    "loai bo",
)

_EXTERNAL_INGREDIENT_NAMES_VI: dict[str, str] = {
    "cassava pizza base": "đế pizza cassava",
    "tomato sauce": "sốt cà chua",
    "chorizo": "xúc xích chorizo",
    "turkey ham": "giăm bông gà tây",
    "sweetcorn": "bắp ngọt",
    "green olives": "ô liu xanh",
    "paprika": "ớt paprika",
    "mozzarella": "phô mai mozzarella",
}


def _friendly_external_ingredient(source_text: str) -> str:
    """Make common source ingredients readable without inventing quantities."""

    text = " ".join(str(source_text or "").split())
    lowered = text.casefold()
    casabe_match = re.fullmatch(r"(\d+(?:\.\d+)?)\s+cut thick slices\s+casabe", lowered)
    if casabe_match:
        return f"{casabe_match.group(1)} lát casabe dày"
    for english_name, vietnamese_name in _EXTERNAL_INGREDIENT_NAMES_VI.items():
        if lowered == english_name:
            return vietnamese_name
        if lowered.endswith(" " + english_name):
            amount = text[: -len(english_name)].strip()
            if amount.casefold().endswith("g"):
                amount = amount[:-1].strip() + " g"
            return f"{amount} {vietnamese_name}".strip()
    return text


def _ground_suggest_dish_queries(
    calls: list[ToolCall],
    *,
    user_text: str,
    explicit_dish_query: str | None,
) -> list[dict[str, str]]:
    """Keep ``suggest_dish.query`` tied to the current user's own words.

    A model may turn a soft profile hint (for example, "high protein") into a
    hard ingredient query such as ``gà``. That collapses the safe candidate
    pool and makes a deterministic selector repeat the same dish. Explicit
    current requests are preserved; unsupported or stale model-added filters
    are removed before dispatch.
    """

    normalized_user = _normalise_intent_text(user_text)
    normalized_explicit = _normalise_intent_text(explicit_dish_query or "")
    changes: list[dict[str, str]] = []

    for call in calls:
        if call.name != "suggest_dish" or not isinstance(call.arguments, dict):
            continue
        raw_query = " ".join(str(call.arguments.get("query") or "").split())
        if not raw_query:
            continue
        normalized_query = _normalise_intent_text(raw_query)

        if normalized_explicit:
            if normalized_query != normalized_explicit:
                call.arguments["query"] = explicit_dish_query
                changes.append({"action": "REPLACED", "query": explicit_dish_query or ""})
            continue

        query_is_literal = _contains_intent_cue(normalized_user, normalized_query)
        positive_request = (
            normalized_user == normalized_query
            or any(
                _contains_intent_cue(normalized_user, cue)
                for cue in _POSITIVE_DISH_QUERY_CUES
            )
            or normalized_user.startswith("an ")
        )
        negative_request = any(
            _contains_intent_cue(normalized_user, cue)
            for cue in _NEGATIVE_DISH_QUERY_CUES
        )
        if query_is_literal and positive_request and not negative_request:
            continue

        call.arguments.pop("query", None)
        changes.append({"action": "REMOVED", "query": raw_query})

    return changes


def _detect_safety_pain_response(user_text: str, history: list[Any]) -> str | None:
    """Detect if user is responding to a workout safety/pain clarification question.

    Returns:
        "NO" if user confirms no pain / ready to work out,
        "YES" if user reports active pain or discomfort,
        None if this turn is not a safety clearance response.
    """
    if not history:
        return None
    last_assistant_text = ""
    for turn in reversed(history):
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else None)
        if role == "assistant":
            last_assistant_text = getattr(turn, "content", "") or (turn.get("content", "") if isinstance(turn, dict) else "")
            break
    if not isinstance(last_assistant_text, str) or not last_assistant_text:
        return None
    normalized_assistant = _normalise_intent_text(last_assistant_text)
    safety_cues = (
        "dau hoac kho chiu",
        "bi dau",
        "chan thuong",
        "xac nhan mot dieu an toan",
        "an toan truoc khi tao buoi tap",
        "dau hieu canh bao",
        "dau dau goi",
        "trang thai suc khoe va kinh nghiem",
    )
    if not any(cue in normalized_assistant for cue in safety_cues):
        return None

    normalized_user = _normalise_intent_text(user_text)
    words = normalized_user.split()
    has_negation = any(neg in words for neg in ("khong", "ko", "k", "chua"))
    has_pain = any(cue in normalized_user for cue in ("dau", "nhuc", "chan thuong", "kho chiu"))
    if has_pain and not has_negation:
        return "YES"
    if words == ["co"]:
        return "YES"
    clearance_cues = (
        "oke", "ok", "khong", "khong dau", "binh thuong", "on", "khong sao",
        "duoc", "yes", "no", "toi on", "khoe", "chuan", "tot", "khong bi gi", "san sang"
    )
    if normalized_user in clearance_cues or has_negation or any(cue == normalized_user for cue in clearance_cues):
        return "NO"
    return None


def _tool_schema_name(schema: Any) -> str | None:
    if not isinstance(schema, dict):
        return None
    function = schema.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    return name if isinstance(name, str) and name else None


def _select_relevant_tool_schemas(
    schemas: list[dict[str, Any]], user_text: str
) -> list[dict[str, Any]]:
    """Return the smallest high-confidence tool set for the current request.

    Routing is deliberately asymmetric: a recognized action gets a narrow
    set, while an ambiguous request keeps the complete catalog. Removing a
    needed tool is much worse than sending a few extra schemas.
    """

    normalized = _normalise_intent_text(user_text)

    def has_any(cues: tuple[str, ...]) -> bool:
        return any(_contains_intent_cue(normalized, cue) for cue in cues)

    def select(names: set[str] | frozenset[str]) -> list[dict[str, Any]]:
        selected = [
            schema for schema in schemas if _tool_schema_name(schema) in names
        ]
        return selected or schemas

    domains = {
        domain
        for domain, cues in _DOMAIN_CUES.items()
        if has_any(cues)
    }
    weight_report = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*kg\b", normalized))
    if weight_report:
        domains.add("fitness")
    measured_drink = bool(
        _contains_intent_cue(normalized, "uong")
        and re.search(r"\b\d+(?:[.,]\d+)?\s*ml\b", normalized)
    )
    named_beverage = has_any(("sua", "ca phe", "tra", "nuoc ngot", "bia", "ruou"))
    hydration_quantity = measured_drink and not named_beverage
    if hydration_quantity:
        domains.add("lifestyle")
        domains.discard("nutrition")

    knowledge_needed = has_any(_MEDICAL_OR_EVIDENCE_CUES)
    names = set(_KNOWLEDGE_TOOL_NAMES if knowledge_needed else ())
    recognized = knowledge_needed

    # Direct UI commands and reminders are independent intents. Accumulating
    # instead of returning early keeps multi-part requests intact.
    if has_any(_NAVIGATION_CUES):
        names.add("navigate_to_screen")
        recognized = True
    if has_any(_REMINDER_CUES):
        names.add("set_lifestyle_reminder")
        recognized = True

    # Weight-stall analysis is inherently cross-domain. Giving it the whole
    # 34-tool catalog was slow and also exposed unrelated write actions.
    if has_any(_WEIGHT_TREND_CUES):
        names.update(
            {
                "get_user_profile", "get_weight_history", "get_meal_log_range",
                "get_exercise_log_range", "get_lifestyle_logs", "calculate_tdee",
            }
        )
        recognized = True

    plan_intent = has_any(_PLAN_CUES)
    if plan_intent:
        plan_tools = set(_PROFILE_TOOL_NAMES)
        create_plan = has_any(("lap", "tao", "xay dung", "len"))
        revise_plan = has_any(("doi", "sua", "dieu chinh", "them", "bo", "thay"))
        change_status = has_any(("luu", "kich hoat", "tam dung", "tiep tuc", "huy"))
        if create_plan:
            if "nutrition" in domains:
                plan_tools.add("build_nutrition_plan")
            if "fitness" in domains:
                plan_tools.add("build_workout_schedule")
            if not domains:
                plan_tools.update({"build_nutrition_plan", "build_workout_schedule"})
        elif revise_plan:
            plan_tools.update({"get_plan", "revise_plan"})
        elif change_status:
            plan_tools.update(
                {"get_plan", "get_active_plan_v2", "save_plan", "set_plan_status"}
            )
        else:
            plan_tools.update({"get_plan", "get_active_plan_v2"})
        names.update(plan_tools)
        recognized = True

    history_intent = has_any(_HISTORY_CUES)
    if history_intent and domains:
        names.update(_PROFILE_TOOL_NAMES)
        if "nutrition" in domains:
            names.update({"get_today_meals", "get_meal_log_range"})
        if "fitness" in domains:
            names.update(
                {"get_today_exercises", "get_exercise_log_range", "get_weight_history"}
            )
        if "lifestyle" in domains:
            names.add("get_lifestyle_logs")
        recognized = True

    recommendation_intent = has_any(_RECOMMENDATION_CUES)
    if recommendation_intent and domains and not history_intent:
        names.update(_PROFILE_TOOL_NAMES)
        if "nutrition" in domains:
            names.update(_NUTRITION_RECOMMENDATION_TOOLS)
        if "fitness" in domains:
            names.update(_FITNESS_RECOMMENDATION_TOOLS)
        if "lifestyle" in domains:
            names.add("get_lifestyle_logs")
        recognized = True

    lookup_intent = has_any(_LOOKUP_CUES)
    if lookup_intent:
        if "nutrition" in domains or not domains:
            names.update(
                {"search_food_nutrition", "search_dish_catalog", "search_recipe_web"}
            )
        if "fitness" in domains or not domains:
            names.add("search_exercise_catalog")
        recognized = True

    explicit_log = (
        has_any(_EXPLICIT_LOG_CUES)
        or weight_report
        or hydration_quantity
        or bool(
            re.search(
                r"\b(?:sang|trua|toi|hom nay)\b.*\b(?:toi|minh)\s+(?:an|tap)\b",
                normalized,
            )
        )
    )
    readback_only = history_intent and has_any(
        ("da an gi", "da tap gi", "con bao nhieu")
    )
    profile_update = has_any(_PROFILE_UPDATE_CUES)
    if profile_update and not explicit_log and domains:
        if "nutrition" in domains:
            names.add("update_nutrition_profile")
        if "fitness" in domains:
            names.add("update_workout_profile")
        recognized = True

    if explicit_log and domains and not readback_only:
        if "nutrition" in domains:
            names.update({"log_meal", "search_dish_catalog", "search_food_nutrition"})
            if profile_update:
                names.add("update_nutrition_profile")
        if weight_report:
            names.add("log_weight")
        elif "fitness" in domains:
            # A completed run/workout is not a weight measurement. Exposing
            # ``log_weight`` here invited the model to fabricate a value and
            # added an unrelated write schema to a common fast path.
            names.update({"log_exercise", "search_exercise_catalog"})
            if profile_update:
                names.add("update_workout_profile")
        if hydration_quantity or "lifestyle" in domains:
            names.add("log_lifestyle")
        recognized = True

    if knowledge_needed:
        names.update(_PROFILE_TOOL_NAMES)

    if recognized:
        return select(names)

    if not domains:
        return schemas

    # Imported lazily to avoid coupling the registry's startup path to the
    # orchestrator module. The map is the live source of domain membership.
    from services.agent.tools import DOMAIN_MODULE_MAP

    allowed = set(_PROFILE_TOOL_NAMES)
    for domain in domains:
        allowed.update(DOMAIN_MODULE_MAP.get(domain, ()))
    return select(allowed)


class AgentOrchestrator:
    def __init__(
        self,
        llm: Any,
        tools: Any,
        memory: Any,
        session_store: Any,
        dispatcher: Any,
        gateway: Any | None = None,
        max_steps: int | None = None,
        tool_timeout_ms: int | None = None,
        heavy_llm: Any | None = None,
        pending_actions: PendingUserActionStore | None = None,
        scope_guard: ScopeGuard | None = None,
        metrics: Any | None = None,
        memory_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.llm = llm
        self.heavy_llm = heavy_llm
        self.tools = tools
        self.memory = memory
        self.session_store = session_store
        self.dispatcher = dispatcher
        self.gateway = gateway
        self.max_steps = max_steps or settings.max_agent_steps
        self.tool_timeout_ms = tool_timeout_ms or settings.tool_timeout_ms
        self.pending_actions = pending_actions or pending_user_actions
        self.scope_guard = scope_guard
        self.metrics = metrics
        self.memory_semaphore = memory_semaphore
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._memory_updates_in_flight: set[str] = set()

    # ------------------------------------------------------------------ main
    async def handleChatMessage(
        self, session_id: str, user_text: str, user_context: Any = None
    ) -> None:
        gateway = self.gateway
        public_trace = PublicReasoningTrace()
        record_initial_context(public_trace, user_context)
        debug_trace = DebugTraceBuilder(
            enabled=bool(gateway is not None and getattr(gateway, "debug_trace_enabled", False))
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "lifecycle",
            "orchestrator",
            "TURN_STARTED",
            payload={"session_id": session_id},
        )
        trace = ContextTraceRecorder(
            user_text,
            enabled=(settings.context_trace_enabled or settings.context_planner_shadow_enabled),
        )
        trace.capture_initial_context(user_context)
        original_user_text = user_text
        scope_reply_suffix: str | None = None
        user_history_marker: str | None = None
        try:
            # A compatible confirmation/rejection resolves the exact stored
            # target before any general scope, context, semantic or LLM work.
            # The semantic S1 shadow is never an authority for this identity.
            pending_resolution = self.pending_actions.claim_confirmation(
                session_id,
                self._owner_user_id(gateway, user_context),
                user_text,
            )
            if pending_resolution.status != "NO_MATCH":
                await self._append_turn(session_id, "user", original_user_text)
                if (
                    pending_resolution.status == "CLAIMED"
                    and pending_resolution.action is not None
                ):
                    await self._resolve_pending_user_action(
                        session_id,
                        pending_resolution.action,
                        gateway,
                        public_trace,
                        debug_trace,
                    )
                    trace.finish(outcome="COMPLETED_PENDING_ACTION")
                else:
                    await self._respond_to_pending_resolution(
                        session_id,
                        pending_resolution,
                        gateway,
                        public_trace,
                        debug_trace,
                    )
                    trace.finish(outcome=f"PENDING_ACTION_{pending_resolution.status}")
                self._schedule_memory_update(session_id)
                return

            if self.scope_guard is not None:
                scope_decision = await self.scope_guard.classify(user_text)
                if (
                    not scope_decision.should_call_llm
                    and self.scope_guard.may_be_contextual_continuation(user_text)
                ):
                    scope_history_loader = getattr(
                        self.memory,
                        "loadRecentConversationForScope",
                        None,
                    )
                    if callable(scope_history_loader):
                        try:
                            recent_scope_history = await scope_history_loader(
                                session_id,
                                max_turns=12,
                            )
                            contextual_decision = (
                                self.scope_guard.contextualize_continuation(
                                    user_text,
                                    recent_scope_history,
                                )
                            )
                            if contextual_decision is not None:
                                scope_decision = contextual_decision
                        except Exception as exc:
                            # Context lookup is an optional fail-closed bridge:
                            # an unavailable database keeps the original
                            # clarification instead of widening app scope.
                            logger.warning(
                                "Contextual scope resolution skipped for session=%s: %s",
                                session_id,
                                exc,
                            )
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "routing",
                    "scope_guard",
                    "SCOPE_DECISION",
                    payload={
                        "outcome": scope_decision.outcome.value,
                        "intent": scope_decision.intent.value,
                        "safety": scope_decision.safety.value,
                        "confidence": scope_decision.confidence,
                        "method": scope_decision.method,
                        "reason_code": scope_decision.reason_code,
                        "fragment_scopes": [
                            fragment.scope.value for fragment in scope_decision.fragments
                        ],
                        "fragment_intents": [
                            fragment.resolved_intent.value
                            for fragment in scope_decision.fragments
                        ],
                        "mixed": scope_decision.is_mixed,
                    },
                    result=(
                        "FORWARDED" if scope_decision.should_call_llm else "SHORT_CIRCUITED"
                    ),
                )
                if not scope_decision.should_call_llm:
                    if self.metrics is not None:
                        self.metrics.increment("inference.deterministic_early_exit")
                    reply = scope_decision.reply or ""
                    await self._append_turn(
                        session_id,
                        "user",
                        user_text,
                        tool_name=SCOPE_GUARD_HISTORY_MARKER,
                    )
                    early_exit_trace = PublicReasoningTrace()
                    early_exit_trace.mark_completed()
                    if reply:
                        await self._append_turn(
                            session_id,
                            "assistant",
                            reply,
                            tool_name=SCOPE_GUARD_HISTORY_MARKER,
                        )
                    if gateway is not None and reply and hasattr(gateway, "send_token"):
                        await gateway.send_token(reply)
                    if gateway is not None:
                        await self._send_done(
                            gateway,
                            reply,
                            structured_data=None,
                            public_trace=early_exit_trace,
                        )
                    trace.finish(outcome=f"SCOPE_{scope_decision.outcome.value}")
                    return

                if scope_decision.is_mixed:
                    # Only the allowed fragment may reach memory/RAG/router/tools.
                    # The original message remains visible in chat history but
                    # is marked so future model context cannot replay it.
                    user_text = scope_decision.allowed_text
                    scope_reply_suffix = scope_decision.reply_suffix
                    user_history_marker = SCOPE_GUARD_MIXED_HISTORY_MARKER

            if gateway is not None and hasattr(gateway, "send_status"):
                await gateway.send_status("Đang xem thông tin liên quan…")
            context_plan_for_cost = None
            try:
                intent_for_cost, context_plan_for_cost = (
                    _shadow_context_planner.create_plan(user_text)
                )
            except Exception:
                intent_for_cost = None
            load_context = getattr(self.memory, "loadContext")
            optimized_context_loader = getattr(
                self.memory, "loadContextCostOptimized", None
            )
            if (
                context_plan_for_cost is not None
                and intent_for_cost is not None
                and intent_for_cost.confidence >= 0.80
                and not intent_for_cost.clarification_required
                and callable(optimized_context_loader)
            ):
                context = await optimized_context_loader(
                    session_id,
                    user_text,
                    include_rag=context_plan_for_cost.rag_policy.value
                    != "RAG_FORBIDDEN",
                    include_relevant_history=context_plan_for_cost.memory_policy.value
                    != "FORBIDDEN",
                )
            else:
                # Unknown memory implementations and uncertain classifications
                # retain the previous fail-open context behavior.
                context = await load_context(session_id, user_text)
            trace.capture_rag(context)
            await self._publish_public_trace(gateway, public_trace)

            plan = classify_turn(user_text, history_len=len(context.history))
            await self._record_debug(
                gateway,
                debug_trace,
                "routing",
                "turn_router",
                "ROUTER_DECISION",
                payload={
                    "tier": plan.tier,
                    "uses_heavy_model": plan.use_heavy_model,
                    "offers_tools": plan.offer_tools,
                    "max_steps": plan.max_steps,
                },
            )
            llm = self._select_llm(plan)
            cost_limits = limits_for_turn(plan)
            tool_schemas = None
            if plan.offer_tools:
                tool_schemas = _select_relevant_tool_schemas(
                    self.tools.schemas(), user_text
                )
            trace.capture_tools_offered(tool_schemas)

            inference_decision = None
            qualified_v2 = False
            if intent_for_cost is not None and context_plan_for_cost is not None:
                inference_decision = decide_inference(
                    intent_for_cost, context_plan_for_cost, plan, cost_limits
                )
                if self.metrics is not None:
                    self.metrics.increment(
                        f"inference.route.{inference_decision.route.value.casefold()}"
                    )
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "routing",
                    "inference_policy_v2",
                    "INFERENCE_DECISION_V2",
                    payload=inference_decision.to_dict(),
                    result=(
                        "ENFORCED"
                        if settings.backend_cost_mode == "enforce"
                        else "TRUSTED_SHADOW"
                    ),
                )
                allowed_shadow_arms = [
                    InferenceRoute.LIGHT_LLM,
                    InferenceRoute.HEAVY_LLM,
                ]
                if not intent_for_cost.explicit_write:
                    allowed_shadow_arms.insert(0, InferenceRoute.DETERMINISTIC)
                recommendation = _shadow_inference_bandit.recommend(
                    inference_decision.feature_vector(),
                    allowed_arms=allowed_shadow_arms,
                )
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "routing",
                    "linucb_shadow",
                    "SHADOW_ROUTE_RECOMMENDATION",
                    payload=recommendation.to_dict(),
                    result="NO_PRODUCTION_EFFECT",
                )
                qualified_v2 = bool(
                    inference_decision.confidence >= 0.85
                    and not inference_decision.clarification_required
                )

            logger.info(
                "Turn routed tier=%s heavy=%s tools=%s session=%s",
                plan.tier,
                plan.use_heavy_model,
                bool(tool_schemas),
                session_id,
            )

            user_profile: Any = user_context
            safety_pain_res = _detect_safety_pain_response(user_text, context.history)
            if safety_pain_res is not None:
                if isinstance(user_profile, dict):
                    user_profile = dict(user_profile)
                    workout_prof = dict(user_profile.get("workout_profile") or {})
                    workout_prof["current_pain_status"] = safety_pain_res
                    workout_prof["safety_checked_at"] = datetime.now(timezone.utc).isoformat()
                    if workout_prof.get("intake_confirmation_status") == "CONFIRMED":
                        workout_prof["intake_confirmation_status"] = "CONFIRMED"
                    user_profile["workout_profile"] = workout_prof
                elif user_profile is None:
                    user_profile = {
                        "workout_profile": {
                            "current_pain_status": safety_pain_res,
                            "safety_checked_at": datetime.now(timezone.utc).isoformat(),
                            "intake_confirmation_status": "CONFIRMED",
                        }
                    }
                if gateway is not None and hasattr(gateway, "user_context"):
                    if isinstance(gateway.user_context, dict):
                        merged_gw = dict(gateway.user_context)
                        merged_gw["workout_profile"] = user_profile.get("workout_profile")
                        gateway.user_context = merged_gw
                    else:
                        gateway.user_context = user_profile

            if isinstance(user_profile, dict) and context.pinned_facts:
                workout_prof = dict(user_profile.get("workout_profile") or {})
                if not workout_prof.get("available_equipment") or not workout_prof.get("training_experience"):
                    for pf in context.pinned_facts:
                        fact_text = str(getattr(pf, "fact", "")).lower()
                        if not workout_prof.get("available_equipment"):
                            if "thảm" in fact_text or "mat" in fact_text:
                                workout_prof["available_equipment"] = ["gym mat"]
                            elif "tạ" in fact_text or "dumbbell" in fact_text:
                                workout_prof["available_equipment"] = ["dumbbell"]
                        if not workout_prof.get("training_experience"):
                            if "mới bắt đầu" in fact_text or "novice" in fact_text:
                                workout_prof["training_experience"] = "NOVICE"
                            elif "năm" in fact_text or "lâu" in fact_text or "experienced" in fact_text:
                                workout_prof["training_experience"] = "EXPERIENCED"
                        if not workout_prof.get("preferred_training_days") and "thứ" in fact_text:
                            days = re.findall(r"thứ \d|chủ nhật", fact_text, re.IGNORECASE)
                            if days:
                                workout_prof["preferred_training_days"] = [d.capitalize() for d in days]
                                workout_prof["available_days_per_week"] = len(days)
                    if workout_prof.get("available_equipment") and not workout_prof.get("training_location"):
                        workout_prof["training_location"] = "home"
                    if workout_prof.get("available_equipment") and not workout_prof.get("default_session_duration_minutes"):
                        workout_prof["default_session_duration_minutes"] = 60
                    if workout_prof.get("available_equipment") and not workout_prof.get("exercise_safety_profile"):
                        workout_prof["exercise_safety_profile"] = {
                            "health_state": "HEALTHY_GENERAL",
                            "pregnancy_status": "NOT_APPLICABLE",
                            "warning_symptoms": [],
                            "acute_injury": False,
                            "recent_surgery": False,
                            "technique_screen_confirmed": False,
                        }
                    if workout_prof.get("available_equipment") and not workout_prof.get("intake_confirmation_status"):
                        workout_prof["intake_confirmation_status"] = "CONFIRMED"
                    user_profile["workout_profile"] = workout_prof
                    if gateway is not None and hasattr(gateway, "user_context") and isinstance(gateway.user_context, dict):
                        gateway.user_context["workout_profile"] = workout_prof
            messages = self._build_messages(
                context,
                user_text,
                plan,
                user_profile=user_profile,
                tool_catalog=tool_schemas,
                prompt_mode=cost_limits.prompt_mode,
                history_turn_limit=cost_limits.history_turn_limit,
            )
            explicit_dish_query = (
                _extract_explicit_dish_query(user_text) if plan.offer_tools else None
            )
            catalog_lookup_attempted = False
            current_context_size = len(json.dumps(messages, ensure_ascii=False, default=str))
            if tool_schemas:
                current_context_size += len(json.dumps(tool_schemas, ensure_ascii=False, default=str))
            trace.capture_production_router(plan, context_size_characters=current_context_size)
            await self._record_debug(
                gateway,
                debug_trace,
                "cost",
                "llm_cost_governor",
                "TURN_BUDGET_ASSIGNED",
                payload={
                    "mode": cost_limits.mode,
                    "max_llm_calls": cost_limits.max_llm_calls,
                    "max_output_tokens": cost_limits.max_output_tokens,
                    "history_turn_limit": cost_limits.history_turn_limit,
                    "estimated_initial_input_tokens": (
                        cost_limits.estimated_input_tokens(messages, tool_schemas)
                    ),
                },
                result="ENFORCED" if cost_limits.mode == "optimized" else "OFF",
            )
            if settings.context_planner_shadow_enabled:
                # Fail-open observation: D3.0 output cannot become an input to
                # any authoritative production decision in this turn.
                try:
                    names_method = getattr(self.tools, "names", None)
                    available_names = names_method() if callable(names_method) else ()
                    shadow_result = _shadow_context_planner.plan_shadow(
                        user_text, user_context=user_context, memory_context=context,
                        available_tool_names=available_names,
                        current_production_context_size_characters=current_context_size,
                    )
                    trace.capture_shadow(shadow_result)
                    all_tool_schemas = tool_schemas if tool_schemas is not None else self.tools.schemas()
                    token_measurements = measure_turn_tokens(
                        messages=messages,
                        production_tool_schemas=tool_schemas,
                        shadow_bundle=shadow_result.bundle.to_dict(),
                        shadow_tool_names=shadow_result.plan.permitted_tools,
                        all_tool_schemas=all_tool_schemas,
                        counter=TokenCounter.from_llm(llm, settings.llm_model),
                    )
                    trace.capture_token_measurements(token_measurements)
                    collection_path = settings.context_planner_natural_collection_path
                    if collection_path:
                        history = (
                            turn.content for turn in getattr(context, "history", ())
                            if getattr(turn, "role", None) == "user"
                        )
                        get_natural_collector(collection_path).collect(
                            session_id=session_id, query=user_text,
                            conversational_context=history,
                            shadow_result=shadow_result,
                            token_measurements=token_measurements,
                        )
                except Exception:
                    logger.warning("Shadow context planner failed; production turn unchanged", exc_info=True)
            await self._append_turn(
                session_id,
                "user",
                original_user_text,
                tool_name=user_history_marker,
            )

            # The router proposes a per-turn budget; the constructor's
            # ``max_steps`` remains a hard ceiling so callers (and tests) keep
            # full control over the worst case.
            step_budget = max(
                1,
                min(plan.max_steps, self.max_steps, cost_limits.max_llm_calls),
            )
            llm_calls = 0

            # Tracks how many times each tool already failed this turn, so a
            # broken tool cannot spin the loop until max_steps runs out.
            failure_counts: dict[str, int] = {}
            workout_structured: dict[str, Any] | None = None
            plan_structured: dict[str, Any] | None = None
            nutrition_structured: dict[str, Any] | None = None
            pending_dish_action: PendingUserAction | None = None
            pending_plan_action: PendingUserAction | None = None
            all_tool_results: list[tuple[ToolCall, ToolResult]] = []
            if getattr(context, "rag_chunks", None):
                all_tool_results.append(
                    (
                        ToolCall("context-rag", "query_rag", {}),
                        ToolResult(ok=True, data={"chunks": context.rag_chunks}),
                    )
                )
            if isinstance(user_context, dict):
                if any(
                    key in user_context
                    for key in ("today_meals", "today_meals_count", "today_calories_consumed")
                ):
                    all_tool_results.append(
                        (
                            ToolCall("context-meals", "get_today_meals", {}),
                            ToolResult(ok=True, data={
                                key: user_context.get(key)
                                for key in (
                                    "today_meals", "today_meals_count",
                                    "today_calories_consumed",
                                )
                                if key in user_context
                            }),
                        )
                    )
                if any(
                    key in user_context
                    for key in ("today_exercises", "today_exercises_count", "today_calories_burned")
                ):
                    all_tool_results.append(
                        (
                            ToolCall("context-exercises", "get_today_exercises", {}),
                            ToolResult(ok=True, data={
                                key: user_context.get(key)
                                for key in (
                                    "today_exercises", "today_exercises_count",
                                    "today_calories_burned",
                                )
                                if key in user_context
                            }),
                        )
                    )
            validate_before_output = bool(
                settings.backend_cost_mode == "enforce"
                and inference_decision is not None
                and qualified_v2
                and inference_decision.validators
            )

            # Qualified, high-confidence reads can be fetched before the
            # answer model. This is deliberately opt-in via enforce mode; the
            # default observe mode only records the candidate policy.
            if (
                settings.backend_cost_mode == "enforce"
                and inference_decision is not None
                and qualified_v2
                and inference_decision.prefetch_tools
            ):
                user_profile = await self._prefetch_read_facts(
                    session_id=session_id,
                    messages=messages,
                    tool_schemas=tool_schemas,
                    tool_names=inference_decision.prefetch_tools,
                    failure_counts=failure_counts,
                    user_profile=user_profile,
                    trace=trace,
                    public_trace=public_trace,
                    gateway=gateway,
                    debug_trace=debug_trace,
                    result_collector=all_tool_results,
                )
                if user_profile is not None:
                    messages[0]["content"] = buildSystemPrompt(
                        context.rolling_summary,
                        context.pinned_facts,
                        context.rag_chunks,
                        tool_catalog=tool_schemas,
                        user_profile=user_profile,
                        mode=cost_limits.prompt_mode,
                        relevant_history=getattr(context, "relevant_history", None),
                    )

            for step in range(step_budget):
                if gateway is not None and hasattr(gateway, "send_status"):
                    if step > 0:
                        await gateway.send_status("Đang kiểm tra thêm thông tin…")
                    else:
                        await gateway.send_status("Đang chuẩn bị câu trả lời…")
                llm_started_at = time.perf_counter()
                llm_calls += 1
                if self.metrics is not None:
                    route_key = (
                        inference_decision.route.value
                        if inference_decision
                        else plan.tier
                    ).casefold()
                    self.metrics.increment(
                        f"llm.calls.{route_key}"
                    )
                    self.metrics.increment(
                        f"llm.input_tokens_estimated.{route_key}",
                        cost_limits.estimated_input_tokens(messages, tool_schemas),
                    )
                response = await llm.chat(
                    messages,
                    tools=tool_schemas,
                    stream=not validate_before_output,
                    prefill=None,
                    max_tokens=cost_limits.max_output_tokens,
                )
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "RESPONSE_RECEIVED",
                    payload={"tool_call_count": len(response.tool_calls or [])},
                    latency_ms=elapsed_ms(llm_started_at),
                    result="OK",
                )

                query_guard_changes = _ground_suggest_dish_queries(
                    list(response.tool_calls or []),
                    user_text=user_text,
                    explicit_dish_query=explicit_dish_query,
                )
                if query_guard_changes:
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "policy",
                        "current_request_guard",
                        "SUGGESTION_QUERY_GROUNDED",
                        payload={"adjustments": query_guard_changes},
                        result="ENFORCED",
                    )

                # An external recipe lookup is never independent from the
                # canonical catalog check. If the model emits web lookup in
                # the first batch (alone or beside catalog lookup), replace it
                # with the local lookup. The deterministic fallback below may
                # call the approved web source only after a confirmed miss, or
                # only for missing cooking instructions on a local dish.
                catalog_policy_adjusted = False
                if not catalog_lookup_attempted:
                    get_tool = getattr(self.tools, "get", None)
                    catalog_available = bool(
                        callable(get_tool)
                        and get_tool("search_dish_catalog") is not None
                    )
                    early_web_calls = [
                        call
                        for call in list(response.tool_calls or [])
                        if call.name == "search_recipe_web"
                    ]
                    if catalog_available and early_web_calls:
                        calls_without_web = [
                            call
                            for call in list(response.tool_calls or [])
                            if call.name != "search_recipe_web"
                        ]
                        replaced_web_call = False
                        for web_call in early_web_calls:
                            query = " ".join(
                                str((web_call.arguments or {}).get("query") or "").split()
                            )
                            if len(query) < 2:
                                calls_without_web.append(web_call)
                                continue
                            replaced_web_call = True
                            query_key = query.casefold()
                            already_present = any(
                                call.name == "search_dish_catalog"
                                and isinstance(call.arguments, dict)
                                and " ".join(
                                    str(call.arguments.get("query") or "").split()
                                ).casefold()
                                == query_key
                                for call in calls_without_web
                            )
                            if already_present:
                                continue
                            arguments: dict[str, Any] = {
                                "query": query,
                                "page": 1,
                                "page_size": 5,
                                "include_details": True,
                            }
                            for key in ("meal_type", "dietary_restrictions"):
                                value = (web_call.arguments or {}).get(key)
                                if value is not None:
                                    arguments[key] = value
                            calls_without_web.append(
                                ToolCall(
                                    id=f"{web_call.id}-catalog-first",
                                    name="search_dish_catalog",
                                    arguments=arguments,
                                )
                            )
                        if replaced_web_call:
                            response.tool_calls = calls_without_web
                            catalog_lookup_attempted = any(
                                call.name == "search_dish_catalog"
                                for call in calls_without_web
                            )
                            catalog_policy_adjusted = True

                # A concrete current request must not be answered from stale
                # history with an unsupported "catalog không có" claim. Keep
                # the model's suggest_dish call when it carries the exact
                # query; otherwise enforce one bounded canonical lookup. A
                # direct web call is held until that lookup confirms a miss.
                if explicit_dish_query and not catalog_lookup_attempted:
                    get_tool = getattr(self.tools, "get", None)
                    if callable(get_tool) and get_tool("search_dish_catalog") is not None:
                        calls = list(response.tool_calls or [])
                        has_catalog_call = any(
                            call.name == "search_dish_catalog" for call in calls
                        )
                        has_matching_suggestion = any(
                            call.name == "suggest_dish"
                            and isinstance(call.arguments, dict)
                            and " ".join(
                                str(call.arguments.get("query") or "").split()
                            ).casefold()
                            == explicit_dish_query.casefold()
                            for call in calls
                        )
                        without_early_web = [
                            call for call in calls if call.name != "search_recipe_web"
                        ]
                        if len(without_early_web) != len(calls):
                            response.tool_calls = without_early_web
                            calls = without_early_web
                            catalog_policy_adjusted = True
                        if not has_catalog_call and not has_matching_suggestion:
                            response.tool_calls = [
                                *calls,
                                ToolCall(
                                    id=f"catalog-required-{step}",
                                    name="search_dish_catalog",
                                    arguments={
                                        "query": explicit_dish_query,
                                        "page": 1,
                                        "page_size": 5,
                                        "include_details": True,
                                    },
                                ),
                            ]
                            has_catalog_call = True
                            catalog_policy_adjusted = True
                        if has_catalog_call:
                            catalog_lookup_attempted = True
                if catalog_policy_adjusted:
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "policy",
                        "catalog_first_guard",
                        "CATALOG_LOOKUP_REQUIRED",
                        payload={"query": explicit_dish_query or "MODEL_WEB_QUERY"},
                        result="ENFORCED",
                    )
                # Text accompanying a tool call is only an internal bridge to
                # the next model step. Streaming it creates a duplicate chat
                # bubble ("để mình kiểm tra...") before the actual answer.
                full_response = await self._stream_final(
                    gateway,
                    response,
                    debug_trace,
                    emit_to_gateway=not bool(response.tool_calls),
                )
                if self.metrics is not None and full_response:
                    self.metrics.increment(
                        f"llm.output_tokens_estimated.{route_key}",
                        max(1, (len(full_response) + 3) // 4),
                    )
                if catalog_policy_adjusted:
                    # Do not replay or persist the unsupported answer that the
                    # guard replaced with an evidence-gathering tool call.
                    full_response = ""

                if not response.tool_calls:
                    if not full_response.strip():
                        if workout_structured is not None:
                            full_response = str(workout_structured.get("text") or "")
                        elif plan_structured is not None:
                            full_response = str(plan_structured.get("text") or "")
                        elif nutrition_structured is not None:
                            full_response = str(nutrition_structured.get("text") or "")
                    if validate_before_output and inference_decision is not None:
                        validation = validate_answer(
                            full_response,
                            validators=inference_decision.validators,
                            tool_results=all_tool_results,
                            user_text=user_text,
                        )
                        if self.metrics is not None:
                            self.metrics.increment(
                                "validator.pass" if validation.passed else "validator.failure"
                            )
                        if not validation.passed:
                            full_response = validation.correction or full_response
                            await self._record_debug(
                                gateway,
                                debug_trace,
                                "validation",
                                "answer_validators",
                                "ANSWER_CORRECTED",
                                payload={"failure_codes": list(validation.failure_codes)},
                                result="DETERMINISTIC_CORRECTION",
                            )
                            if self.metrics is not None:
                                self.metrics.increment("validator.deterministic_correction")
                        if (
                            full_response.strip()
                            and gateway is not None
                            and hasattr(gateway, "send_token")
                        ):
                            await gateway.send_token(full_response)
                    if pending_dish_action is not None:
                        self.pending_actions.put(pending_dish_action)
                        full_response = self._add_confirmation_invitation(
                            full_response, pending_dish_action.display_name
                        )
                        await self._record_debug(
                            gateway,
                            debug_trace,
                            "action",
                            "pending_user_action",
                            "PENDING_ACTION_CREATED",
                            payload={
                                "action_id": pending_dish_action.action_id,
                                "action_type": pending_dish_action.action_type,
                                "target_id": pending_dish_action.target_id,
                            },
                            correlation_id=pending_dish_action.action_id,
                            result="PENDING_CONFIRMATION",
                        )
                        if gateway is not None and hasattr(gateway, "send_action_state"):
                            await gateway.send_action_state(
                                {
                                    "status": "PENDING_CONFIRMATION",
                                    "label": "Chờ bạn xác nhận món này đã được ăn trước khi ghi nhật ký.",
                                }
                            )
                    if pending_plan_action is not None:
                        self.pending_actions.put(pending_plan_action)
                        full_response = self._add_plan_confirmation_invitation(
                            full_response, pending_plan_action.display_name
                        )
                        await self._record_debug(
                            gateway,
                            debug_trace,
                            "action",
                            "pending_user_action",
                            "PENDING_ACTION_CREATED",
                            payload={
                                "action_id": pending_plan_action.action_id,
                                "action_type": pending_plan_action.action_type,
                                "target_id": pending_plan_action.target_id,
                                "target_identity": pending_plan_action.target_identity,
                            },
                            correlation_id=pending_plan_action.action_id,
                            result="PENDING_CONFIRMATION",
                        )
                        if gateway is not None and hasattr(gateway, "send_action_state"):
                            await gateway.send_action_state(
                                {
                                    "status": "PENDING_CONFIRMATION",
                                    "label": "Chờ bạn xác nhận để lưu đúng phiên bản kế hoạch đang xem.",
                                }
                            )
                    if scope_reply_suffix:
                        full_response = self._append_scope_reply(
                            full_response, scope_reply_suffix
                        )
                        if gateway is not None and hasattr(gateway, "send_token"):
                            await gateway.send_token(f"\n\n{scope_reply_suffix}")
                    if full_response.strip():
                        public_trace.mark_completed()
                        await self._append_turn(
                            session_id,
                            "assistant",
                            full_response,
                            structured_data=nutrition_structured or plan_structured or workout_structured,
                            public_trace=self._public_trace_payload(public_trace),
                        )
                    if gateway is not None:
                        await self._send_done(
                            gateway,
                            full_response,
                            structured_data=nutrition_structured or plan_structured or workout_structured,
                            public_trace=public_trace,
                        )
                    trace.finish(outcome="COMPLETED")
                    self._schedule_memory_update(session_id)
                    return

                msg: dict[str, Any] = {"role": "assistant"}
                if full_response.strip():
                    msg["content"] = full_response
                msg["tool_calls"] = [self._call_to_message(c) for c in response.tool_calls]
                messages.append(msg)

                if gateway is not None and hasattr(gateway, "send_status"):
                    await gateway.send_status("Đang kiểm tra thêm thông tin…")

                for call in response.tool_calls:
                    record_tool_started(public_trace, call.name)
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_CALL",
                        payload=self._debug_tool_call_payload(call),
                        correlation_id=call.id,
                    )
                await self._publish_public_trace(gateway, public_trace)

                dispatch_started_at = time.perf_counter()
                tool_results = await self._dispatch_all(
                    session_id, response.tool_calls, failure_counts
                )
                all_tool_results.extend(tool_results)
                for call in response.tool_calls:
                    trace.capture_tool_call(call.name, call.arguments)

                # A suggest-dish miss may mean either that the dish is absent
                # or that an existing dish failed meal/calorie filters. Verify
                # the complete live catalog first, then use web discovery only
                # after a confirmed zero-match. Synthetic calls are appended to
                # the assistant message so OpenAI conversation history remains
                # structurally valid.
                catalog_fallback_call = self._dish_catalog_fallback_call(
                    response.tool_calls, tool_results
                )
                if catalog_fallback_call is not None:
                    catalog_lookup_attempted = True
                    msg["tool_calls"].append(
                        self._call_to_message(catalog_fallback_call)
                    )
                    record_tool_started(public_trace, catalog_fallback_call.name)
                    trace.capture_tool_call(
                        catalog_fallback_call.name,
                        catalog_fallback_call.arguments,
                    )
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_CALL",
                        payload=self._debug_tool_call_payload(catalog_fallback_call),
                        correlation_id=catalog_fallback_call.id,
                    )
                    await self._publish_public_trace(gateway, public_trace)
                    catalog_fallback_result = await self.dispatcher.dispatch(
                        session_id, catalog_fallback_call, self.tool_timeout_ms
                    )
                    tool_results.append(
                        (catalog_fallback_call, catalog_fallback_result)
                    )
                    all_tool_results.append(
                        (catalog_fallback_call, catalog_fallback_result)
                    )

                fallback_calls = list(response.tool_calls)
                if catalog_fallback_call is not None:
                    fallback_calls.append(catalog_fallback_call)
                web_fallback_call = self._recipe_web_fallback_call(
                    fallback_calls, tool_results, user_text=user_text
                )
                if web_fallback_call is not None:
                    msg["tool_calls"].append(
                        self._call_to_message(web_fallback_call)
                    )
                    record_tool_started(public_trace, web_fallback_call.name)
                    trace.capture_tool_call(
                        web_fallback_call.name, web_fallback_call.arguments
                    )
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_CALL",
                        payload=self._debug_tool_call_payload(web_fallback_call),
                        correlation_id=web_fallback_call.id,
                    )
                    await self._publish_public_trace(gateway, public_trace)
                    web_fallback_result = await self.dispatcher.dispatch(
                        session_id, web_fallback_call, self.tool_timeout_ms
                    )
                    tool_results.append((web_fallback_call, web_fallback_result))
                    all_tool_results.append((web_fallback_call, web_fallback_result))

                if gateway is not None and hasattr(gateway, "send_status"):
                    await gateway.send_status("Đang hoàn tất câu trả lời…")

                for call, result in tool_results:
                    trace.capture_tool_result(call.name, result)
                    record_tool_result(public_trace, call.name, ok=result.ok)
                    await self._record_debug(
                        gateway,
                        debug_trace,
                        "tool",
                        "tool_dispatcher",
                        "TOOL_RESULT",
                        payload=self._debug_tool_result_payload(call, result),
                        correlation_id=call.id,
                        latency_ms=elapsed_ms(dispatch_started_at),
                        result="OK" if result.ok else "ERROR",
                    )
                    if call.name in {
                        "build_personalized_workout",
                        "suggest_workout",
                    } and result.ok and isinstance(result.data, dict):
                        presentation = result.data.get("presentation")
                        if isinstance(presentation, dict) and presentation.get("type") == "personalized_workout":
                            workout_structured = presentation
                            trace.capture_workout_integration(result.data, presentation_path="DETERMINISTIC_CARD")
                    if call.name in {
                        "build_nutrition_plan",
                        "build_workout_schedule",
                        "get_plan",
                        "get_active_plan_v2",
                        "revise_plan",
                    } and result.ok and isinstance(result.data, dict):
                        presentation = result.data.get("presentation")
                        if isinstance(presentation, dict) and presentation.get("type") == "versioned_plan":
                            is_clarification = (
                                result.data.get("status") in {"CLARIFICATION_REQUIRED", "NEEDS_CLARIFICATION", "ERROR"}
                                or "CLARIFICATION_REQUIRED" in result.data.get("reason_codes", [])
                                or (
                                    "days" in presentation
                                    and len(presentation.get("days", [])) == 0
                                    and result.data.get("status") != "READY"
                                )
                            )
                            # Only accept plans that are ready or valid.
                            # Never overwrite an existing valid plan with an unready or empty draft.
                            if not is_clarification:
                                plan_structured = presentation
                    serialized = self._serialize_result(call, result)
                    await self._append_turn(
                        session_id, "tool", serialized,
                        tool_call_id=call.id, tool_name=call.name,
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": call.id, "content": serialized}
                    )
                    ui_message = result.ui_message
                    if isinstance(ui_message, dict):
                        ui_text = ui_message.get("text")
                        structured_data = ui_message.get("structured")
                        if isinstance(ui_text, str) and isinstance(
                            structured_data, dict
                        ):
                            await self._append_turn(
                                session_id,
                                "assistant",
                                ui_text,
                                structured_data=structured_data,
                            )
                    if call.name == "get_user_profile" and result.ok and result.data:
                        if isinstance(user_profile, dict) and isinstance(result.data, dict):
                            user_profile = {**user_profile, **result.data}
                        else:
                            user_profile = result.data
                    if (
                        call.name == "suggest_dish"
                        and result.ok
                        and isinstance(result.data, dict)
                    ):
                        nutrition_structured = await self._maybe_create_n3_shadow_delivery(
                            gateway=gateway,
                            owner_user_id=self._owner_user_id(gateway, user_context),
                            suggestion=result.data,
                            arguments=call.arguments,
                        )
                        pending_dish_action = self.pending_actions.create_dish_log_action(
                            session_id,
                            owner_user_id=self._owner_user_id(gateway, user_context),
                            suggestion=result.data,
                            suggestion_arguments=call.arguments,
                        )
                    if (
                        call.name in {"build_nutrition_plan", "build_workout_schedule", "revise_plan"}
                        and result.ok
                        and isinstance(result.data, dict)
                        and result.data.get("status") == "READY"
                    ):
                        pending_plan_action = self.pending_actions.create_plan_save_action(
                            session_id,
                            owner_user_id=self._owner_user_id(gateway, user_context),
                            plan_payload=result.data,
                        )

                await self._publish_public_trace(gateway, public_trace)

                exact_recipe_reply = self._exact_recipe_web_reply(tool_results)
                if exact_recipe_reply is not None:
                    if self.metrics is not None:
                        self.metrics.increment("inference.deterministic_early_exit")
                    exact_recipe_reply = self._append_scope_reply(
                        exact_recipe_reply, scope_reply_suffix
                    )
                    public_trace.mark_completed()
                    await self._append_turn(
                        session_id,
                        "assistant",
                        exact_recipe_reply,
                        public_trace=self._public_trace_payload(public_trace),
                    )
                    if gateway is not None and hasattr(gateway, "send_token"):
                        await gateway.send_token(exact_recipe_reply)
                    if gateway is not None:
                        await self._send_done(
                            gateway,
                            exact_recipe_reply,
                            structured_data=None,
                            public_trace=public_trace,
                        )
                    trace.finish(outcome="COMPLETED_EXTERNAL_RECIPE_LOOKUP")
                    self._schedule_memory_update(session_id)
                    return

                exact_catalog_reply = self._exact_exercise_catalog_reply(
                    response.tool_calls, tool_results
                )
                if exact_catalog_reply is not None:
                    if self.metrics is not None:
                        self.metrics.increment("inference.deterministic_early_exit")
                    exact_catalog_reply = self._append_scope_reply(
                        exact_catalog_reply, scope_reply_suffix
                    )
                    public_trace.mark_completed()
                    await self._append_turn(
                        session_id,
                        "assistant",
                        exact_catalog_reply,
                        public_trace=self._public_trace_payload(public_trace),
                    )
                    if gateway is not None and hasattr(gateway, "send_token"):
                        await gateway.send_token(exact_catalog_reply)
                    if gateway is not None:
                        await self._send_done(
                            gateway,
                            exact_catalog_reply,
                            structured_data=None,
                            public_trace=public_trace,
                        )
                    trace.finish(outcome="COMPLETED_EXACT_CATALOG_LOOKUP")
                    self._schedule_memory_update(session_id)
                    return

                # Structured planners already return authoritative text and a
                # typed card. A second completion would be billed and then
                # discarded, while also adding a hallucination surface.
                # HOWEVER: A second completion MUST run if:
                # 1. Any tool returned a clarification need or failure.
                # 2. The turn is COMPLEX, contains questions ("?"), or had multiple tool calls.
                # 3. plan_structured is present but has 0 items.
                structured_result = (
                    nutrition_structured or plan_structured or workout_structured
                )
                has_clarification_need = any(
                    not r.ok
                    or (
                        isinstance(r.data, dict)
                        and r.data.get("status")
                        in {
                            "CLARIFICATION_REQUIRED",
                            "NEEDS_CLARIFICATION",
                            "ERROR",
                        }
                    )
                    for _, r in tool_results
                )
                has_conversational_question = (
                    plan.tier == COMPLEX
                    or "?" in user_text
                    or len(tool_results) > 1
                )
                has_valid_items = True
                if plan_structured is not None and "days" in plan_structured:
                    has_valid_items = any(
                        isinstance(d, dict) and bool(d.get("items"))
                        for d in plan_structured.get("days", [])
                    )

                if (
                    isinstance(structured_result, dict)
                    and str(structured_result.get("text") or "").strip()
                    and not has_clarification_need
                    and not has_conversational_question
                    and has_valid_items
                ):
                    if self.metrics is not None:
                        self.metrics.increment("inference.deterministic_early_exit")
                    await self._final_answer_fallback(
                        session_id,
                        llm,
                        messages,
                        gateway,
                        public_trace,
                        debug_trace,
                        workout_structured,
                        pending_dish_action,
                        plan_structured,
                        pending_plan_action,
                        nutrition_structured,
                        scope_reply_suffix,
                        allow_llm_call=False,
                        max_tokens=cost_limits.max_output_tokens,
                        deterministic_reason="STRUCTURED_RESULT_DIRECT",
                    )
                    trace.finish(outcome="COMPLETED_STRUCTURED_WITHOUT_SECOND_LLM")
                    self._schedule_memory_update(session_id)
                    return

                # Refresh the system prompt with anything we just learned about
                # the user so later steps in the same turn stop re-asking.
                if user_profile is not None:
                    messages[0]["content"] = buildSystemPrompt(
                        context.rolling_summary,
                        context.pinned_facts,
                        context.rag_chunks,
                        tool_catalog=tool_schemas,
                        user_profile=user_profile,
                        mode=cost_limits.prompt_mode,
                        relevant_history=getattr(context, "relevant_history", None),
                    )

                # Last permitted step: force a text answer instead of dying on
                # AGENT_LOOP_EXCEEDED, which the user reads as a crash.
                if step == step_budget - 2:
                    messages.append({
                        "role": "user",
                        "content": (
                            "[HỆ THỐNG: Đã đủ dữ liệu. Trả lời người dùng bằng lời ngay bây giờ, "
                            "không gọi thêm tool nào nữa.]"
                        ),
                    })

            # Loop exhausted — make one last tool-free pass so the user still
            # gets a real answer.
            await self._final_answer_fallback(
                session_id,
                llm,
                messages,
                gateway,
                public_trace,
                debug_trace,
                workout_structured,
                pending_dish_action,
                plan_structured,
                pending_plan_action,
                nutrition_structured,
                scope_reply_suffix,
                allow_llm_call=llm_calls < cost_limits.max_llm_calls,
                max_tokens=cost_limits.max_output_tokens,
            )
            trace.finish(outcome="COMPLETED_WITH_FALLBACK")
            self._schedule_memory_update(session_id)

        except LLMUnavailableError as exc:
            quota_exhausted = exc.reason_code == "QUOTA_EXHAUSTED"
            error_code = "LLM_QUOTA_EXHAUSTED" if quota_exhausted else "LLM_UNAVAILABLE"
            trace.finish(outcome=error_code)
            logger.warning("LLM unavailable for session=%s", session_id, exc_info=True)
            if gateway is not None:
                await gateway.send_error(
                    error_code,
                    (
                        "Mình tạm thời chưa thể trả lời vì dịch vụ đang quá tải. Bạn thử lại sau ít phút nhé."
                        if quota_exhausted
                        else "Mình tạm thời chưa thể trả lời. Bạn thử lại sau ít phút nhé."
                    ),
                )
            raise
        except GarbledOutputError:
            trace.finish(outcome="LLM_ERROR")
            logger.warning("Garbled LLM output for session=%s", session_id)
            if gateway is not None:
                await gateway.send_error(
                    "LLM_ERROR",
                    "Mình chưa tạo được câu trả lời rõ ràng. Bạn gửi lại yêu cầu này giúp mình nhé.",
                )
            raise
        finally:
            if not trace.trace.final_context_manifest:
                trace.finish(outcome="ERROR")
            trace.emit()

    # ------------------------------------------------------------- internals
    def _select_llm(self, plan: TurnPlan) -> Any:
        """Return the heavy model for complex turns when one is wired in."""
        if plan.use_heavy_model and self.heavy_llm is not None:
            return self.heavy_llm
        return self.llm

    async def _dispatch_all(
        self,
        session_id: str,
        calls: list[ToolCall],
        failure_counts: dict[str, int],
    ) -> list[tuple[ToolCall, ToolResult]]:
        """Parallelize safe reads while preserving write ordering.

        Identical independent reads share one dispatch. Diversity-sensitive
        dish suggestions are excluded from de-duplication because successive
        calls intentionally produce different candidates. Non-idempotent
        calls form ordering barriers and always execute one by one.
        """

        retry_locks: dict[str, asyncio.Lock] = {}

        async def _run(call: ToolCall) -> tuple[ToolCall, ToolResult]:
            result = await self.dispatcher.dispatch(session_id, call, self.tool_timeout_ms)
            if not result.ok and result.error in _RETRYABLE_ERRORS:
                retry_lock = retry_locks.setdefault(call.name, asyncio.Lock())
                async with retry_lock:
                    if failure_counts.get(call.name, 0) == 0:
                        failure_counts[call.name] = 1
                        logger.info("Retrying tool %s after %s", call.name, result.error)
                        result = await self.dispatcher.dispatch(
                            session_id, call, self.tool_timeout_ms
                        )
            if not result.ok:
                failure_counts[call.name] = failure_counts.get(call.name, 0) + 1
                logger.warning("Tool %s failed: %s", call.name, result.error)
            return call, result

        def _parallel_safe(call: ToolCall) -> bool:
            get_tool = getattr(self.tools, "get", None)
            descriptor = get_tool(call.name) if callable(get_tool) else None
            if descriptor is not None and hasattr(descriptor, "idempotent"):
                return bool(descriptor.idempotent)
            return call.name not in _NON_IDEMPOTENT_TOOL_NAMES

        async def _run_read_batch(
            batch: list[ToolCall],
        ) -> list[tuple[ToolCall, ToolResult]]:
            tasks: dict[str, asyncio.Task[tuple[ToolCall, ToolResult]]] = {}
            keys: list[str] = []
            for call in batch:
                arguments = json.dumps(
                    call.arguments or {}, ensure_ascii=False, sort_keys=True, default=str
                )
                key = f"{call.name}:{arguments}"
                if call.name == "suggest_dish":
                    key = f"{key}:{call.id}"
                keys.append(key)
                if key not in tasks:
                    tasks[key] = asyncio.create_task(_run(call))
            await asyncio.gather(*tasks.values())
            return [
                (call, tasks[key].result()[1])
                for call, key in zip(batch, keys, strict=True)
            ]

        results: list[tuple[ToolCall, ToolResult]] = []
        read_batch: list[ToolCall] = []
        for call in calls:
            if _parallel_safe(call):
                read_batch.append(call)
                continue
            if read_batch:
                results.extend(await _run_read_batch(read_batch))
                read_batch = []
            results.append(await _run(call))
        if read_batch:
            results.extend(await _run_read_batch(read_batch))
        return results

    async def _prefetch_read_facts(
        self,
        *,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]] | None,
        tool_names: tuple[str, ...],
        failure_counts: dict[str, int],
        user_profile: Any,
        trace: ContextTraceRecorder,
        public_trace: PublicReasoningTrace,
        gateway: Any | None,
        debug_trace: DebugTraceBuilder,
        result_collector: list[tuple[ToolCall, ToolResult]],
    ) -> Any:
        offered = {
            str(item.get("function", {}).get("name"))
            for item in (tool_schemas or [])
            if isinstance(item, dict)
        }
        calls: list[ToolCall] = []
        get_tool = getattr(self.tools, "get", None)
        for index, name in enumerate(tool_names):
            if name not in offered or not callable(get_tool):
                continue
            descriptor = get_tool(name)
            schema = getattr(descriptor, "parameters_schema", {}) or {}
            if (
                descriptor is None
                or not bool(getattr(descriptor, "idempotent", False))
                or schema.get("required")
                or (name == "get_user_profile" and user_profile)
            ):
                continue
            calls.append(ToolCall(f"prefetch-{index}-{name}", name, {}))
        if not calls:
            return user_profile

        assistant_message = {
            "role": "assistant",
            "tool_calls": [self._call_to_message(call) for call in calls],
        }
        messages.append(assistant_message)
        for call in calls:
            record_tool_started(public_trace, call.name)
            trace.capture_tool_call(call.name, call.arguments)
        await self._publish_public_trace(gateway, public_trace)

        started = time.perf_counter()
        results = await self._dispatch_all(session_id, calls, failure_counts)
        result_collector.extend(results)
        for call, result in results:
            serialized = self._serialize_result(call, result)
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": serialized}
            )
            trace.capture_tool_result(call.name, result)
            record_tool_result(public_trace, call.name, ok=result.ok)
            if self.metrics is not None:
                self.metrics.increment(
                    "prefetch.hit" if result.ok else "prefetch.failure"
                )
            await self._record_debug(
                gateway,
                debug_trace,
                "tool",
                "prefetch_v2",
                "PREFETCH_RESULT",
                payload=self._debug_tool_result_payload(call, result),
                correlation_id=call.id,
                latency_ms=elapsed_ms(started),
                result="OK" if result.ok else "ERROR",
            )
            if call.name == "get_user_profile" and result.ok and result.data:
                if isinstance(user_profile, dict) and isinstance(result.data, dict):
                    user_profile = {**user_profile, **result.data}
                else:
                    user_profile = result.data
        await self._publish_public_trace(gateway, public_trace)
        return user_profile

    def _dish_catalog_fallback_call(
        self,
        calls: list[ToolCall],
        results: list[tuple[ToolCall, ToolResult]],
    ) -> ToolCall | None:
        """Verify a named suggest-dish miss against the complete live catalog."""

        get_tool = getattr(self.tools, "get", None)
        if not callable(get_tool) or get_tool("search_dish_catalog") is None:
            return None
        for call, result in results:
            if (
                call.name != "suggest_dish"
                or result.ok
                or result.error != "NO_DISH_FOUND"
                or not isinstance(call.arguments, dict)
            ):
                continue
            query = " ".join(str(call.arguments.get("query") or "").split())
            if len(query) < 2:
                continue
            query_key = query.casefold()
            if any(
                catalog_call.name == "search_dish_catalog"
                and isinstance(catalog_call.arguments, dict)
                and " ".join(
                    str(catalog_call.arguments.get("query") or "").split()
                ).casefold()
                == query_key
                for catalog_call in calls
            ):
                continue
            arguments: dict[str, Any] = {
                "query": query,
                "page": 1,
                "page_size": 5,
                "include_details": True,
            }
            restrictions = call.arguments.get("dietary_restrictions")
            if isinstance(restrictions, (list, tuple)):
                arguments["dietary_restrictions"] = list(restrictions)
            exclusions = call.arguments.get("ingredient_exclusions")
            if isinstance(exclusions, (list, tuple)):
                arguments["ingredient_exclusions"] = list(exclusions)
            return ToolCall(
                id=f"{call.id}-dish-catalog-fallback",
                name="search_dish_catalog",
                arguments=arguments,
            )
        return None

    @staticmethod
    def _exact_exercise_catalog_reply(
        calls: list[ToolCall],
        results: list[tuple[ToolCall, ToolResult]],
    ) -> str | None:
        """Render direct exercise lookups without a generative second pass.

        A live model expanded the terse Limber 11 source into invented body
        positions, benefits and a save invitation. Catalog lookup is a read
        operation, so returning the exact stored instruction text is both
        faster and more reliable than asking the model to paraphrase it.
        """

        lookup_names = {call.name for call in calls}
        if "search_exercise_catalog" not in lookup_names:
            return None
        if lookup_names - {"search_exercise_catalog", "get_user_profile"}:
            return None

        lookup = next(
            (
                result
                for call, result in results
                if call.name == "search_exercise_catalog"
            ),
            None,
        )
        if lookup is None or not lookup.ok or not isinstance(lookup.data, dict):
            return None

        data = lookup.data
        scanned = data.get("scanned_count")
        matched = data.get("matched_count")
        rows = data.get("results")
        rows = rows if isinstance(rows, list) else []
        if matched == 0 or not rows:
            scope = f" sau khi quét {scanned} bài" if scanned else ""
            return f"Mình không tìm thấy bài tập này trong dữ liệu ứng dụng{scope}."

        intro_scope = f" sau khi quét {scanned} bài" if scanned else ""
        lines = [f"Mình tìm thấy {matched} kết quả{intro_scope}."]
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("name_en") or "Bài tập").strip()
            source = str(row.get("source") or "dữ liệu ứng dụng").strip()
            lines.append(f"\n**{name}** — nguồn: {source}.")
            if (
                row.get("review_status") == "SOURCE_NORMALIZED_CURATED_FIELDS_UNREVIEWED"
                or row.get("quality_flags")
            ):
                lines.append(
                    "Bản ghi nguồn chưa được duyệt đầy đủ; đây là tra cứu dữ liệu, "
                    "không phải xác nhận bài phù hợp hoặc an toàn riêng cho bạn."
                )
            instructions = row.get("instructions")
            text = (
                instructions.get("text")
                if isinstance(instructions, dict)
                else None
            )
            if isinstance(text, str) and text.strip():
                exact_text = text.strip().replace("```", "'''")
                lines.append(
                    "Nội dung hướng dẫn trong nguồn (giữ nguyên để tránh diễn giải sai):\n"
                    f"```text\n{exact_text}\n```"
                )
            else:
                lines.append(
                    "Thông tin hiện có chưa kèm hướng dẫn thực hiện, nên mình không tự "
                    "thêm các bước có thể thiếu chính xác."
                )
        return "\n".join(lines)

    @staticmethod
    def _exact_recipe_web_reply(
        results: list[tuple[ToolCall, ToolResult]],
    ) -> str | None:
        """Render approved external recipe evidence without another LLM pass.

        Small models have been observed to receive a valid web result and then
        repeat their earlier "catalog không có" refusal. Rendering the typed
        result directly makes the source and verification boundary visible and
        prevents invented nutrition or suitability claims.
        """

        web_result = next(
            (
                result
                for call, result in results
                if call.name == "search_recipe_web"
            ),
            None,
        )
        if (
            web_result is None
            or not web_result.ok
            or not isinstance(web_result.data, dict)
            or web_result.data.get("status")
            not in {"REFERENCE_ONLY_RESULTS", "VERIFIED_SHADOW_RESULTS"}
        ):
            return None
        recipes = web_result.data.get("recipes")
        if not isinstance(recipes, list) or not recipes:
            return None
        recipes = [
            recipe
            for recipe in recipes
            if isinstance(recipe, dict)
            and str(recipe.get("title") or "").strip()
            and str(recipe.get("source") or "").strip()
            and str(recipe.get("source_url") or "").startswith("https://")
            and recipe.get("verification_status")
            in {"REFERENCE_ONLY", "VERIFIED_SHADOW"}
        ]
        if not recipes:
            # A malformed/incomplete tool payload is not safe to expose as an
            # attributed web result; let the normal model error guidance run.
            return None

        requested_query = str(web_result.data.get("requested_query") or "món này").strip()
        instructions_only = web_result.data.get("purpose") == "instructions_only"
        if instructions_only:
            lines = [f"Mình tìm được một cách làm tham khảo cho **{requested_query}**:"]
        else:
            lines = [
                f"Mình chưa có thông tin dinh dưỡng đã kiểm chứng cho **{requested_query}**, "
                "nhưng tìm được một công thức tham khảo:"
            ]
        for recipe in recipes[:3]:
            title = " ".join(str(recipe.get("title") or "Công thức").split())[:120]
            source_id = str(recipe.get("source") or "Nguồn ngoài")
            source_label = {
                "THEMEALDB_OFFICIAL_API": "TheMealDB",
            }.get(source_id, source_id.replace("_", " ").title())
            source_url = str(recipe.get("source_url") or "").strip()
            source_domain = source_url.split("/", 3)[2] if source_url.startswith("https://") else ""
            source = f"{source_label} ({source_domain})" if source_domain else source_label
            lines.append(f"\n**{title}**")
            lines.append(f"Tham khảo từ: {source}.")

            ingredients = recipe.get("ingredients")
            ingredient_names: list[str] = []
            if isinstance(ingredients, list):
                for ingredient in ingredients[:10]:
                    if not isinstance(ingredient, dict):
                        continue
                    text = " ".join(
                        str(
                            ingredient.get("source_text")
                            or ingredient.get("canonical_food_name")
                            or ""
                        ).split()
                    )
                    if text:
                        ingredient_names.append(_friendly_external_ingredient(text[:120]))
            if ingredient_names:
                lines.append("Nguyên liệu chính trong công thức:")
                lines.extend(f"- {name}" for name in ingredient_names)

            if instructions_only:
                instructions = recipe.get("instructions")
                if isinstance(instructions, list):
                    instruction_text = " ".join(
                        " ".join(str(item).split())
                        for item in instructions
                        if str(item).strip()
                    )
                    if instruction_text:
                        excerpt = instruction_text[:700].rstrip()
                        if len(instruction_text) > len(excerpt):
                            excerpt += "…"
                        lines.append("Cách làm được nguồn mô tả ngắn gọn như sau: " + excerpt)

            if recipe.get("verification_status") == "VERIFIED_SHADOW":
                nutrition = recipe.get("calculated_nutrition")
                if isinstance(nutrition, dict):
                    lines.append(
                        "Dinh dưỡng ước tính từ các nguyên liệu đã đối chiếu: "
                        f"{nutrition.get('total_calories')} kcal; "
                        f"protein {nutrition.get('total_protein')} g; "
                        f"carb {nutrition.get('total_carbs')} g; "
                        f"chất béo {nutrition.get('total_fat')} g."
                    )
                lines.append(
                    "Đây vẫn là công thức tham khảo và chưa được thêm vào dữ liệu món ăn "
                    "chính thức của ứng dụng."
                )
            else:
                lines.append("")
                lines.append(
                    "Phần dinh dưỡng và độ phù hợp với dị ứng hoặc chế độ ăn vẫn chưa được "
                    "kiểm chứng, nên mình chưa thể tính calo chính xác hay tự ghi món này "
                    "vào nhật ký."
                )

        return "\n".join(lines) if len(lines) > 1 else None

    def _recipe_web_fallback_call(
        self,
        calls: list[ToolCall],
        results: list[tuple[ToolCall, ToolResult]],
        *,
        user_text: str = "",
    ) -> ToolCall | None:
        """Build a bounded external fallback after canonical catalog lookup.

        A confirmed miss may use an approved recipe source. A matching local
        dish may use that source only for explicitly requested cooking steps
        when the canonical record says those steps are unavailable. External
        prose never replaces canonical nutrition.
        """

        if any(call.name == "search_recipe_web" for call in calls):
            return None
        get_tool = getattr(self.tools, "get", None)
        if not callable(get_tool) or get_tool("search_recipe_web") is None:
            return None

        normalized_user_text = _normalise_intent_text(user_text)
        wants_instructions = any(
            _contains_intent_cue(normalized_user_text, cue)
            for cue in ("cach lam", "cach nau", "huong dan", "cong thuc", "che bien")
        )

        # A direct catalog lookup is the normal path for questions such as
        # "món này có trong ứng dụng không?". Previously only a failed
        # suggest_dish call could reach the approved external recipe source,
        # so a catalog miss stopped too early and local dishes could never get
        # reference cooking instructions.
        for call, result in results:
            if (
                call.name != "search_dish_catalog"
                or not result.ok
                or not isinstance(call.arguments, dict)
                or not isinstance(result.data, dict)
            ):
                continue
            query = " ".join(str(call.arguments.get("query") or "").split())
            if len(query) < 2:
                continue
            matched_count = result.data.get("matched_count")
            if matched_count == 0 and any(
                candidate.name == "suggest_dish"
                and isinstance(candidate.arguments, dict)
                and " ".join(
                    str(candidate.arguments.get("query") or "").split()
                ).casefold()
                == query.casefold()
                for candidate in calls
            ):
                # The suggest_dish branch below carries meal/target context
                # into the external lookup; let it build the richer call.
                continue
            purpose = "catalog_miss"
            if matched_count != 0:
                rows = result.data.get("results")
                lacks_instructions = bool(rows) and all(
                    not isinstance(row, dict) or not row.get("instructions")
                    for row in rows
                )
                if not (wants_instructions and lacks_instructions):
                    continue
                purpose = "instructions_only"
            arguments: dict[str, Any] = {"query": query}
            if purpose == "instructions_only":
                arguments["purpose"] = purpose
            restrictions = call.arguments.get("dietary_restrictions")
            if isinstance(restrictions, (list, tuple)):
                arguments["dietary_restrictions"] = list(restrictions)
            return ToolCall(
                id=f"{call.id}-recipe-web-fallback",
                name="search_recipe_web",
                arguments=arguments,
            )

        for call, result in results:
            if (
                call.name != "suggest_dish"
                or result.ok
                or result.error != "NO_DISH_FOUND"
                or not isinstance(call.arguments, dict)
            ):
                continue
            query = " ".join(str(call.arguments.get("query") or "").split())
            if len(query) < 2:
                continue
            if get_tool("search_dish_catalog") is not None:
                query_key = query.casefold()
                catalog_miss_confirmed = any(
                    catalog_call.name == "search_dish_catalog"
                    and isinstance(catalog_call.arguments, dict)
                    and " ".join(
                        str(catalog_call.arguments.get("query") or "").split()
                    ).casefold()
                    == query_key
                    and catalog_result.ok
                    and isinstance(catalog_result.data, dict)
                    and catalog_result.data.get("matched_count") == 0
                    for catalog_call, catalog_result in results
                )
                if not catalog_miss_confirmed:
                    continue
            arguments: dict[str, Any] = {"query": query}
            meal_type = call.arguments.get("meal_type")
            if isinstance(meal_type, str):
                arguments["meal_type"] = meal_type
            target_kcal = call.arguments.get("target_kcal")
            if isinstance(target_kcal, (int, float)) and not isinstance(target_kcal, bool):
                arguments["target_kcal"] = target_kcal
            restrictions = call.arguments.get("dietary_restrictions")
            if isinstance(restrictions, (list, tuple)):
                arguments["dietary_restrictions"] = list(restrictions)
            return ToolCall(
                id=f"{call.id}-recipe-web-fallback",
                name="search_recipe_web",
                arguments=arguments,
            )
        return None

    async def _final_answer_fallback(
        self,
        session_id: str,
        llm: Any,
        messages: list[dict[str, Any]],
        gateway: Any | None,
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
        workout_structured: dict[str, Any] | None = None,
        pending_dish_action: PendingUserAction | None = None,
        plan_structured: dict[str, Any] | None = None,
        pending_plan_action: PendingUserAction | None = None,
        nutrition_structured: dict[str, Any] | None = None,
        scope_reply_suffix: str | None = None,
        *,
        allow_llm_call: bool = True,
        max_tokens: int | None = None,
        deterministic_reason: str = "PAID_CALL_BUDGET_EXHAUSTED",
    ) -> None:
        """Finish within the paid-call budget, using a fixed reply when spent."""
        messages.append({
            "role": "user",
            "content": (
                "[HỆ THỐNG: Bạn đã dùng hết số bước cho phép. Trả lời người dùng ngay bằng lời, "
                "dựa trên dữ liệu đã thu thập. Không gọi tool.]"
            ),
        })
        text = ""
        if allow_llm_call:
            try:
                llm_started_at = time.perf_counter()
                response = await llm.chat(
                    messages,
                    tools=None,
                    max_tokens=max_tokens,
                )
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "FALLBACK_RESPONSE_RECEIVED",
                    payload={"tool_call_count": len(response.tool_calls or [])},
                    latency_ms=elapsed_ms(llm_started_at),
                    result="OK",
                )
                text = await self._stream_final(gateway, response, debug_trace)
            except (LLMUnavailableError, GarbledOutputError):
                text = ""
        else:
            await self._record_debug(
                gateway,
                debug_trace,
                "cost",
                "llm_cost_governor",
                deterministic_reason,
                payload=None,
                result="DETERMINISTIC_RESPONSE",
            )

        if not text.strip():
            if workout_structured is not None:
                text = str(workout_structured.get("text") or "")
            elif plan_structured is not None:
                text = str(plan_structured.get("text") or "")
            elif nutrition_structured is not None:
                text = str(nutrition_structured.get("text") or "")
            elif not text.strip():
                text = (
                    "Mình chưa lấy đủ thông tin để trả lời chính xác. "
                    "Bạn gửi lại yêu cầu này giúp mình nhé."
                )
                if gateway is not None:
                    await gateway.send_token(text)

        if pending_dish_action is not None:
            self.pending_actions.put(pending_dish_action)
            text = self._add_confirmation_invitation(
                text, pending_dish_action.display_name
            )
            await self._record_debug(
                gateway,
                debug_trace,
                "action",
                "pending_user_action",
                "PENDING_ACTION_CREATED",
                payload={
                    "action_id": pending_dish_action.action_id,
                    "action_type": pending_dish_action.action_type,
                    "target_id": pending_dish_action.target_id,
                },
                correlation_id=pending_dish_action.action_id,
                result="PENDING_CONFIRMATION",
            )
        if pending_plan_action is not None:
            self.pending_actions.put(pending_plan_action)
            text = self._add_plan_confirmation_invitation(
                text, pending_plan_action.display_name
            )
            await self._record_debug(
                gateway,
                debug_trace,
                "action",
                "pending_user_action",
                "PENDING_ACTION_CREATED",
                payload={
                    "action_id": pending_plan_action.action_id,
                    "action_type": pending_plan_action.action_type,
                    "target_id": pending_plan_action.target_id,
                    "target_identity": pending_plan_action.target_identity,
                },
                correlation_id=pending_plan_action.action_id,
                result="PENDING_CONFIRMATION",
            )

        if scope_reply_suffix:
            text = self._append_scope_reply(text, scope_reply_suffix)
            if gateway is not None and hasattr(gateway, "send_token"):
                await gateway.send_token(f"\n\n{scope_reply_suffix}")

        public_trace.mark_completed()
        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=nutrition_structured or plan_structured or workout_structured,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=nutrition_structured or plan_structured or workout_structured,
                public_trace=public_trace,
            )

    async def _resolve_pending_user_action(
        self,
        session_id: str,
        action: PendingUserAction,
        gateway: Any | None,
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
    ) -> None:
        """Execute the exact stored action without asking the LLM again."""

        public_trace.add("CONFIRMATION_RECEIVED")
        record_tool_started(public_trace, action.tool_name)
        call = ToolCall(
            id=action.action_id,
            name=action.tool_name,
            arguments=action.tool_arguments,
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "USER_CONFIRMATION",
            payload={"affirmative": True, "target_id": action.target_id},
            correlation_id=action.action_id,
            result="CONFIRMED",
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "ACTION_RESOLUTION",
            payload={
                "action_id": action.action_id,
                "action_type": action.action_type,
                "target_id": action.target_id,
            },
            correlation_id=action.action_id,
            result="CONFIRMED",
        )
        await self._record_debug(
            gateway,
            debug_trace,
            "tool",
            "tool_dispatcher",
            "TOOL_CALL",
            payload=self._debug_tool_call_payload(call),
            correlation_id=action.action_id,
        )
        started_at = time.perf_counter()
        result = await self.dispatcher.dispatch(session_id, call, self.tool_timeout_ms)
        record_tool_result(public_trace, action.tool_name, ok=result.ok)
        await self._record_debug(
            gateway,
            debug_trace,
            "persistence",
            "tool_dispatcher",
            "DB_WRITE",
            payload=self._debug_tool_result_payload(call, result),
            correlation_id=action.action_id,
            latency_ms=elapsed_ms(started_at),
            result="PERSISTED" if result.ok else "NOT_PERSISTED",
        )

        structured_data: dict[str, Any] | None = None
        result_data = result.data if isinstance(result.data, dict) else {}
        identity = self._pending_action_identity(action, result)
        identity_verified = identity["verified"]
        if identity_verified and self.pending_actions.complete(
            action,
            persisted_reference_id=str(identity["persisted_reference_id"]),
        ):
            await self._record_debug(
                gateway,
                debug_trace,
                "persistence",
                "tool_dispatcher",
                "READ_BACK",
                payload={
                    "target_id": action.target_id,
                    **identity["debug_references"],
                },
                correlation_id=action.action_id,
                result="IDENTITY_VERIFIED",
            )
            public_trace.mark_completed()
            if action.action_type == "SAVE_PLAN_REVISION" and result_data.get("write_status") == "SHADOW_SAVED":
                text = (
                    f"Mình đã ghi nhận {action.display_name} để bạn xem thử. "
                    "Kế hoạch bạn đang dùng vẫn chưa thay đổi."
                )
            elif action.action_type == "SAVE_PLAN_REVISION":
                text = f"Đã lưu {action.display_name}."
            else:
                text = f"Đã lưu {action.display_name} vào nhật ký của bạn."
            if isinstance(result.ui_message, dict):
                candidate = result.ui_message.get("structured")
                if isinstance(candidate, dict):
                    structured_data = candidate
            if structured_data is None:
                candidate = result_data.get("presentation")
                if isinstance(candidate, dict) and candidate.get("type") == "versioned_plan":
                    structured_data = candidate
            state = {
                "status": "PERSISTED",
                "label": "Đã lưu lựa chọn bạn vừa xác nhận.",
            }
        else:
            # A write acknowledgement without the catalogue identity chain is
            # deliberately not presented as saved. Release the claim so the
            # user can retry after the client reports a real persistence error.
            self.pending_actions.release(action)
            public_trace.mark_clarification_required()
            if result.ok:
                text = (
                    f"Mình chưa xác minh được {action.display_name} đã được lưu đúng. "
                    "Bạn vui lòng thử lại nhé."
                )
            else:
                text = (
                    f"Mình chưa thể lưu {action.display_name}. "
                    "Bạn có thể xác nhận lại hoặc thử lại sau nhé."
                )
            state = {
                "status": "NOT_PERSISTED",
                "label": "Chưa lưu được lựa chọn đã xác nhận.",
            }

        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=structured_data,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None and hasattr(gateway, "send_action_state"):
            await gateway.send_action_state(state)
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=structured_data,
                public_trace=public_trace,
            )

    async def _respond_to_pending_resolution(
        self,
        session_id: str,
        resolution: PendingActionResolution,
        gateway: Any | None,
        public_trace: PublicReasoningTrace,
        debug_trace: DebugTraceBuilder,
    ) -> None:
        """Reply safely to a terminal or ambiguous confirmation attempt.

        These branches intentionally do not invoke the LLM or dispatcher. A
        plain confirmation must never select an arbitrary pending write.
        """

        action = resolution.action
        await self._record_debug(
            gateway,
            debug_trace,
            "action",
            "pending_user_action",
            "ACTION_RESOLUTION",
            payload={
                "status": resolution.status,
                "target_id": action.target_id if action is not None else None,
            },
            correlation_id=action.action_id if action is not None else None,
            result=resolution.status,
        )
        structured_data: dict[str, Any] | None = None
        if resolution.status == "ALREADY_EXECUTED":
            public_trace.add("CONFIRMATION_RECEIVED")
            public_trace.add("PERSISTENCE_CONFIRMED")
            public_trace.mark_completed()
            text = "Lựa chọn này đã được lưu trước đó, nên mình không ghi thêm lần nữa."
            state = {
                "status": "ALREADY_EXECUTED",
                "label": "Lựa chọn này đã được lưu trước đó.",
            }
        elif resolution.status == "REJECTED":
            public_trace.mark_completed()
            display_name = action.display_name if action is not None else "lựa chọn này"
            text = f"Được, mình sẽ không lưu {display_name}."
            state = {
                "status": "CANCELLED",
                "label": "Đã hủy lựa chọn đang chờ xác nhận.",
            }
        elif resolution.status == "IN_PROGRESS":
            public_trace.add("CONFIRMATION_RECEIVED")
            public_trace.add("PERSISTENCE_IN_PROGRESS")
            text = "Lựa chọn này đang được lưu. Mình sẽ không tạo thêm một bản ghi nữa."
            state = {
                "status": "IN_PROGRESS",
                "label": "Đang lưu lựa chọn bạn vừa xác nhận.",
            }
        elif resolution.status == "AMBIGUOUS":
            public_trace.mark_clarification_required()
            text = (
                "Bạn đang có vài lựa chọn chờ xác nhận. Hãy nói rõ món ăn, bài tập hoặc "
                "kế hoạch bạn muốn lưu nhé."
            )
            state = {
                "status": "CLARIFICATION_REQUIRED",
                "label": "Cần xác định rõ lựa chọn cần lưu.",
            }
        elif resolution.status == "ACTION_EXPIRED":
            public_trace.mark_clarification_required()
            text = "Xác nhận này đã hết hạn. Bạn hãy yêu cầu gợi ý lại để mình kiểm tra thông tin mới nhất nhé."
            state = {
                "status": "ACTION_EXPIRED",
                "label": "Lựa chọn chờ xác nhận đã hết hạn.",
            }
        else:  # OWNER_MISMATCH and future non-action statuses
            public_trace.mark_clarification_required()
            text = "Mình không tìm thấy lựa chọn chờ xác nhận cho phiên này. Bạn hãy yêu cầu lại nếu vẫn muốn lưu nhé."
            state = {
                "status": "NO_PENDING_ACTION",
                "label": "Không có lựa chọn phù hợp để lưu.",
            }

        await self._append_turn(
            session_id,
            "assistant",
            text,
            structured_data=structured_data,
            public_trace=self._public_trace_payload(public_trace),
        )
        if gateway is not None and hasattr(gateway, "send_action_state"):
            await gateway.send_action_state(state)
        if gateway is not None:
            await self._send_done(
                gateway,
                text,
                structured_data=structured_data,
                public_trace=public_trace,
            )

    @staticmethod
    async def _maybe_create_n3_shadow_delivery(
        *,
        gateway: Any | None,
        owner_user_id: str,
        suggestion: dict[str, Any],
        arguments: Any,
    ) -> dict[str, Any] | None:
        """Attach a safe N3.2.1 card to a trusted canonical dish read.

        ``suggest_dish`` remains the production recommendation. This helper is
        invoked only when the explicit development/shadow flag and an
        authenticated chat principal are present; it observes and records a
        separate shadow recommendation event and cannot alter the tool result.
        """

        if (
            not settings.adaptive_recommendation_shadow_enabled
            or gateway is None
            or not bool(getattr(gateway, "authenticated_principal", False))
            or not owner_user_id
            or owner_user_id == "anonymous"
        ):
            return None
        try:
            application = getattr(getattr(gateway, "websocket", None), "app", None)
            repository = getattr(getattr(application, "state", None), "adaptive_recipe_repository", None)
            store = getattr(getattr(application, "state", None), "adaptive_feedback_store", None)
            if repository is None or store is None:
                return None
            from datetime import datetime, timezone
            from uuid import uuid4

            from modules.nutrition.adaptive.contracts import ConstraintContext
            from modules.nutrition.adaptive.delivery import (
                TrustedDeliveryError,
                canonical_catalog_reference,
                structured_chat_payload,
                validate_candidate_for_exposure,
            )
            from modules.nutrition.adaptive.intelligence import (
                RecommendationContext,
                RecommendationMemoryEntry,
                RecommendationRankerV2,
                features_for,
            )

            candidate = repository.register_trusted_delivery_reference(
                canonical_catalog_reference(suggestion)
            )
            tool_arguments = arguments if isinstance(arguments, dict) else {}
            context = RecommendationContext(
                owner_user_id=owner_user_id,
                baseline_ranked_candidate_ids=(candidate.candidate_id,),
                constraints=ConstraintContext(
                    dietary_exclusions=frozenset(tool_arguments.get("dietary_restrictions") or ()),
                    target_kcal=tool_arguments.get("target_kcal"),
                ),
                meal_type=tool_arguments.get("meal_type"),
                recent_recommendations=await store.recent_recommendations(
                    owner_user_id=owner_user_id
                ),
            )
            eligibility = repository.ranking_eligibility_gate()
            ranked = RecommendationRankerV2(eligibility_gate=eligibility).rank(
                (candidate,),
                context=context,
                preference_profile=await store.preference_profile(owner_user_id=owner_user_id),
            )
            if not ranked:
                return None
            selected = ranked[0]
            validate_candidate_for_exposure(selected, owner_user_id=owner_user_id,
                                            gate=eligibility, constraints=context.constraints)
            recommendation_event_id = str(uuid4())
            features = features_for(selected.candidate)
            entry = RecommendationMemoryEntry(
                recommendation_id=recommendation_event_id,
                owner_user_id=owner_user_id,
                candidate_id=selected.candidate.candidate_id,
                dish=selected.candidate.title,
                source_type=selected.source_type,
                shown_at=datetime.now(timezone.utc),
                selected_policy=selected.policy_version,
                context_fingerprint=context.fingerprint(),
                feature_payload={
                    "dish": features.dish,
                    "ingredients": list(features.ingredients),
                    "primary_protein": features.primary_protein,
                    "cuisine": features.cuisine,
                    "preparation": features.preparation,
                    "cooking_effort": features.cooking_effort,
                    "budget_band": features.budget_band,
                },
            )
            # Persist/read back before emitting a feedback-eligible card. A
            # durable store failure therefore suppresses only shadow UI, never
            # the authoritative canonical dish result.
            persisted = await store.persist_delivery(entry)
            repository.record_recommendation(persisted)
            return structured_chat_payload(
                selected,
                recommendation_event_id,
                meal_type=context.meal_type,
            )
        except (TrustedDeliveryError, ValueError):
            logger.warning("N3.2.1 trusted shadow delivery skipped: invalid canonical tool result")
        except Exception:
            # Shadow observation must never degrade the authoritative dish
            # response. Fail closed: no feedback card is emitted on error.
            logger.warning("N3.2.1 trusted shadow delivery skipped", exc_info=True)
        return None

    @staticmethod
    def _owner_user_id(gateway: Any | None, user_context: Any | None) -> str:
        """Resolve a stable principal for pending-action ownership.

        Authenticated gateway identity wins over caller-provided context. The
        anonymous fallback keeps local/offline development deterministic while
        still binding the action to a single session.
        """

        gateway_user_id = getattr(gateway, "user_id", None) if gateway is not None else None
        if isinstance(gateway_user_id, str) and gateway_user_id.strip():
            return gateway_user_id.strip()
        if isinstance(user_context, dict):
            for key in ("user_id", "id"):
                value = user_context.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return "anonymous"

    @staticmethod
    def _add_confirmation_invitation(text: str, display_name: str) -> str:
        invitation = (
            f"Bạn có xác nhận đã ăn **{display_name}** và muốn ghi vào nhật ký không?"
        )
        if invitation in text:
            return text
        return f"{text.rstrip()}\n\n{invitation}".strip()

    @staticmethod
    def _add_plan_confirmation_invitation(text: str, display_name: str) -> str:
        invitation = f"Bạn có muốn lưu đúng **{display_name}** này không?"
        if invitation in text:
            return text
        return f"{text.rstrip()}\n\n{invitation}".strip()

    def _pending_action_identity(
        self, action: PendingUserAction, result: ToolResult
    ) -> dict[str, Any]:
        """Verify a stored action against its domain-specific read-back chain."""

        data = result.data if isinstance(result.data, dict) else {}
        if action.action_type == "SAVE_PLAN_REVISION":
            expected = action.target_identity
            persisted = {
                "plan_id": data.get("plan_id"),
                "revision_id": data.get("revision_id"),
                "revision_content_hash": data.get("revision_content_hash"),
            }
            read_back = {
                "plan_id": data.get("read_back_plan_id"),
                "revision_id": data.get("read_back_revision_id"),
                "revision_content_hash": data.get("read_back_revision_content_hash"),
            }
            verified = (
                result.ok
                and data.get("write_status") in {"SHADOW_SAVED", "PERSISTED"}
                and expected == persisted
                and expected == read_back
            )
            return {
                "verified": verified,
                "persisted_reference_id": read_back.get("revision_id"),
                "debug_references": {
                    "expected_plan_id": expected.get("plan_id"),
                    "expected_revision_id": expected.get("revision_id"),
                    "persisted_plan_id": persisted.get("plan_id"),
                    "persisted_revision_id": persisted.get("revision_id"),
                    "read_back_plan_id": read_back.get("plan_id"),
                    "read_back_revision_id": read_back.get("revision_id"),
                },
            }
        persisted_id = data.get("catalog_dish_id")
        read_back_id = data.get("read_back_catalog_dish_id")
        card_id = self._structured_card_catalog_dish_id(result.ui_message)
        return {
            "verified": (
                result.ok
                and persisted_id == action.target_id
                and read_back_id == action.target_id
                and card_id == action.target_id
            ),
            "persisted_reference_id": read_back_id,
            "debug_references": {
                "persisted_reference_id": persisted_id,
                "read_back_reference_id": read_back_id,
                "card_reference_id": card_id,
            },
        }

    def _schedule_memory_update(self, session_id: str) -> None:
        """Consolidate memory in the background once a turn is answered.

        Fire-and-forget: the user already has their reply, and a summarisation
        failure must never surface as a chat error. A strong reference to the
        task is kept so the event loop does not garbage-collect it mid-flight.
        """
        updater = getattr(self.memory, "updateRollingSummary", None)
        if updater is None or session_id in self._memory_updates_in_flight:
            if updater is not None and self.metrics is not None:
                self.metrics.increment("memory.jobs_coalesced")
            return

        self._memory_updates_in_flight.add(session_id)

        async def _run() -> None:
            try:
                if self.metrics is not None:
                    self.metrics.increment("memory.jobs_started")
                if self.memory_semaphore is None:
                    await updater(session_id, self.llm)
                else:
                    async with self.memory_semaphore:
                        await updater(session_id, self.llm)
                if self.metrics is not None:
                    self.metrics.increment("memory.jobs_completed")
            except Exception as exc:  # pragma: no cover - best effort by design
                if self.metrics is not None:
                    self.metrics.increment("memory.jobs_failed")
                logger.debug("Background memory update skipped: %s", exc)
            finally:
                self._memory_updates_in_flight.discard(session_id)

        try:
            task = asyncio.create_task(_run())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            self._memory_updates_in_flight.discard(session_id)

    def _build_messages(
        self,
        context: Any,
        user_text: str,
        plan: TurnPlan | None = None,
        user_profile: Any = None,
        tool_catalog: Any = None,
        prompt_mode: str | None = None,
        history_turn_limit: int | None = None,
    ) -> list[dict[str, Any]]:
        plan = plan or classify_turn(user_text, history_len=len(context.history))
        prompt = buildSystemPrompt(
            context.rolling_summary,
            context.pinned_facts,
            context.rag_chunks,
            tool_catalog=(
                tool_catalog
                if tool_catalog is not None
                else self.tools if plan.offer_tools else None
            ),
            user_profile=user_profile,
            mode=prompt_mode or plan.prompt_mode,
            relevant_history=getattr(context, "relevant_history", None),
        )

        messages: list[dict[str, Any]] = [{"role": "system", "content": prompt}]

        # Persisted history cannot reconstruct the assistant.tool_calls object,
        # so replaying a stored ``role=tool`` turn would create an orphan tool
        # message rejected by strict OpenAI-compatible providers. The final
        # assistant answer and rolling summary retain the user-facing facts.
        # Cost limits count model-visible conversational turns, not database
        # rows. Tool results and scope-firewall markers can otherwise consume
        # the whole window before they are discarded, making short replies
        # such as "oke" look like a brand-new conversation.
        history = [
            turn
            for turn in context.history
            if turn.tool_name not in SCOPE_GUARD_HISTORY_MARKERS
            and turn.role in {"user", "assistant"}
        ]
        if history_turn_limit is not None:
            visible_limit = max(0, history_turn_limit)
            history = history[-visible_limit:] if visible_limit else []
        for turn in history:
            msg: dict[str, Any] = {"role": turn.role, "content": turn.content}
            messages.append(msg)
        messages.append({"role": "user", "content": user_text})
        return messages

    async def _stream_final(
        self,
        gateway: Any | None,
        response: Any,
        debug_trace: DebugTraceBuilder,
        *,
        emit_to_gateway: bool = True,
    ) -> str:
        chunks: list[str] = []
        if response.content_stream is None:
            return response.full_text or ""
        async for token in response.content_stream:
            provider_event_type = classify_provider_token(token)
            if provider_event_type == "INTERNAL_REASONING":
                # Provider reasoning/scratchpad is never sent to or persisted
                # for the user. Public steps come from trusted app events.
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "INTERNAL_REASONING_DROPPED",
                    payload={"provider_event_type": provider_event_type},
                    result="DROPPED",
                )
                continue
            if provider_event_type != "VISIBLE_CONTENT":
                # The adapter has no provider-declared display-safe reasoning
                # summary contract today. Keep metadata for debug, but never
                # pass an unverified provider field into the public channel.
                await self._record_debug(
                    gateway,
                    debug_trace,
                    "provider",
                    "llm_adapter",
                    "TOKEN_USAGE" if provider_event_type == "USAGE" else "PROVIDER_EVENT",
                    payload={"provider_event_type": provider_event_type},
                    result="OBSERVED",
                )
                continue
            else:
                chunks.append(str(token))
                if (
                    emit_to_gateway
                    and gateway is not None
                    and hasattr(gateway, "send_token")
                ):
                    await gateway.send_token(str(token))
        return "".join(chunks) or response.full_text or ""

    @staticmethod
    def _append_scope_reply(text: str, suffix: str | None) -> str:
        if not suffix or suffix in text:
            return text
        return f"{text.rstrip()}\n\n{suffix}" if text.strip() else suffix

    async def _append_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        thoughts: str = "",
        structured_data: dict[str, Any] | None = None,
        public_trace: dict[str, Any] | None = None,
    ) -> None:
        append = getattr(self.session_store, "appendTurn", None)
        if append is not None:
            result = append(
                session_id,
                role,
                content,
                tool_call_id,
                tool_name,
                thoughts,
                structured_data,
                public_trace,
            )
            if hasattr(result, "__await__"):
                await result
            return
        append = getattr(self.session_store, "append_turn", None)
        if append is not None:
            append(
                session_id,
                role,
                content,
                tool_call_id,
                tool_name,
                thoughts,
                structured_data,
                public_trace,
            )

    @staticmethod
    async def _publish_public_trace(
        gateway: Any | None, public_trace: PublicReasoningTrace
    ) -> None:
        if (
            gateway is not None
            and public_trace.steps
            and hasattr(gateway, "send_public_trace")
        ):
            await gateway.send_public_trace(public_trace.to_dict())

    @staticmethod
    def _public_trace_payload(
        public_trace: PublicReasoningTrace,
    ) -> dict[str, Any] | None:
        return public_trace.to_dict() if public_trace.steps else None

    @staticmethod
    async def _record_debug(
        gateway: Any | None,
        debug_trace: DebugTraceBuilder,
        category: str,
        component: str,
        operation: str,
        *,
        payload: Any = None,
        correlation_id: str | None = None,
        latency_ms: float | None = None,
        result: str | None = None,
    ) -> None:
        event = debug_trace.record(
            category,
            component,
            operation,
            payload=payload,
            correlation_id=correlation_id,
            latency_ms=latency_ms,
            result=result,
        )
        if event is not None and gateway is not None and hasattr(gateway, "send_debug_trace"):
            await gateway.send_debug_trace(event.to_dict())

    @staticmethod
    def _debug_tool_call_payload(call: ToolCall) -> dict[str, Any]:
        """Expose tool execution shape without copying user/profile payloads."""

        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        safe_argument_keys = {
            "meal_type",
            "target_kcal",
            "serving_grams",
            "catalog_dish_id",
            "duration_min",
            "plan_id",
            "revision_id",
            "expected_revision_number",
            "operation",
            "domain",
            "period_start",
            "period_end",
            "timezone",
        }
        safe_arguments = {
            key: value
            for key, value in arguments.items()
            if key in safe_argument_keys and isinstance(value, (str, bool, int, float))
        }
        payload: dict[str, Any] = {
            "name": call.name,
            "argument_keys": sorted(str(key) for key in arguments),
        }
        if safe_arguments:
            payload["sanitized_arguments"] = safe_arguments
        catalog_dish_id = arguments.get("catalog_dish_id")
        if isinstance(catalog_dish_id, str) and catalog_dish_id:
            payload["target_id"] = catalog_dish_id
        return payload

    @staticmethod
    def _structured_card_catalog_dish_id(ui_message: Any) -> str | None:
        """Read the reference displayed in a structured meal card, if any."""

        if not isinstance(ui_message, dict):
            return None
        structured = ui_message.get("structured")
        if not isinstance(structured, dict):
            return None
        actions = structured.get("actions")
        if not isinstance(actions, list):
            return None
        card_ids = {
            str(details.get("catalog_dish_id"))
            for action in actions
            if isinstance(action, dict)
            and isinstance((details := action.get("details")), dict)
            and isinstance(details.get("catalog_dish_id"), str)
            and details.get("catalog_dish_id")
        }
        return next(iter(card_ids)) if len(card_ids) == 1 else None

    @staticmethod
    def _debug_tool_result_payload(call: ToolCall, result: ToolResult) -> dict[str, Any]:
        """Expose only result state and safe reference identifiers in debug."""

        data = result.data if isinstance(result.data, dict) else {}
        payload: dict[str, Any] = {
            "name": call.name,
            "ok": result.ok,
            "result_keys": sorted(str(key) for key in data),
        }
        if result.error:
            payload["error_code"] = result.error
        for key in (
            "write_status", "meal_record_status", "catalog_dish_id", "read_back_catalog_dish_id",
            "plan_id", "revision_id", "read_back_plan_id", "read_back_revision_id",
            "lifecycle_status", "status",
        ):
            value = data.get(key)
            if isinstance(value, (str, bool, int, float)):
                payload[key] = value
        return payload

    @staticmethod
    async def _send_done(
        gateway: Any,
        full_response: str,
        *,
        structured_data: dict[str, Any] | None,
        public_trace: PublicReasoningTrace,
    ) -> None:
        await gateway.send_done(
            full_response,
            structured_data=structured_data,
            public_trace=AgentOrchestrator._public_trace_payload(public_trace),
        )

    @staticmethod
    def _call_to_message(call: ToolCall) -> dict[str, Any]:
        """Render a ToolCall as an OpenAI ``assistant.tool_calls`` entry.

        Two details matter and were previously wrong:

        - ``type`` is required by the API schema.
        - ``arguments`` must be a JSON *string*, not an object. Sending a dict
          makes strict providers reject the whole request with HTTP 400
          (``BAD_REQUEST``), which surfaced to users as LLM_UNAVAILABLE on the
          second agent step — i.e. every turn that actually used a tool.
          Lenient providers accepted it, which is why this went unnoticed.
        """
        arguments = call.arguments
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {}, ensure_ascii=False)
        return {
            "id": call.id,
            "type": "function",
            "function": {"name": call.name, "arguments": arguments},
        }

    @staticmethod
    def _serialize_result(call: ToolCall, result: ToolResult) -> str:
        """Serialise a tool result, attaching recovery guidance on failure."""
        if result.ok:
            specific = _SUCCESS_RESULT_GUIDANCE.get(call.name)
            guidance = (
                f"{_DEFAULT_SUCCESS_GUIDANCE} {specific}"
                if specific
                else _DEFAULT_SUCCESS_GUIDANCE
            )
            return json.dumps(
                {
                    "ok": True,
                    "data": result.data,
                    "huong_dan_tra_loi": guidance,
                },
                ensure_ascii=False,
            )
        code = result.error or "TOOL_INTERNAL_ERROR"
        return json.dumps(
            {
                "ok": False,
                "error": code,
                "tool": call.name,
                "data": result.data,
                "huong_dan": (
                    _ERROR_RESPONSE_CONTRACT
                    + _ERROR_GUIDANCE.get(code, _ERROR_GUIDANCE["TOOL_INTERNAL_ERROR"])
                ),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _summarize_result(result: ToolResult) -> str:
        if not result.ok:
            return result.error or "ERROR"
        text = json.dumps(result.data, ensure_ascii=False)
        return text[:200]


__all__ = ["AgentOrchestrator"]
