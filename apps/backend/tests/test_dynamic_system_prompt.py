from __future__ import annotations

import pytest
from services.agent.system_prompt import (
    buildSystemPrompt,
    _calculate_body_metrics,
    _format_profile,
)
from services.agent.llm_client import LLMResponse
from services.agent.memory_service import Context
from services.agent.orchestrator import AgentOrchestrator
from tests.test_orchestrator import FakeTools, FakeMemory, FakeStore, FakeDispatcher, CapturingLLM, _stream


def test_calculate_body_metrics_male_lose_weight():
    # Nam, 25 tuổi, 175cm, 70kg, sedentary, lose_weight
    metrics = _calculate_body_metrics(
        age=25,
        gender="male",
        height_cm=175.0,
        weight_kg=70.0,
        activity_level="sedentary",
        health_goal="lose_weight",
    )
    assert metrics["bmi"] == 22.9
    assert metrics["bmi_category"] == "Bình thường (Normal / Healthy)"
    assert metrics["bmr"] == 1674.0
    assert metrics["tdee"] in (2008.0, 2009.0)
    assert metrics["daily_kcal_target"] == max(1200.0, metrics["tdee"] - 500.0)
    assert metrics["daily_protein_target"] == 126.0  # 1.8 * 70
    assert metrics["daily_water_liters"] == 2.3  # 70 * 0.033


def test_calculate_body_metrics_female_gain_muscle():
    # Nữ, 22 tuổi, 160cm, 45kg, light, gain_muscle
    metrics = _calculate_body_metrics(
        age=22,
        gender="female",
        height_cm=160.0,
        weight_kg=45.0,
        activity_level="light",
        health_goal="gain_muscle",
    )
    assert metrics["bmi"] == 17.6
    assert metrics["bmi_category"] == "Gầy (Underweight)"
    # BMR: 10*45 + 6.25*160 - 5*22 - 161 = 450 + 1000 - 110 - 161 = 1179
    assert metrics["bmr"] == 1179.0
    assert metrics["tdee"] == round(1179.0 * 1.375, 0)
    assert metrics["daily_kcal_target"] == metrics["tdee"] + 300.0
    assert metrics["daily_protein_target"] == 90.0  # 2.0 * 45


def test_format_profile_includes_goal_and_today_logs():
    profile = {
        "name": "Nguyễn Văn A",
        "age": 28,
        "gender": "male",
        "height": 172.0,
        "weight": 75.0,
        "target_weight": 68.0,
        "activity_level": "moderate",
        "health_goal": "lose_weight",
        "dietary_restrictions": ["không ăn cay", "hạn chế đường"],
        "today_calories_consumed": 1250,
        "today_meals_count": 2,
        "today_meals": [
            {"name": "Phở bò tái", "calories": 450, "meal_type": "breakfast"},
            {"name": "Cơm tấm sườn", "calories": 800, "meal_type": "lunch"},
        ],
        "today_calories_burned": 250,
        "today_exercises_count": 1,
        "today_exercises": [
            {"name": "Chạy bộ", "duration": 30, "calories_burned": 250}
        ],
    }

    formatted = _format_profile(profile)

    # Kiểm tra các phần chính
    assert "=== THỂ TRẠNG VÀ CHỈ SỐ CƠ THỂ CỦA NGƯỜI DÙNG ===" in formatted
    assert "Nguyễn Văn A" in formatted
    assert "75.0 kg" in formatted
    assert "Cân nặng mục tiêu: 68.0 kg" in formatted
    assert "BMI: 25.4" in formatted
    assert "Thừa cân" in formatted
    assert "Kiêng cữ / Dị ứng thực phẩm: không ăn cay, hạn chế đường" in formatted

    assert "=== MỤC TIÊU & NGUYÊN TẮC TƯ VẤN CÁ NHÂN HÓA ===" in formatted
    assert "Giảm cân / Giảm mỡ" in formatted
    assert "Hướng dẫn giảm mỡ" in formatted

    assert "=== NHẬT KÝ THỰC TẾ HÔM NAY TRONG ỨNG DỤNG ===" in formatted
    assert "1250 kcal" in formatted
    assert "Phở bò tái" in formatted
    assert "Cơm tấm sườn" in formatted
    assert "Chạy bộ" in formatted
    assert "QUY TẮC TƯ VẤN BỮA TIẾP THEO" in formatted


def test_build_system_prompt_integrates_user_profile():
    profile = {
        "name": "Trần Thị B",
        "age": 24,
        "gender": "female",
        "height": 158.0,
        "weight": 48.0,
        "health_goal": "gain_muscle",
    }
    prompt = buildSystemPrompt(
        rolling_summary="Đã tư vấn bữa sáng.",
        pinned_facts=[],
        rag_chunks=[],
        user_profile=profile,
        mode="full",
    )

    assert "Trần Thị B" in prompt
    assert "Tăng cơ / Tăng cân lành mạnh" in prompt
    assert "THỂ TRẠNG VÀ CHỈ SỐ CƠ THỂ" in prompt
    assert "Chưa có ghi chú đặc biệt ngoài thông tin hồ sơ và nhật ký bên dưới." in prompt


@pytest.mark.asyncio
async def test_orchestrator_injects_user_context_into_prompt_first_turn():
    llm = CapturingLLM([LLMResponse(content_stream=_stream(["Xin chào"]), full_text="Xin chào")])
    store = FakeStore()
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), None)

    user_context = {
        "name": "Lê Hoàng",
        "age": 30,
        "gender": "male",
        "height": 180.0,
        "weight": 80.0,
        "health_goal": "lose_weight",
    }

    await orchestrator.handleChatMessage("sess-test-1", "Chào bạn", user_context=user_context)

    # Prompt gửi cho LLM phải chứa thông tin thể trạng và mục tiêu ngay từ lượt đầu tiên
    first_msg_content = llm.last_messages[0]["content"]
    assert "Lê Hoàng" in first_msg_content
    assert "lose_weight" in first_msg_content or "Giảm cân" in first_msg_content
    assert "BMI: 24.7" in first_msg_content
