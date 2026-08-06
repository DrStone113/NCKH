from __future__ import annotations

import sys
from pathlib import Path
import pytest

# Thêm thư mục gốc của backend vào sys.path để import các module dịch vụ
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.agent.tools.dish import suggest_dish, _remove_accents
from services.agent.tools.workout import suggest_workout
from services.agent.tool_dispatcher import ToolDispatcher
from services.agent.tool_registry import ToolRegistry, ToolDescriptor
from services.agent.llm_client import ToolCall
from services.agent.system_prompt import buildSystemPrompt


# ===========================================================================
# Level 1 (Basic) Unit Tests
# ===========================================================================

def test_suggest_dish_basic():
    """TC-1.1: Gợi ý món ăn khỏe mạnh cơ bản theo meal_type và target_kcal."""
    # Bữa tối mục tiêu 700 kcal
    result = suggest_dish(meal_type="dinner", target_kcal=700.0)
    assert result is not None
    assert "id" in result
    assert "name" in result
    assert 700.0 * 0.7 <= result["total_calories"] <= 700.0 * 1.5
    assert len(result["components"]) >= 1


def test_suggest_dish_query_matching():
    """TC-1.1/TC-1.4: Tìm kiếm theo từ khóa có dấu và không dấu."""
    # Tìm kiếm có dấu
    result_with_accent = suggest_dish(meal_type="lunch", target_kcal=600.0, query="cơm")
    assert "cơm" in result_with_accent["name"].lower()

    # Tìm kiếm không dấu (accent-insensitive)
    result_no_accent = suggest_dish(meal_type="lunch", target_kcal=600.0, query="com")
    assert "cơm" in result_no_accent["name"].lower() or "com" in result_no_accent["name"].lower()

    # Thử từ khóa khác
    result_pho = suggest_dish(meal_type="breakfast", target_kcal=500.0, query="pho")
    assert "phở" in result_pho["name"].lower() or "pho" in result_pho["name"].lower()


# ===========================================================================
# Level 2 (Intermediate) Unit & Allergy Tests
# ===========================================================================

def test_suggest_dish_allergy_restriction():
    """TC-2.4: Đảm bảo bộ lọc không hải sản (no_seafood) hoạt động chính xác."""
    # Kêu gợi ý tất cả các món ăn bữa trưa không hải sản
    result = suggest_dish(
        meal_type="lunch",
        target_kcal=600.0,
        dietary_restrictions=["no_seafood"],
    )
    
    # Danh sách các từ khóa liên quan đến hải sản để kiểm tra tính an toàn dị ứng
    seafood_keywords = {"tôm", "mực", "cua", "cá hồi", "cá ngừ", "hàu", "sò", "ốc", "hải sản"}
    
    # Kiểm tra cả tên món ăn
    dish_name_lower = result["name"].lower()
    for kw in seafood_keywords:
        assert kw not in dish_name_lower, f"Món ăn gợi ý có chứa thành phần hải sản: {result['name']}"

    # Kiểm tra tất cả thành phần chi tiết của món ăn
    for component in result["components"]:
        comp_name_lower = component["name"].lower()
        for kw in seafood_keywords:
            assert kw not in comp_name_lower, f"Thành phần {component['name']} chứa dị nguyên hải sản"


def test_suggest_dish_vegetarian_constraint():
    """TC-2.7: Kiểm tra ràng buộc món ăn chay (vegetarian)."""
    result = suggest_dish(
        meal_type="lunch",
        target_kcal=500.0,
        dietary_restrictions=["vegetarian"],
    )
    # Tên món hoặc các thành phần không được chứa thịt/cá/hải sản thông thường
    non_veg_keywords = {"thịt bò", "thịt lợn", "ức gà", "gà ta", "tôm", "mực", "cua", "cá hồi"}
    for comp in result["components"]:
        comp_name = comp["name"].lower()
        for kw in non_veg_keywords:
            assert kw not in comp_name, f"Món chay chứa thành phần không chay: {comp['name']}"


# ===========================================================================
# Level 3 (Advanced/Adversarial) Safety & Dispatcher Tests
# ===========================================================================

def test_suggest_dish_impossible_constraints():
    """TC-3.8: Đưa ra mâu thuẫn ràng buộc cực đoan để kiểm tra khả năng bắt lỗi."""
    # Yêu cầu món thuần chay (vegan) nhưng từ khóa lại là "thịt bò" -> Phải ném lỗi NO_DISH_FOUND
    with pytest.raises(ValueError) as exc_info:
        suggest_dish(
            meal_type="dinner",
            target_kcal=600.0,
            dietary_restrictions=["vegan"],
            query="thịt bò",
        )
    assert str(exc_info.value) == "NO_DISH_FOUND"


@pytest.mark.asyncio
async def test_tool_dispatcher_safety_error_mapping():
    """Kiểm tra ToolDispatcher ánh xạ chuẩn xác lỗi ValueError cụ thể về mã lỗi thích hợp."""
    registry = ToolRegistry()
    # Đăng ký tool suggest_dish
    from services.agent.tools.dish import TOOL_DESCRIPTOR
    registry.register(TOOL_DESCRIPTOR)

    dispatcher = ToolDispatcher(registry=registry)

    # 1. Gửi yêu cầu với từ khóa bất khả thi để kích hoạt ValueError("NO_DISH_FOUND")
    call_no_dish = ToolCall(
        id="c1",
        name="suggest_dish",
        arguments={
            "meal_type": "dinner",
            "target_kcal": 600.0,
            "dietary_restrictions": ["vegan"],
            "query": "thịt bò tôm cua ghẹ",
        }
    )

    result_no_dish = await dispatcher.dispatch(session_id="s1", call=call_no_dish, timeout_ms=5000)
    assert not result_no_dish.ok
    assert result_no_dish.error == "NO_DISH_FOUND"

    # 2. Gửi meal_type không hợp lệ để kích hoạt ValueError("INVALID_MEAL_TYPE")
    call_invalid_type = ToolCall(
        id="c2",
        name="suggest_dish",
        arguments={
            "meal_type": "giữa_khuya",
            "target_kcal": 500.0,
        }
    )
    result_invalid = await dispatcher.dispatch(session_id="s1", call=call_invalid_type, timeout_ms=5000)
    assert not result_invalid.ok
    assert result_invalid.error == "INVALID_ARGS"


def test_system_prompt_safety_inclusions():
    """TC-3.7: Kiểm tra độ an toàn y tế và các cảnh báo lằn ranh đỏ có trong system prompt."""
    prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        tool_catalog=None,
    )

    # Đảm bảo system prompt chứa các ràng buộc y khoa nghiêm ngặt
    assert "chẩn đoán" in prompt.lower()
    assert "bác sĩ" in prompt.lower()
    assert "thuốc" in prompt.lower()
    assert "có thai" in prompt.lower()
    assert "tiểu diabetes" in prompt.lower()
