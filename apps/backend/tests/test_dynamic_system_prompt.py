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
        equation_sex="male",
        height_cm=175.0,
        weight_kg=70.0,
        activity_level="sedentary",
        health_goal="lose_weight",
    )
    assert metrics["bmi"] == 22.86
    assert metrics["bmi_category"] == "Bình thường"
    assert metrics["bmr"] == 1673.75
    assert metrics["tdee"] == pytest.approx(2008.5)
    assert metrics["daily_kcal_target"] == pytest.approx(metrics["tdee"] * 0.9)
    assert metrics["daily_protein_target"] == 105.0
    assert metrics["daily_water_liters"] == 2.31


def test_calculate_body_metrics_female_gain_muscle():
    # Nữ, 22 tuổi, 160cm, 45kg, light, gain_muscle
    metrics = _calculate_body_metrics(
        age=22,
        equation_sex="female",
        height_cm=160.0,
        weight_kg=45.0,
        activity_level="light",
        health_goal="gain_muscle",
    )
    assert metrics["bmi"] == 17.58
    assert metrics["bmi_category"] == "Thiếu cân"
    # BMR: 10*45 + 6.25*160 - 5*22 - 161 = 450 + 1000 - 110 - 161 = 1179
    assert metrics["bmr"] == 1179.0
    assert metrics["tdee"] == pytest.approx(1179.0 * 1.375)
    assert metrics["status"] == "REQUIRES_SPECIALIST_GUIDANCE"
    assert metrics["daily_kcal_target"] is None
    assert metrics["daily_protein_target"] is None


def test_format_profile_includes_goal_and_today_logs():
    profile = {
        "name": "Nguyễn Văn A",
        "age": 28,
        "gender": "male",
        "equation_sex": "male",
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
        "daily_nutrition_summary": {
            "policy_version": "nutrition-policy-v1.0.1",
            "formula_ids": ["DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1"],
        },
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
    assert "Béo phì độ I" in formatted
    assert "Kiêng cữ / Dị ứng thực phẩm: không ăn cay, hạn chế đường" in formatted

    assert "=== MỤC TIÊU & NGUYÊN TẮC TƯ VẤN CÁ NHÂN HÓA ===" in formatted
    assert "Giảm cân / Giảm mỡ" in formatted
    assert "Hướng dẫn giảm mỡ" in formatted

    assert "=== NHẬT KÝ THỰC TẾ HÔM NAY TRONG ỨNG DỤNG ===" in formatted
    assert "1250 kcal" in formatted
    assert "nutrition-policy-v1.0.1" in formatted
    assert "DAILY_NUTRITION_SUMMARY_CONSUMED_V1_0_1" in formatted
    assert "Phở bò tái" in formatted
    assert "Cơm tấm sườn" in formatted
    assert "Chạy bộ" in formatted
    assert "QUY TẮC TƯ VẤN BỮA TIẾP THEO" in formatted


def test_format_profile_handles_today_logs_without_canonical_calorie_target():
    profile = {
        "name": "Người dùng chưa xác nhận giới tính công thức",
        "age": 22,
        "gender": "male",
        "today_calories_consumed": 0,
        "today_meals_count": 0,
        "today_calories_burned": 0,
        "today_exercises_count": 0,
    }

    formatted = _format_profile(profile)

    assert "chưa có mục tiêu năng lượng canonical khả dụng" in formatted
    assert "Chưa có số calo còn lại canonical khả dụng" in formatted
    assert "không được tự suy diễn một con số" in formatted


def test_format_profile_exposes_free_text_nutrition_notes_without_tag_claims():
    formatted = _format_profile(
        {
            "nutrition_profile": {
                "allergy_and_avoidance_note": "Dị ứng tôm; không uống sữa",
                "food_preference_note": "Thích món Việt, ít cay",
                "nutrition_goal_note": "Muốn ăn đủ đạm",
            }
        }
    )

    assert "GHI CHÚ DINH DƯỠNG NGƯỜI DÙNG TỰ KHAI" in formatted
    assert "Dị ứng tôm; không uống sữa" in formatted
    assert "Thích món Việt, ít cay" in formatted
    assert "không phải tag dị ứng canonical" in formatted


def test_format_profile_v2_keeps_structured_allergens_distinct_from_free_text():
    formatted = _format_profile(
        {
            "nutrition_profile": {
                "nutrition_goal": "LOSE_WEIGHT",
                "food_allergies": ["PEANUT"],
                "dietary_restrictions": ["no_pork"],
                "food_dislikes_text": "Không thích rau mùi",
                "nutrition_notes": "Khó chịu sau khi uống sữa",
                "provenance": {
                    "food_allergies": "EXPLICIT_UI_SELECTION",
                    "nutrition_notes": "EXPLICIT_USER_TEXT",
                },
            }
        }
    )

    assert "dị nguyên canonical=PEANUT" in formatted
    assert "hạn chế canonical=no_pork" in formatted
    assert "Khó chịu sau khi uống sữa" in formatted
    assert "không phải tag dị ứng canonical" in formatted


def test_profile_v21_uses_shared_general_layer_and_marks_candidate_field_state():
    formatted = _format_profile(
        {
            "general_profile": {
                "age": 31,
                "height_cm": 165.0,
                "weight_kg": 61.0,
                "equation_sex": "female",
                "activity_level": "light",
                "health_goal": "maintain",
            },
            "nutrition_profile": {
                "field_states": {
                    "food_exclusions": {
                        "value": ["beef"],
                        "status": "CANDIDATE_FACT",
                        "source": "CANDIDATE_FACT",
                    }
                }
            },
        }
    )

    assert "31" in formatted
    assert "Field provenance cần xác nhận" in formatted

    prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        user_profile={"general_profile": {"age": 31}},
    )
    assert "general_profile" in prompt
    assert "food exclusion" in prompt


def test_build_system_prompt_integrates_user_profile():
    profile = {
        "name": "Trần Thị B",
        "age": 24,
        "gender": "female",
        "equation_sex": "female",
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


def test_interaction_contract_applies_to_light_and_full_prompts():
    light_prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        mode="light",
    )
    full_prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        mode="full",
    )

    for prompt in (light_prompt, full_prompt):
        assert "HỢP ĐỒNG ỨNG XỬ VỚI NGƯỜI DÙNG" in prompt
        assert "chưa tối ưu nhưng vẫn có thể lựa chọn" in prompt.casefold()
        assert "chưa đủ dữ liệu để kết luận" in prompt.casefold()
        assert "không phán xét" in prompt.casefold()
        assert "không đổ lỗi cho người dùng" in prompt.casefold()
        assert "xác minh thành công" in prompt.casefold()

    assert "không an toàn/không được phép" in full_prompt
    assert "chưa biết khác với bằng 0" in full_prompt
    assert "Chỉ xác nhận hành động khi ứng dụng đã xác minh thành công" in full_prompt


def test_full_prompt_covers_non_judgmental_cross_domain_behavior():
    prompt = buildSystemPrompt(
        rolling_summary="",
        pinned_facts=[],
        rag_chunks=[],
        mode="full",
    )

    assert "ỨNG XỬ THEO TỪNG LĨNH VỰC" in prompt
    assert "Không gọi món ăn là \"tốt/xấu\"" in prompt
    assert "Không biến vận động thành hình phạt hoặc món nợ calo" in prompt
    assert "Không quy đổi một món ăn thành số phút tập cần để đốt hết" in prompt
    assert "Phản hồi đồng cảm nhưng không chẩn đoán từ một câu nói" in prompt
    assert "Không tự biến gợi ý thành kế hoạch" in prompt
    assert "không biến kế hoạch thành nhật ký" in prompt


@pytest.mark.asyncio
async def test_orchestrator_injects_user_context_into_prompt_first_turn():
    llm = CapturingLLM([LLMResponse(content_stream=_stream(["Xin chào"]), full_text="Xin chào")])
    store = FakeStore()
    orchestrator = AgentOrchestrator(llm, FakeTools(), FakeMemory(), store, FakeDispatcher(), None)

    user_context = {
        "name": "Lê Hoàng",
        "age": 30,
        "gender": "male",
        "equation_sex": "male",
        "height": 180.0,
        "weight": 80.0,
        "health_goal": "lose_weight",
    }

    await orchestrator.handleChatMessage(
        "sess-test-1",
        "Tư vấn mục tiêu giảm cân hiện tại của tôi",
        user_context=user_context,
    )

    # A real coaching turn receives the relevant profile immediately. Pure
    # greetings deliberately use the light prompt and do not dump private
    # body metrics into an otherwise unrelated exchange.
    first_msg_content = llm.last_messages[0]["content"]
    assert "Lê Hoàng" in first_msg_content
    assert "lose_weight" in first_msg_content or "Giảm cân" in first_msg_content
    assert "BMI: 24.7" in first_msg_content
