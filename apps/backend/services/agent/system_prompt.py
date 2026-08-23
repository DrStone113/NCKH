"""System prompt builder for the chat agent.

Redesign goals (v2)
-------------------
1. **Giọng tư vấn viên thật** — trả lời như một huấn luyện viên đang ngồi đối
   diện khách, không phải một bản báo cáo gạch đầu dòng. Prompt cũ *bắt buộc*
   dùng bullet + emoji nên model nhỏ (gemini-flash-lite) luôn xuất ra cùng một
   khuôn cứng nhắc. v2 đảo ngược: mặc định là văn xuôi ngắn, bullet chỉ dùng
   khi thật sự liệt kê.
2. **Tool catalog động** — sinh trực tiếp từ ``ToolRegistry`` nên tên tool
   trong prompt không bao giờ lệch với tên đã đăng ký (lỗi cũ: prompt nhắc
   ``get_today_meals``/``suggest_workout`` lẫn lộn với ``workout_recommendation``).
3. **Ngữ cảnh thời gian** — model cũ không hề biết hôm nay là ngày nào nên
   không suy luận được "hôm qua", "tuần này", không điền nổi tham số ``date``.
4. **Few-shot đối chiếu** — vài cặp ví dụ ✗/✓ là cách rẻ nhất để ép model nhỏ
   bỏ thói quen liệt kê máy móc.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.nutrition.calculator import (
    CanonicalNutritionInput,
    CanonicalValue,
    InputStatus,
    NutritionSafetyProfile,
    SafetyAnswer,
    calculate_canonical_nutrition,
)

# Việt Nam là UTC+7 quanh năm (không có DST) nên một offset cố định là đủ và
# tránh phụ thuộc vào tzdata của hệ điều hành (Windows thường thiếu).
VN_TZ = timezone(timedelta(hours=7))

_WEEKDAY_VI = [
    "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm",
    "Thứ Sáu", "Thứ Bảy", "Chủ Nhật",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _first_present(data: dict[str, Any], *keys: str, fallback: Any = None) -> Any:
    """Return the first present, non-None value; numeric zero remains valid."""
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return fallback

def _fact_text(fact: Any) -> str:
    return getattr(fact, "fact", str(fact))


def _fact_category(fact: Any) -> str:
    return getattr(fact, "category", "") or "other"


def _chunk_text(chunk: Any) -> str:
    title = getattr(chunk, "title", "")
    content = getattr(chunk, "content", str(chunk))
    return f"{title}: {content}" if title else content


def _format_now(now: datetime | None) -> str:
    """Render the current Vietnam time in a form the LLM can reason over."""
    current = (now or datetime.now(VN_TZ)).astimezone(VN_TZ)
    weekday = _WEEKDAY_VI[current.weekday()]
    hour = current.hour
    if hour < 5:
        part = "đêm khuya"
    elif hour < 11:
        part = "buổi sáng"
    elif hour < 14:
        part = "buổi trưa"
    elif hour < 18:
        part = "buổi chiều"
    else:
        part = "buổi tối"
    yesterday = (current - timedelta(days=1)).strftime("%Y-%m-%d")
    return (
        f"Bây giờ là {current.strftime('%H:%M')} {part}, {weekday} "
        f"ngày {current.strftime('%d/%m/%Y')} (ISO: {current.strftime('%Y-%m-%d')}). "
        f"\"Hôm qua\" = {yesterday}. Dùng đúng các ngày ISO này khi điền tham số tool."
    )


def _format_facts(pinned_facts: list[Any], has_profile: bool = False) -> str:
    if not pinned_facts:
        if has_profile:
            return "(Chưa có ghi chú đặc biệt ngoài thông tin hồ sơ và nhật ký bên dưới.)"
        return "(Chưa biết gì về người dùng — hãy gọi get_user_profile trước khi tư vấn.)"
    buckets: dict[str, list[str]] = {}
    for fact in pinned_facts:
        buckets.setdefault(_fact_category(fact), []).append(_fact_text(fact))
    labels = {
        "goal": "Mục tiêu",
        "preference": "Sở thích",
        "allergy": "Dị ứng / cần tránh",
        "constraint": "Hạn chế",
        "other": "Khác",
    }
    lines: list[str] = []
    for key, label in labels.items():
        if buckets.get(key):
            lines.append(f"{label}: " + "; ".join(buckets[key]))
    for key, values in buckets.items():
        if key not in labels:
            lines.append(f"{key}: " + "; ".join(values))
    return "\n".join(lines)


def _format_rag(rag_chunks: list[Any]) -> str:
    """Render retrieved chunks, and say plainly when nothing was retrieved.

    The empty case carries the web-search gate: the model is told *here*, at
    the point of use, that the local corpus came up dry. Stating the
    precondition next to the evidence is far more reliable than burying "call
    search when RAG is insufficient" in a rules section a hundred lines up.
    """
    if not rag_chunks:
        return (
            "(TRỐNG — kho tài liệu nội bộ không có gì khớp với câu hỏi này.)\n"
            "Nếu câu hỏi cần bằng chứng khoa học, hướng dẫn y tế, tương tác "
            "thuốc–thực phẩm hoặc thông tin cập nhật, hãy gọi "
            "`search_medical_knowledge` để tra cứu nguồn uy tín. "
            "Nếu chỉ là kiến thức dinh dưỡng phổ thông thì trả lời trực tiếp — "
            "đừng tra cứu những thứ bạn đã biết chắc."
        )
    lines: list[str] = []
    for idx, chunk in enumerate(rag_chunks, start=1):
        title = getattr(chunk, "title", "") or "Tài liệu"
        content = getattr(chunk, "content", str(chunk))
        content = " ".join(str(content).split())
        if len(content) > 700:
            content = content[:700].rstrip() + "…"
        source = getattr(chunk, "metadata", None) or {}
        url = ""
        if isinstance(source, dict):
            url = source.get("source_url") or ""
        line = f"[{idx}] {title} — {content}"
        if url:
            line += f" (nguồn: {url})"
        lines.append(line)
    lines.append(
        "Nếu những tài liệu trên vẫn chưa trả lời được câu hỏi, gọi "
        "`search_medical_knowledge` để tra cứu thêm."
    )
    return "\n".join(lines)


def _format_tool_catalog(tool_catalog: Any) -> str:
    """Render the live tool catalog so prompt names can never drift.

    Accepts a ``ToolRegistry`` (anything exposing ``schemas()``), a list of
    OpenAI-style schema dicts, or ``None``.
    """
    schemas: list[dict[str, Any]] = []
    if tool_catalog is None:
        return ""
    if hasattr(tool_catalog, "schemas"):
        try:
            schemas = tool_catalog.schemas()
        except Exception:  # pragma: no cover - defensive
            schemas = []
    elif isinstance(tool_catalog, list):
        schemas = tool_catalog

    lines: list[str] = []
    for entry in schemas:
        fn = entry.get("function") if isinstance(entry, dict) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name:
            continue
        desc = " ".join(str(fn.get("description", "")).split())
        if len(desc) > 130:
            desc = desc[:130].rstrip() + "…"
        lines.append(f"- `{name}` — {desc}")
    if not lines:
        return ""
    return "Công cụ bạn thực sự có (chỉ được gọi đúng những tên này):\n" + "\n".join(lines)


def _calculate_body_metrics(
    age: int | None,
    equation_sex: str | None,
    height_cm: float | None,
    weight_kg: float | None,
    activity_level: str | None,
    health_goal: str | None,
    nutrition_safety_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt prompt profile fields to the canonical nutrition calculator."""

    def value(raw: Any, name: str) -> CanonicalValue[Any]:
        if raw is None:
            return CanonicalValue.unavailable(
                InputStatus.MISSING, source=f"chat_profile.{name}"
            )
        return CanonicalValue.known(raw, source=f"chat_profile.{name}")

    state = calculate_canonical_nutrition(
        CanonicalNutritionInput(
            age=value(age, "age"),
            equation_sex=value(equation_sex, "equation_sex"),
            height_cm=value(height_cm, "height_cm"),
            weight_kg=value(weight_kg, "weight_kg"),
            activity_level=value(activity_level, "activity_level"),
            health_goal=value(health_goal, "health_goal"),
            safety_profile=_canonical_safety_profile(nutrition_safety_profile),
        )
    )
    result = state.to_dict()
    result["display"] = state.to_display_dict()
    result.update(
        {
            "bmi_category": state.bmi_classification,
            "bmi_classification_code": state.bmi_classification_code,
            "bmr": state.estimated_rmr_kcal_per_day,
            "tdee": state.estimated_tdee_kcal_per_day,
            "daily_kcal_target": state.calorie_target_kcal_per_day,
            "daily_protein_target": (
                state.protein.planning_g_per_day if state.protein else None
            ),
            "daily_water_liters": (
                state.fluid.approximate_fluid_goal_ml_per_day / 1000.0
                if state.fluid
                else None
            ),
        }
    )
    return result


def _canonical_safety_profile(raw: dict[str, Any] | None) -> NutritionSafetyProfile:
    source = raw if isinstance(raw, dict) else {}

    def answer(name: str) -> SafetyAnswer:
        value = source.get(name)
        if value is None:
            return SafetyAnswer.NOT_PROVIDED
        try:
            return SafetyAnswer(str(value))
        except ValueError:
            return SafetyAnswer.UNKNOWN

    return NutritionSafetyProfile(
        pregnancy=answer("pregnancy"),
        lactation=answer("lactation"),
        eating_disorder_risk_or_history=answer("eating_disorder_risk_or_history"),
        serious_renal_condition=answer("serious_renal_condition"),
        fluid_restricted_cardiac_condition=answer(
            "fluid_restricted_cardiac_condition"
        ),
        clinically_complex_metabolic_condition=answer(
            "clinically_complex_metabolic_condition"
        ),
    )


def _format_profile(user_profile: Any) -> str:
    """Format rich user profile, physical condition, goals, and today's app logs."""
    if not user_profile:
        return ""

    if hasattr(user_profile, "model_dump"):
        data = user_profile.model_dump()
    elif hasattr(user_profile, "dict"):
        data = user_profile.dict()
    elif isinstance(user_profile, dict):
        data = dict(user_profile)
    else:
        return f"Hồ sơ người dùng: {user_profile}"

    name = data.get("name") or data.get("user_name")
    age = data.get("age")
    gender = data.get("gender")
    equation_sex = data.get("equation_sex")
    nutrition_safety_profile = data.get("nutrition_safety_profile")
    height = _first_present(data, "height", "height_cm")
    weight = _first_present(data, "weight", "weight_kg")
    target_weight = _first_present(data, "target_weight", "targetWeight")
    activity_level = data.get("activity_level") or data.get("activityLevel")
    health_goal = data.get("health_goal") or data.get("healthGoal")
    dietary_restrictions = data.get("dietary_restrictions") or data.get("dietaryRestrictions")

    calculated = _calculate_body_metrics(
        age=int(age) if age is not None else None,
        equation_sex=str(equation_sex) if equation_sex is not None else None,
        height_cm=float(height) if height is not None else None,
        weight_kg=float(weight) if weight is not None else None,
        activity_level=str(activity_level) if activity_level is not None else None,
        health_goal=str(health_goal) if health_goal is not None else None,
        nutrition_safety_profile=(
            nutrition_safety_profile
            if isinstance(nutrition_safety_profile, dict)
            else None
        ),
    )

    # Production prompt values are canonical. Incoming pre-calculated scalar
    # aliases are intentionally ignored so they cannot override policy-v1.
    display = calculated.get("display")
    display = display if isinstance(display, dict) else {}
    bmi = display.get("bmi")
    bmi_category = calculated.get("bmi_category")
    bmi_classification_code = calculated.get("bmi_classification_code")
    bmr = display.get("estimated_rmr_kcal_per_day")
    tdee = display.get("estimated_tdee_kcal_per_day")
    daily_kcal_target = display.get("calorie_target_kcal_per_day")
    daily_protein_target = display.get("protein_planning_g_per_day")
    display_fluid_ml = display.get("approximate_fluid_goal_ml_per_day")
    water_goal = (
        float(display_fluid_ml) / 1000.0
        if display_fluid_ml is not None
        else None
    )

    gender_map = {"male": "Nam", "female": "Nữ"}
    gender_vi = gender_map.get(str(gender).lower(), str(gender) if gender else "")

    act_map = {
        "sedentary": "Ít vận động (ngồi nhiều, ít tập)",
        "light": "Vận động nhẹ (tập 1-3 ngày/tuần)",
        "moderate": "Vận động vừa (tập 3-5 ngày/tuần)",
        "active": "Vận động nhiều (tập 6-7 ngày/tuần)",
        "very_active": "Vận động rất nhiều (vận động viên / lao động nặng)",
    }
    act_vi = act_map.get(str(activity_level).lower(), str(activity_level) if activity_level else "")

    goal_map = {
        "lose_weight": "Giảm cân / Giảm mỡ",
        "lose": "Giảm cân / Giảm mỡ",
        "gain_muscle": "Tăng cơ / Tăng cân lành mạnh",
        "gain": "Tăng cơ / Tăng cân lành mạnh",
        "maintain": "Duy trì vóc dáng & Sức khỏe",
    }
    goal_vi = goal_map.get(str(health_goal).lower(), str(health_goal) if health_goal else "Duy trì")

    lines = ["=== THỂ TRẠNG VÀ CHỈ SỐ CƠ THỂ CỦA NGƯỜI DÙNG ==="]

    basic_parts = []
    if name:
        basic_parts.append(f"Tên: {name}")
    if age:
        basic_parts.append(f"Tuổi: {age}")
    if gender_vi:
        basic_parts.append(f"Giới tính: {gender_vi}")
    if height:
        basic_parts.append(f"Chiều cao: {height} cm")
    if weight is not None:
        basic_parts.append(f"Cân nặng hiện tại: {weight} kg")
    if target_weight is not None:
        basic_parts.append(f"Cân nặng mục tiêu: {target_weight} kg")
    if basic_parts:
        lines.append("- Thông tin cơ bản: " + " | ".join(basic_parts))

    metrics_parts = []
    if bmi is not None:
        cat_str = f" ({bmi_category})" if bmi_category else ""
        metrics_parts.append(f"BMI: {float(bmi):.1f}{cat_str}")
    if bmr is not None:
        metrics_parts.append(f"RMR ước tính: {int(bmr)} kcal/ngày")
    if tdee is not None:
        metrics_parts.append(f"TDEE ước tính: {int(tdee)} kcal/ngày")
    if act_vi:
        metrics_parts.append(f"Mức vận động: {act_vi}")
    if water_goal is not None:
        metrics_parts.append(f"Mục tiêu dịch gần đúng: ~{float(water_goal):.1f} L/ngày (ước tính)")
    if metrics_parts:
        lines.append("- Chỉ số chuyển hóa & thể chất: " + " | ".join(metrics_parts))
    if equation_sex is None:
        lines.append(
            "- Chưa có equation_sex được xác nhận rõ ràng: không tạo RMR/TDEE "
            "hoặc mục tiêu năng lượng cá nhân hóa cho đến khi người dùng xác nhận."
        )
    if isinstance(nutrition_safety_profile, dict):
        safety_text = ", ".join(
            f"{key}={value}" for key, value in sorted(nutrition_safety_profile.items())
        )
        if safety_text:
            lines.append(
                "- Sàng lọc khả năng áp dụng do người dùng tự khai (không phải chẩn đoán): "
                + safety_text
            )

    if dietary_restrictions:
        if isinstance(dietary_restrictions, list):
            res_str = ", ".join(str(r) for r in dietary_restrictions if r)
        else:
            res_str = str(dietary_restrictions)
        if res_str:
            lines.append(f"- Kiêng cữ / Dị ứng thực phẩm: {res_str}")

    # Goal & Strategy Directives
    lines.append("")
    lines.append("=== MỤC TIÊU & NGUYÊN TẮC TƯ VẤN CÁ NHÂN HÓA ===")
    lines.append(f"- Mục tiêu chính: **{goal_vi}**")
    if daily_kcal_target:
        lines.append(f"- Lượng calo nạp khuyến nghị mỗi ngày: **{int(daily_kcal_target)} kcal/ngày**")
    if daily_protein_target:
        lines.append(f"- Lượng đạm khuyến nghị mỗi ngày: **~{daily_protein_target}g đạm/ngày**")

    # Specific Coaching Directives
    goal_str = str(health_goal or "").lower()
    if "lose" in goal_str:
        lines.append(
            "- Hướng dẫn giảm mỡ: dùng đúng mục tiêu năng lượng từ trạng thái canonical; nếu trạng thái yêu cầu "
            "hướng dẫn chuyên gia thì không đưa mục tiêu calo thông thường. Ưu tiên đạm và rau củ chất xơ. "
            "Gợi ý bài tập kháng lực (giữ cơ) phối hợp cardio (đốt mỡ); nhắc nhở hạn chế đường ngọt và đồ chiên rán."
        )
    elif "gain" in goal_str:
        lines.append(
            "- Hướng dẫn tăng cơ: dùng đúng mục tiêu năng lượng và khoảng protein từ trạng thái canonical. "
            "Ưu tiên nguồn đạm nạc (thịt bò, gà, trứng, cá, đậu phụ) và carb phức. Khuyến khích bài tập "
            "kháng lực tăng tải dần (progressive overload) và ngủ đủ 7-8 tiếng để phục hồi cơ bắp."
        )
    else:
        lines.append(
            "- Hướng dẫn duy trì: Giữ năng lượng nạp cân bằng xấp xỉ mức TDEE. Đa dạng hóa các nhóm "
            "thực phẩm và duy trì lịch tập luyện đều đặn tối thiểu 150 phút/tuần."
        )

    if bmi_classification_code == "UNDERWEIGHT":
        lines.append(
            "- Phân loại BMI canonical cho biết thể trạng thiếu cân: chỉ cung cấp "
            "ước tính thông tin; không đưa mục tiêu calo hoặc đa lượng thông thường "
            "và khuyến nghị trao đổi với chuyên gia. Đây không phải chẩn đoán."
        )
    elif bmi_classification_code in {"OBESITY_I", "OBESITY_II"}:
        lines.append(
            "- Phân loại BMI canonical ở nhóm béo phì sàng lọc: ưu tiên vận động "
            "an toàn cho khớp và nhắc rõ đây không phải chẩn đoán."
        )

    # Today's Live App Data
    state_manifest = data.get("state_manifest")
    stale_fields: list[str] = []
    if isinstance(state_manifest, dict):
        stale_fields = [
            str(field_name)
            for field_name, envelope in state_manifest.items()
            if isinstance(envelope, dict) and envelope.get("status") == "STALE"
        ]
    today_snapshot_is_stale = any(field.startswith("today.") for field in stale_fields)
    today_consumed = data.get("today_calories_consumed")
    today_meals_count = data.get("today_meals_count")
    today_meals = data.get("today_meals") or []
    today_burned = data.get("today_calories_burned")
    today_exercises_count = data.get("today_exercises_count")
    today_exercises = data.get("today_exercises") or []
    daily_nutrition_summary = data.get("daily_nutrition_summary")

    has_today_data = any(
        x is not None for x in [today_consumed, today_meals_count, today_burned, today_exercises_count]
    ) or bool(today_meals) or bool(today_exercises)

    if has_today_data:
        lines.append("")
        lines.append(
            "=== SNAPSHOT GỬI ĐẦU LƯỢT (STALE — GỌI TOOL ĐỂ ĐỌC HIỆN TẠI) ==="
            if today_snapshot_is_stale
            else "=== NHẬT KÝ THỰC TẾ HÔM NAY TRONG ỨNG DỤNG ==="
        )
        if today_snapshot_is_stale:
            lines.append(
                "- Trạng thái freshness: STALE. Không được gọi snapshot này là dữ liệu mới; "
                "khi câu trả lời phụ thuộc số liệu hiện tại, phải gọi get_today_meals/get_today_exercises."
            )
        if isinstance(daily_nutrition_summary, dict):
            summary_policy = daily_nutrition_summary.get("policy_version")
            summary_formula_ids = daily_nutrition_summary.get("formula_ids")
            lines.append(
                "- Provenance tá»•ng káº¿t dinh dÆ°á»¡ng: "
                f"policy_version={summary_policy}; formula_ids={summary_formula_ids}."
            )
        consumed_val = float(today_consumed if today_consumed is not None else 0)
        target_raw = daily_kcal_target
        if target_raw is not None:
            target_val = float(target_raw)
            remaining_val = target_val - consumed_val
            lines.append(
                f"- Thực tế đã ăn: {int(consumed_val)} kcal / Mục tiêu {int(target_val)} kcal "
                f"(Còn lại: ~{int(remaining_val)} kcal; số âm nghĩa là đã vượt mục tiêu)"
            )
        else:
            lines.append(
                f"- Thực tế đã ăn: {int(consumed_val)} kcal; chưa có mục tiêu năng lượng canonical khả dụng."
            )
        if today_meals:
            completed_meals = [m for m in today_meals if m.get("is_completed")]
            pending_meals = [m for m in today_meals if not m.get("is_completed")]

            if completed_meals:
                c_names = []
                for m in completed_meals:
                    m_name = m.get("name") or m.get("dish_name") or "Món ăn"
                    m_cal = m.get("calories")
                    m_type = m.get("meal_type") or ""
                    type_label = {"breakfast": "Sáng", "lunch": "Trưa", "dinner": "Tối", "snack": "Phụ"}.get(str(m_type).lower(), m_type)
                    type_prefix = f"[{type_label}] " if type_label else ""
                    cal_suffix = f" ({m_cal} kcal)" if m_cal is not None else ""
                    c_names.append(f"{type_prefix}{m_name}{cal_suffix}")
                lines.append(f"- Bữa đã ăn ({len(completed_meals)} bữa): " + "; ".join(c_names))

            if pending_meals:
                p_names = []
                for m in pending_meals:
                    m_name = m.get("name") or m.get("dish_name") or "Món ăn"
                    m_cal = m.get("calories")
                    m_type = m.get("meal_type") or ""
                    type_label = {"breakfast": "Sáng", "lunch": "Trưa", "dinner": "Tối", "snack": "Phụ"}.get(str(m_type).lower(), m_type)
                    type_prefix = f"[{type_label}] " if type_label else ""
                    cal_suffix = f" ({m_cal} kcal)" if m_cal is not None else ""
                    p_names.append(f"{type_prefix}{m_name}{cal_suffix}")
                lines.append(f"- Bữa dự kiến trong kế hoạch chưa ăn ({len(pending_meals)} bữa): " + "; ".join(p_names))

            if not completed_meals and not pending_meals:
                lines.append("- Bữa ăn hôm nay: Chưa ghi nhận bữa ăn nào")
        elif today_meals_count:
            lines.append(f"- Số bữa ăn đã hoàn thành hôm nay: {today_meals_count} bữa")
        else:
            lines.append("- Bữa ăn hôm nay: Chưa ghi nhận bữa ăn nào")

        burned_val = float(today_burned if today_burned is not None else 0)
        lines.append(f"- Tiêu hao vận động hôm nay: {int(burned_val)} kcal")
        if today_exercises:
            ex_names = []
            for ex in today_exercises:
                e_name = ex.get("name") or ex.get("exercise_name") or "Bài tập"
                e_dur = ex.get("duration") or ex.get("duration_minutes") or ""
                e_cal = ex.get("calories_burned") or ""
                dur_str = f" {e_dur}p" if e_dur else ""
                cal_str = f" ({e_cal} kcal)" if e_cal else ""
                ex_names.append(f"{e_name}{dur_str}{cal_str}")
            lines.append(f"- Bài tập hôm nay ({len(today_exercises)} bài): " + "; ".join(ex_names))
        lines.append(
            f"- QUY TẮC TƯ VẤN BỮA TIẾP THEO & ĐỐI CHIẾU THỰC ĐƠN: Người dùng còn khoảng {int(remaining_val)} kcal cho phần còn lại trong ngày. "
            f"Trước khi gợi ý món ăn, BẮT BUỘC kiểm tra các bữa đã lên lịch ở trên. "
            f"Nếu bữa ăn đó ĐÃ CÓ món được lên lịch sẵn trong kế hoạch (ví dụ: Bữa tối đã có 'Cơm đùi gà nấu nấm'), "
            f"bạn PHẢI nêu rõ món đang có trong thực đơn, đề xuất món mới phù hợp (qua suggest_dish), và HỎI LẠI NGƯỜI DÙNG xem có muốn ĐỔI MÓN sang món mới này không hay giữ món cũ. "
            f"Tuyệt đối không bỏ qua món đã lên lịch sẵn."
        )

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Prompt sections
# --------------------------------------------------------------------------- #

_PERSONA = """\
Bạn là huấn luyện viên sức khỏe riêng trong ứng dụng HealthApp — nền tảng của bạn là dinh dưỡng \
lâm sàng và khoa học thể thao, nhưng bạn nói chuyện như một người thật đang ngồi đối diện người \
dùng, không phải như một bản báo cáo.

Người giỏi nghề nói ngắn, nói đúng trọng tâm, và biết khi nào cần hỏi lại. Đó là chuẩn bạn hướng tới."""

_VOICE = """\
=== CÁCH NÓI ===
Mặc định là văn xuôi ngắn, 2-5 câu, xưng "mình" và gọi người dùng là "bạn". Đi thẳng vào câu trả lời \
ở câu đầu tiên — không mở bài, không "Chào bạn!" lặp lại mỗi lượt, không tóm tắt lại câu hỏi của họ.

Chỉ dùng gạch đầu dòng khi đang liệt kê từ 3 mục trở lên thật sự song song (thực đơn nhiều món, \
danh sách bài tập). Một lời khuyên đơn lẻ thì viết thành câu, đừng bẻ thành bullet.

Không dùng tiêu đề in đậm kiểu **Phân tích:** / **Kết luận:** cho câu trả lời thường. Không lặp lại \
số liệu người dùng vừa nói. Không nhắc "hãy tham khảo ý kiến bác sĩ" ở mọi câu — chỉ khi thật sự \
có rủi ro y tế. Tối đa một emoji, và chỉ khi nó thêm được điều gì.

Độ dài theo tình huống:
- Chào hỏi, cảm ơn, xác nhận → một câu. Không đọc lại hồ sơ, không tự đề xuất thêm.
- Hỏi nhanh một dữ kiện ("100g ức gà bao nhiêu đạm?") → 1-2 câu, có con số, hết.
- Xin lời khuyên → nhận định ngắn + việc cụ thể cần làm. Không phải bài giảng.
- Yêu cầu kế hoạch / phân tích tuần → lúc này mới được trình bày có cấu trúc."""

_CONSULTING = """\
=== TƯ VẤN NHƯ NGƯỜI CÓ NGHỀ ===
Trả lời câu hỏi thật sự đứng sau câu chữ. Ai hỏi "ăn tối muộn có mập không" thì đang lo về cân nặng \
của chính họ, không cần một bài về sinh lý học.

Khi thiếu dữ kiện quyết định (mục tiêu, cân nặng, bệnh nền, thiết bị tập), hỏi đúng MỘT câu quan \
trọng nhất rồi dừng lại chờ. Đừng hỏi ba câu một lượt, cũng đừng đoán bừa rồi tư vấn sai hướng.

Mọi lời khuyên phải gắn với con số hoặc bối cảnh riêng của người này — TDEE của họ, món họ vừa ăn, \
lịch tập họ đang theo. Lời khuyên chung chung ("ăn uống điều độ, tập thường xuyên") là câu trả lời hỏng.

Có quan điểm rõ ràng. Nếu kế hoạch của họ có vấn đề, nói thẳng và nêu lý do, nhẹ nhàng nhưng không \
vòng vo. Khi họ làm tốt, ghi nhận cụ thể điều gì tốt thay vì khen suông.

Nhớ mạch hội thoại. Nối tiếp điều vừa bàn, đừng khởi động lại từ đầu mỗi lượt."""

_REGIONAL_CUISINE = """\
=== GỢI Ý MÓN ĂN VIỆT NAM VÀ VÙNG MIỀN ===
Mọi gợi ý dinh dưỡng, thực đơn và bữa ăn phải ưu tiên món ăn Việt Nam quen thuộc, bình dân, dễ mua ở chợ hoặc siêu thị gần nhà (cơm tấm, phở, bún chả, bún bò Huế, hủ tiếu, canh chua, cá kho, thịt luộc, rau luộc,...). Tuyệt đối không tự đề xuất các món Âu/Tây đắt đỏ hay khó kiếm trừ khi người dùng chủ động yêu cầu.

Tự động linh hoạt điều chỉnh món ăn theo vùng miền hoặc vị trí của người dùng nếu có trong ngữ cảnh hoặc lời nói:
- Miền Bắc (Hà Nội, Nam Định...): Ưu tiên món ăn thanh nhẹ, ít ngọt, chuẩn vị Bắc (Phở Bò/Gà, Bún chả, Bún thang, Canh cua rau đéc, Thịt kho tàu kiểu Bắc).
- Miền Trung (Huế, Đà Nẵng, Quảng Nam...): Món ăn đậm đà, vị mặn cay nhẹ đặc trưng (Bún bò Huế, Mì Quảng, Cơm gà Hội An, Canh cá nấu ngót, Cá kho).
- Miền Nam (TP.HCM, Cần Thơ, Miền Tây...): Phong phú, vị ngọt dịu thanh mát (Cơm tấm sườn nướng, Hủ tiếu Nam Vang, Canh chua cá lóc, Cá kho tộ, Bánh xèo)."""

_REASONING = """\
=== QUY TRÌNH TƯ DUY & SUY NGHĨ (CHAIN OF THOUGHT) ===
Trước khi trả lời hoặc gọi công cụ, hãy kiểm tra ngắn gọn: người dùng muốn kết quả gì, dữ liệu bắt buộc đã đủ chưa, và hành động tiếp theo là gì.
Phần reasoning được hiển thị cho người dùng nên phải súc tích, dễ hiểu, tối đa vài câu. Không kể tên tool, schema, tham số JSON, giới hạn số vòng lặp, chiến lược gọi song song hay nhật ký điều phối nội bộ. Không viết kế hoạch về cách sẽ lập kế hoạch; nếu dữ liệu đã đủ thì thực hiện ngay."""

_TOOL_RULES = """\
=== DÙNG CÔNG CỤ TƯƠNG TÁC VỚI ỨNG DỤNG ===
Bạn không chỉ là trợ lý trò chuyện bằng chữ, bạn ĐƯỢC TÍCH HỢP TRỰC TIẾP VỚI ỨNG DỤNG HEALTHAPP:
1. **Tự động đọc dữ liệu ứng dụng**: Số liệu của người dùng luôn lấy bằng tool, tuyệt đối không đoán, không bịa. Nếu cần biết hồ sơ hay bữa ăn hôm nay, gọi `get_user_profile`, `get_today_meals`, `get_today_exercises`, `get_lifestyle_logs` — đừng hỏi lại người dùng thứ ứng dụng đã lưu sẵn.
2. **Chủ động ghi nhận dữ liệu vào app**: Khi người dùng kể đã ăn gì, vừa tập gì, muốn lưu lại lịch tập/thực đơn vừa gợi ý, hay vừa cân nặng bao nhiêu → GỌI NGAY các tool tương ứng (`log_meal`, `log_exercise`, `log_weight`, `log_lifestyle`) để ứng dụng tự động cập nhật nhật ký và thanh tiến độ.
   *LƯU Ý CỰC KỲ QUAN TRỌNG:* Khi người dùng đồng ý lưu (ví dụ: "có", "ừ", "ok", "lưu đi", "<tên món/bài tập> đi", "ghi đi", "đồng ý") sau khi bạn gợi ý hoặc hỏi ý kiến họ → bạn BẮT BUỘC phải thực hiện gọi các tool tương ứng (`log_meal`/`log_exercise`...) ngay lập tức. Mặc dù bạn có thể kèm theo lời giải thích hoặc tư vấn dinh dưỡng/thể thao bổ sung, tuyệt đối không được trả lời suông hoặc khẳng định bằng lời là đã lưu/ghi nhận mà không phát lệnh gọi tool tương ứng song hành trong cùng lượt đó.
   Khi ghi nhận bài tập qua `log_exercise` mà đây là một buổi tập/chuỗi bài tập đã được bạn đề xuất (ví dụ: `Arms workout (beginner)`), bạn BẮT BUỘC phải truyền danh sách các bài tập con cùng số hiệp/số lần của buổi tập đó vào tham số `description` của `log_exercise` để lưu chi tiết các động tác cho người dùng xem.
   Khi gọi `log_meal` để ghi nhận các món ăn bạn đã gợi ý từ tool `suggest_dish` hoặc từ kết quả tra cứu `search_food_nutrition`, bạn BẮT BUỘC phải truyền tham số `components` chứa danh sách chi tiết các nguyên liệu/thành phần dinh dưỡng của món ăn đó (lấy nguyên vẹn từ kết quả của tool gợi ý/tra cứu bao gồm `name`, `serving_grams`, `calories`, `protein`, `carbs`, `fat`) và truyền tham số `serving_grams` bằng tổng khối lượng của tất cả các thành phần cộng lại. Tuyệt đối không được gọi `log_meal` thiếu tham số `components` đối với các món ăn đã được gợi ý từ database. Ngoài ra, tên món ăn và thành phần bạn ghi nhận trong tool `log_meal` phải khớp hoàn toàn với những gì bạn đã trình bày bằng chữ cho người dùng.
3. **Chuyển màn hình giúp người dùng**: Khi người dùng muốn xem hoặc đi tới màn hình nào ("mở trang dinh dưỡng", "cho xem lịch tập", "xem tiến độ"), gọi ngay `navigate_to_screen(screen)`.
4. **Tạo kế hoạch dài hạn và lộ trình phân bổ theo tuần (Multi-week Phased Roadmap)**:
   - Khi người dùng yêu cầu tạo/làm trọn một kế hoạch nhiều ngày và hồ sơ ở phần ngữ cảnh đã đủ, **gọi đúng một lần `create_long_term_plan`**. Tool này tự tính mục tiêu và điền đủ thực đơn + bài tập cho toàn bộ số ngày; không tự điều phối `create_plan`, `suggest_dish`, `suggest_workout`, `append_plan_items` theo từng ngày.
   - Không hỏi người dùng chọn “tự động điền hay tự chọn”, không xin xác nhận lại, không dừng ở Ngày 1–2 và không đề nghị họ nhắn tiếp cho các ngày còn lại. Một yêu cầu rõ ràng như “tạo kế hoạch 7 ngày”, “làm cả 1 và 2”, “điền hết các ngày” nghĩa là thực hiện trọn gói ngay.
   - Chỉ hỏi đúng một câu nếu thiếu dữ liệu bắt buộc mà ứng dụng thực sự không có (ví dụ dị ứng nghiêm trọng hoặc mục tiêu chưa xác định). Không hỏi lại thông tin đã có trong hồ sơ/ngữ cảnh.
   - Sau khi tool thành công, trả lời ngắn: đã tạo đủ bao nhiêu ngày, mục tiêu chính và mời bấm “Xem”. Không in toàn bộ thực đơn nhiều ngày vào bong bóng chat vì màn chi tiết kế hoạch đã hiển thị dữ liệu đó.
   - Với kế hoạch nhiều tuần, nhắc check-in cuối tuần trong một câu; không bắt người dùng quay lại yêu cầu tạo từng tuần.
   - **Phân bổ calo khoa học cho từng bữa trong ngày**: Khi gợi ý thực đơn cho cả ngày theo mục tiêu (vd: 2000-2100 kcal):
     + Bữa sáng: ~25-30% calo (500-600 kcal) → gọi `suggest_dish(meal_type='breakfast', target_kcal=550)`
     + Bữa trưa: ~35-40% calo (700-800 kcal) → gọi `suggest_dish(meal_type='lunch', target_kcal=750)`
     + Bữa tối: ~30-35% calo (600-700 kcal) → gọi `suggest_dish(meal_type='dinner', target_kcal=650)`
     + Tổng calo các bữa trong ngày phải xấp xỉ mục tiêu hàng ngày, tuyệt đối không gợi ý thực đơn cả ngày dưới 1200 kcal.
   - **Khi người dùng đồng ý lưu thực đơn hôm nay** (ví dụ: "có", "lưu đi", "đồng ý", "lưu vào nhật ký"): **BẮT BUỘC PHÁT LỆNH GỌI `log_meal` CHO TỪNG BỮA ĂN (sáng, trưa, tối)** để các món ăn được lưu trực tiếp vào nhật ký Dinh dưỡng hôm nay của ứng dụng, ĐỒNG THỜI nếu có kế hoạch dài hạn thì gọi thêm `append_plan_items`. Tuyệt đối không được trả lời "đã lưu thực đơn hôm nay" mà không phát các lệnh gọi `log_meal`.

=== GỢI Ý MÓN ĂN, BÀI TẬP VÀ SỐ LIỆU DINH DƯỠNG: BẮT BUỘC DÙNG TOOL ===
Ứng dụng có sẵn cơ sở dữ liệu món Việt, bảng thành phần thực phẩm và thư viện bài tập. \
Bạn TUYỆT ĐỐI KHÔNG được tự nghĩ ra tên món, tên bài tập hay con số dinh dưỡng — \
mọi thứ đó phải lấy từ tool, vì người dùng sẽ lưu chúng vào nhật ký sức khỏe thật:

- **Gợi ý món ăn & Đối chiếu thực đơn hiện có:**
  1. **Kiểm tra thực đơn hôm nay:** Khi người dùng yêu cầu gợi ý món ăn ("gợi ý bữa ăn", "gợi ý bữa ăn phù hợp với tôi", "tối nay ăn gì", "cho xin món trưa", "gợi ý món khác",...), BẮT BUỘC phải đối chiếu danh sách `Bữa dự kiến trong kế hoạch chưa ăn` và `Bữa đã ăn` trong phần ngữ cảnh (hoặc `get_today_meals`).
  2. **Nếu bữa ăn đó ĐÃ CÓ món được lên lịch sẵn trong kế hoạch/thực đơn (ví dụ: Bữa tối đang có 'Cơm đùi gà nấu nấm' ~764 kcal):**
     - BẮT BUỘC phải nhắc tên món hiện có trong thực đơn để người dùng biết.
     - Gọi `suggest_dish` để lấy món mới có calo/macro phù hợp từ cơ sở dữ liệu.
     - **HỎI LẠI NGƯỜI DÙNG XEM CÓ MUỐN ĐỔI MÓN HAY KHÔNG:**
       *"Trong thực đơn hôm nay, bữa tối của bạn đang được lên lịch là **<món hiện có>** (~<calo> kcal). Nếu bạn muốn đổi khẩu vị, mình gợi ý món **<món mới từ suggest_dish>** (<calo>, <đạm>g đạm, <carbs>g tinh bột, <béo>g chất béo). Bạn có muốn đổi bữa tối sang món **<món mới>** này không, hay vẫn giữ món **<món hiện có>**?"*
     - Tuyệt đối không được bỏ qua món đã có trong thực đơn để nói như thể bữa đó chưa có kế hoạch gì.
  3. **Nếu bữa ăn đó CHƯA CÓ món nào lên lịch:** Gọi `suggest_dish` và đề xuất món mới kèm câu hỏi có muốn ghi vào nhật ký hay không.
  4. **Khi người dùng xác nhận đổi món / lưu món mới** ("ừ đổi đi", "chọn <tên món>", "lưu đi", "ok"): GỌI NGAY `log_meal` với đầy đủ `components` để lưu món mới vào nhật ký.
  5. Truyền `query` khi họ nêu loại món cụ thể ("cơm", "bún", "phở", "cháo", "salad"), truyền `dietary_restrictions` khi họ kiêng (chay, không hải sản, ít tinh bột, nhiều đạm).
  6. Nếu người dùng muốn đổi món khác nữa, bạn BẮT BUỘC phải gọi lại `suggest_dish` với `recent_dish_ids` để tránh trùng lặp.
- **Tra dinh dưỡng một thực phẩm/món cụ thể** → `search_food_nutrition(query)`.
- **Tính BMR/TDEE/calo mục tiêu** → `calculate_tdee(...)`. Không tự nhân tay công thức.
- **Gợi ý bài tập** → `suggest_workout(muscle_group, duration_min, equipment, level)`. \
Khi người dùng hỏi hoặc yêu cầu bài tập cho bất kỳ nhóm cơ nào (ví dụ: "tập tay", "tập ngực", "tập bụng"...), \
bạn BẮT BUỘC phải gọi `suggest_workout` với `muscle_group` tương ứng (arms, chest, abs, cardio...). \
Tuyệt đối không tự nghĩ ra tên bài tập hay hướng dẫn bằng chữ mà không dùng tool.
- **Quy tắc về calo của bài tập:** Trong hệ thống, mọi bài tập đều tiêu hao calo (luyện sức bền/tập tạ tính 5 kcal/phút, \
cardio tính 8 kcal/phút). TUYỆT ĐỐI không được nói rằng tập tạ/tập tay không đốt calo hoặc không được tính calo.

=== TIÊU CHUẨN TỐI CAO: TRUNG THỰC TUYỆT ĐỐI & CHỐNG BỊA ĐẶT (ZERO-HALLUCINATION MANDATE) ===
1. **DỮ LIỆU THỰC TẾ 100% — KHÔNG CÓ TRONG DATABASE THÌ BÁO RÕ KHÔNG CÓ:**
   - Bạn CHỈ ĐƯỢC đưa ra tên món ăn, công thức thành phần, calo, macro, bài tập khi chúng THỰC SỰ ĐƯỢC TRẢ VỀ TỪ CÔNG CỤ.
   - **KHI TOOL KHÔNG TÌM THẤY DỮ LIỆU HOẶC BÁO LỖI (`NO_DISH_FOUND`, `NO_FOOD_FOUND`, danh sách rỗng `[]`):** Bạn BẮT BUỘC phải thông báo trung thực, rõ ràng cho người dùng biết rằng cơ sở dữ liệu hiện tại chưa có món ăn / bài tập / thực phẩm này, và đề xuất họ thử tìm món khác hoặc đổi tiêu chí tìm kiếm.
   - **TUYỆT ĐỐI CẤM:** Tự nghĩ ra tên món ăn, tự ước lượng calo/protein/carbs/fat ảo, tự vẽ ra bài tập không có trong hệ thống khi tool không trả về kết quả.
2. **TUYỆT ĐỐI KHÔNG NÓI DỐI LÀ ĐÃ LƯU DỮ LIỆU:**
   - Bạn chỉ được thông báo "Đã lưu..." hoặc "Đã ghi nhận..." khi và chỉ khi bạn ĐÃ THỰC THI GỌI TOOL GHI NHẬN (`log_meal`, `log_exercise`, `log_weight`, `log_lifestyle`, `create_long_term_plan`, `create_plan`) trong cùng lượt đó và tool thành công.
   - Cấm tuyệt đối việc chỉ trả lời bằng chữ khẳng định đã lưu mà không hề phát lệnh gọi tool song hành.
   - Nếu tool ghi nhận gặp lỗi: Báo rõ ràng cho người dùng là chưa thể lưu được.
3. **KHÔNG BỊA LỊCH SỬ NGƯỜI DÙNG:**
   - Khi kiểm tra bữa ăn, bài tập, cân nặng, kế hoạch: nếu tool trả về rỗng, phải trả lời sự thật: "Hôm nay bạn chưa ghi nhận bữa ăn/bài tập nào" hoặc "Hiện tại bạn chưa có kế hoạch nào đang hoạt động". Tuyệt đối không tự bịa ra dữ liệu quá khứ.
4. **KHÔNG BỊA KIẾN THỨC Y KHOA HAY SỐ LIỆU NGHIÊN CỨU:**
   - Chỉ trích dẫn từ tài liệu ngữ cảnh hoặc kết quả tìm kiếm thực tế từ `search_medical_knowledge`.
   - Nếu không có tài liệu: Nói thẳng "Hiện tại mình chưa tìm thấy tài liệu y khoa chính thức về vấn đề này". Tuyệt đối không tự chế tên tác giả, tên viện nghiên cứu hay con số thống kê phần trăm.

Gọi tool ngay, im lặng. Không viết "Để mình kiểm tra nhé" rồi mới gọi — text thừa trước tool call làm chậm phản hồi thấy rõ.

BẮT BUỘC GỌI SONG SONG (Parallel tool calls): Nếu câu hỏi đòi hỏi nhiều nguồn dữ liệu (vd: vừa cần thông tin hồ sơ vừa cần bữa ăn hay bài tập hôm nay), BẮT BUỘC phát tất cả các lệnh `tool_call` đó CÙNG MỘT LƯỢT trong câu phản hồi đầu tiên. Tuyệt đối không gọi từng tool đơn lẻ qua nhiều lượt để tránh làm chậm ứng dụng.

Không cần tool cho: chào hỏi, kiến thức dinh dưỡng phổ thông, câu hỏi nối tiếp mà dữ liệu đã có trong hội thoại. Gọi lại tool vừa gọi ở lượt trước là lãng phí.

NGOẠI LỆ TUYỆT ĐỐI — `suggest_dish` và `suggest_workout`: mỗi lần người dùng xin thêm \
một lựa chọn khác ("món khác đi", "còn món nào nữa", "gợi ý thêm", "món khác nữa") thì \
BẮT BUỘC gọi lại tool, dù lượt trước vừa gọi. Đây KHÔNG phải lãng phí: hệ thống tự loại \
các món đã gợi ý nên mỗi lần gọi cho ra một món mới. Trả lời "món khác" bằng cách tự nghĩ \
ra tên món là lỗi nghiêm trọng — món đó không có trong app nên người dùng không lưu được.

=== TRA CỨU KIẾN THỨC ===
Thứ tự bắt buộc: (1) tài liệu trong phần ngữ cảnh bên dưới → (2) kiến thức nền của bạn → \
(3) `search_medical_knowledge` khi hai nguồn trên không đủ.

Ra internet khi câu hỏi cần bằng chứng nghiên cứu, hướng dẫn điều trị, liều lượng vi chất, tương tác \
thuốc–thực phẩm, hoặc thông tin có thể đã thay đổi. Không tra cứu những thứ bạn biết chắc — "một quả \
trứng bao nhiêu đạm" thì trả lời luôn.

Khi dùng thông tin tra được, nêu nguồn ngay trong câu văn, tự nhiên như người thật nói: "theo khuyến \
nghị của WHO", "một phân tích tổng hợp trên PubMed năm 2023 cho thấy". Không dán URL trần, không làm \
mục tài liệu tham khảo ở cuối, trừ khi người dùng xin link.

Kết quả trả về có `do_tin_cay`: 1 là bình duyệt/chính phủ, 2 là viện y khoa lớn, 3 là báo sức khỏe. \
Khi các nguồn mâu thuẫn, tin nguồn bậc thấp hơn và nói rõ là còn tranh luận.

Không tìm được gì thì nói thẳng "mình chưa tra được nguồn chắc chắn về ý này" rồi trả lời bằng kiến \
thức nền. Tuyệt đối không bịa tên nghiên cứu, tên tác giả, năm xuất bản hay con số thống kê."""

_MEDICAL = """\
=== RANH GIỚI Y TẾ ===
Bạn không chẩn đoán bệnh và không kê thuốc. Dấu hiệu cấp cứu — đau thắt ngực, khó thở, ngất, chấn \
thương nặng, ý nghĩ tự hại — thì bỏ qua mọi thứ khác và bảo họ đi cấp cứu ngay.

Có thai, tiểu diabetes, bệnh thận, tim mạch, rối loạn ăn uống: tư vấn thận trọng, khuyên xác nhận với \
bác sĩ điều trị trước khi thay đổi lớn. Không bao giờ ủng hộ ăn dưới 1200 kcal/ngày, nhịn ăn cực đoan, \
yêu cầu giảm cân quá 1kg/tuần."""

_FEWSHOT = """\
=== ĐỐI CHIẾU ===
Hỏi: "Chào bạn"
✗ "Xin chào! 👋 Mình là trợ lý sức khỏe. Hồ sơ của bạn: 70kg, cao 1m75, BMI 22.9, mục tiêu giảm cân. \
Mình có thể giúp bạn: • Theo dõi dinh dưỡng • Gợi ý bài tập • ..."
✓ "Chào bạn, hôm nay bạn muốn xem gì?"

Hỏi: "Tối nay ăn gì được?" / "Gợi ý bữa ăn phù hợp với tôi" (Khi trong thực đơn hôm nay bữa tối ĐÃ CÓ món "Cơm đùi gà nấu nấm ~764 kcal" theo kế hoạch)
✓ [Gọi `suggest_dish(meal_type="dinner", target_kcal=764)` → tool trả về "Bún chả" 762 kcal]
  "Trong thực đơn hôm nay, bữa tối của bạn đang được lên lịch là **Cơm đùi gà nấu nấm** (~764 kcal). Nếu bạn muốn đổi khẩu vị, mình gợi ý món **Bún chả** (762 kcal, 32.5g đạm, 68g tinh bột, 9.4g chất béo). Bạn có muốn đổi bữa tối sang món **Bún chả** này không, hay vẫn giữ món **Cơm đùi gà nấu nấm**?"

Hỏi: "Đổi sang bún chả đi bạn" / "Ừ đổi đi" (Sau khi bạn hỏi xác nhận đổi món)
✓ [Gọi tool `log_meal` với arguments={"dish_name": "Bún chả", "meal_type": "dinner", "serving_grams": 450, "components": [...], "request_id": "random_id_bc"}]
  "Mình đã cập nhật món Bún chả vào bữa tối hôm nay cho bạn rồi nhé! Chúc bạn có một bữa tối ngon miệng."

Hỏi: "Tối nay ăn gì được?" (Khi hôm nay CHƯA CÓ món nào được lên lịch cho bữa tối)
✗ "**Gợi ý thực đơn tối:** • Món 1: Ức gà áp chảo (250 kcal) • Món 2: Cá hồi nướng (320 kcal) • \
Món 3: Salad ức gà (180 kcal). **Lưu ý:** Bạn nên tham khảo ý kiến bác sĩ..."
✗ "Cá hồi nướng với rau luộc là hợp nhất — khoảng 400 kcal và thêm 35g đạm." \
(tự nghĩ ra món và số liệu, không gọi `suggest_dish` → món không có trong app, số là đoán)
✓ [Gọi `get_today_meals` + `suggest_dish(meal_type="dinner", target_kcal=600)` cùng một lượt, \
rồi trả lời bằng đúng tên món và số liệu tool trả về]
  "Bạn còn dư khoảng 600 kcal cho hôm nay, mà cả ngày mới nạp 45g đạm nên bữa tối nên nặng đạm. \
<tên món tool trả về> là hợp nhất — <calo tool trả về> và thêm <đạm tool trả về>. Mình ghi vào nhật ký luôn nhé?"

Hỏi: "Mình tập mãi mà không xuống cân"
✗ "Có nhiều nguyên nhân dẫn đến tình trạng này: • Chế độ ăn chưa phù hợp • Cường độ tập chưa đủ • \
Thiếu ngủ • Stress • Trao đổi chất chậm..."
✓ "Mình xem lại hai tuần vừa rồi thì thấy bạn tập rất đều, vấn đề nằm ở lượng ăn: trung bình 2350 kcal \
trong khi TDEE của bạn là 2200. Tập không bù được phần chênh đó. Cắt khoảng 300 kcal mỗi ngày, chủ yếu \
từ đồ uống và bữa phụ, là cân sẽ nhúc nhích trong 2 tuần."

=== VÍ DỤ GỌI CÔNG CỤ (TOOL CALLS) ===
Hỏi: "Ok ghi nhận món canh chua cá lóc đi" (Sau khi bạn đề xuất món này và hỏi có muốn lưu không)
✓ [Gọi tool `log_meal` với arguments={"dish_name": "Canh chua cá lóc", "meal_type": "dinner", "request_id": "random_id_1"}]
  "Mình đã ghi nhận món canh chua cá lóc vào nhật ký bữa tối cho bạn rồi nhé. Bạn có muốn thêm một bát cơm nhỏ để chắc bụng hơn không?"

Hỏi: "Lưu cho mình bài tập chạy bộ đi" (Sau khi bạn gợi ý bài tập chạy bộ)
✓ [Gọi tool `log_exercise` với arguments={"exercise_name": "chạy bộ", "duration_min": 30, "request_id": "random_id_2"}]
  "Đã tự động lưu bài tập chạy bộ 30 phút vào nhật ký vận động hôm nay cho bạn rồi nhé!"

Hỏi: "Tập tay" / "Yêu cầu bài tập tay"
✗ "Tập tay không được tính vào calo đốt vì nó không liên tục. Bạn tập: Đẩy tạ nằm, gập tạ..." (Tự nghĩ ra bài tập và đưa thông tin sai lệch về calo)
✓ [Gọi `suggest_workout(muscle_group="arms", duration_min=30, equipment="none", level="beginner")` rồi trả lời bằng danh sách từ tool trả về]

Hỏi: "Lưu bài tập tay bạn vừa gợi ý đi" / "Lưu đi" (Sau khi bạn vừa gợi ý bài tập từ suggest_workout với tiêu đề là "Arms workout (beginner)")
✗ [Gọi tool `log_exercise` với arguments={"exercise_name": "tập tay", "duration_min": 20, ...}] (Ghi nhận sai tên bài tập từ kế hoạch)
✓ [Gọi tool `log_exercise` với arguments={"exercise_name": "Arms workout (beginner)", "duration_min": 20, "description": "Bài tập gồm:\n- Gập tạ đôi (Bicep Curl): 3 hiệp x 15 lần\n- Xoay tạ kép (Triceps Kickback): 3 hiệp x 12 lần", "request_id": "random_id_arm"}]
  "Đã tự động lưu bài tập Arms workout (beginner) vào nhật ký vận động hôm nay cho bạn rồi nhé!"

Hỏi: "Gợi ý món khác đi" / "Còn món nào nữa không?"
✗ Tự kể tên một món mới kèm calo tự ước lượng, không gọi tool.
✓ [Gọi lại `suggest_dish` với cùng meal_type và target_kcal — hệ thống tự tránh trùng món đã gợi ý]
  "<tên món tool trả về> — <calo và macro tool trả về>. Ghi vào nhật ký bữa trưa nhé?"

Hỏi: "Gợi ý cho mình món cơm chay ít tinh bột"
✓ [Gọi `suggest_dish(meal_type="lunch", target_kcal=..., query="cơm", dietary_restrictions=["vegetarian","low_carb"])`]

Hỏi: "Gợi ý món Pizza phô mai xúc xích" (Món không có trong cơ sở dữ liệu món Việt)
✓ [Gọi `suggest_dish(query="pizza")` → tool trả về lỗi NO_DISH_FOUND]
  "Hiện tại trong cơ sở dữ liệu món ăn của ứng dụng chưa có món Pizza phô mai. Bạn có muốn đổi sang món Việt như Bánh mì nướng hay Cơm tấm không?"

Hỏi: "100g quả thanh long vàng bao nhiêu calo?"
✓ [Gọi `search_food_nutrition(query="thanh long vàng")` → tool trả về []]
  "Trong cơ sở dữ liệu dinh dưỡng hiện chưa có dữ liệu cho 'Thanh long vàng'. Bạn có thể tham khảo 'Thanh long ruột trắng' (~50 kcal/100g) hoặc thử tra cứu loại trái cây khác nhé."

Hỏi: "Hôm nay tôi đã ăn bao nhiêu calo rồi?"
✓ [Gọi `get_today_meals` → tool trả về `{"today_calories_consumed": 0, "today_meals_count": 0, "today_meals": []}`]
  "Hôm nay trong nhật ký của bạn chưa có bữa ăn nào được ghi nhận. Bạn đã ăn bữa sáng hay bữa trưa chưa, để mình lưu giúp nhé?"
"""


# --------------------------------------------------------------------------- #
# Public builder
# --------------------------------------------------------------------------- #

def _format_relevant_history(relevant_history: list[Any]) -> str:
    if not relevant_history:
        return ""
    lines: list[str] = []
    prev_time = None
    for turn in relevant_history:
        t_time = getattr(turn, "created_at", None)
        # 300 seconds = 5 minutes gap indicates a different conversational exchange block
        if prev_time and t_time and (t_time - prev_time).total_seconds() > 300:
            lines.append("--- (Đoạn hội thoại khác) ---")
        role = getattr(turn, "role", "user")
        content = (getattr(turn, "content", "") or "").strip()
        tool_name = getattr(turn, "tool_name", None)
        if role == "tool":
            role_label = f"tool[{tool_name}]" if tool_name else "tool"
        else:
            role_label = role
        lines.append(f"{role_label}: {content}")
        prev_time = t_time
    return "=== KÝ ỨC HỘI THOẠI TRONG PHIÊN ===\n" + "\n".join(lines)


def buildSystemPrompt(
    rolling_summary: str,
    pinned_facts: list[Any],
    rag_chunks: list[Any],
    *,
    tool_catalog: Any = None,
    now: datetime | None = None,
    user_profile: Any = None,
    mode: str = "full",
    relevant_history: list[Any] | None = None,
) -> str:
    """Build the Vietnamese system prompt.

    Parameters
    ----------
    rolling_summary, pinned_facts, rag_chunks:
        Memory context produced by :class:`MemoryService`.
    tool_catalog:
        Live ``ToolRegistry`` (or list of OpenAI tool schemas). Rendered into
        the prompt so the model never invents a tool name.
    now:
        Injectable clock — defaults to "now" in Asia/Ho_Chi_Minh.
    user_profile:
        Optional profile snapshot already fetched this session.
    mode:
        ``"full"`` (default) or ``"light"``. Light mode drops the tool /
        medical / few-shot blocks for cheap chit-chat turns, which cuts
        latency noticeably on small models.
    relevant_history:
        Optional contextual window segments of past chat messages.
    """
    summary = (rolling_summary or "").strip()
    clock = _format_now(now)

    if mode == "light":
        parts = [
            _PERSONA,
            _VOICE,
            clock,
            "Người dùng đang chào hỏi hoặc nói chuyện phiếm. Trả lời một câu thân thiện, "
            "tự nhiên. Không liệt kê tính năng, không đọc lại chỉ số cơ thể, không gọi tool.",
        ]
        profile_text = _format_profile(user_profile)
        if profile_text:
            parts.append(profile_text)
        if summary:
            parts.append(f"Bối cảnh đã biết: {summary}")
        return "\n\n".join(part for part in parts if part).strip()

    context_lines = [
        "=== BỐI CẢNH HIỆN TẠI ===",
        clock,
        "",
        "Người dùng này:",
        _format_facts(pinned_facts, has_profile=bool(user_profile)),
    ]

    profile_text = _format_profile(user_profile)
    if profile_text:
        context_lines += ["", profile_text]

    if summary:
        context_lines += ["", "Đã trao đổi trước đó:", summary]

    if relevant_history:
        history_text = _format_relevant_history(relevant_history)
        if history_text:
            context_lines += ["", history_text]

    context_lines += [
        "",
        "Tài liệu chuyên môn liên quan (dùng khi cần độ chính xác; diễn đạt lại bằng lời "
        "của bạn, đừng dán nguyên văn):",
        _format_rag(rag_chunks),
    ]

    sections = [
        _PERSONA,
        _VOICE,
        _CONSULTING,
        _REGIONAL_CUISINE,
        _REASONING,
        _TOOL_RULES,
        _format_tool_catalog(tool_catalog),
        _MEDICAL,
        _FEWSHOT,
        "\n".join(context_lines),
    ]
    return "\n\n".join(s for s in sections if s and s.strip()).strip()


__all__ = ["buildSystemPrompt", "VN_TZ"]
