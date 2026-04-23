"""
Prompt builder — tạo prompt tối ưu theo intent.
"""
from models.schemas import UserContext, KnowledgeChunk
from db.session_store import ChatTurn
from services.tdee_calculator import calculate_bmr, calculate_tdee, get_recommended_calories
from services.intent_classifier import Intent

HEALTH_GOAL_VN = {
    "lose_weight": "Giảm cân",
    "maintain": "Duy trì cân nặng",
    "gain_muscle": "Tăng cơ",
}
ACTIVITY_LEVEL_VN = {
    "sedentary": "Ít vận động",
    "light": "Nhẹ",
    "moderate": "Vừa phải",
    "active": "Tích cực",
    "very_active": "Rất tích cực",
}

# Tỉ lệ protein theo mục tiêu (g/kg cân nặng) — dựa theo khuyến nghị dinh dưỡng
PROTEIN_PER_KG = {
    "lose_weight": 2.0,   # Cao protein để giữ cơ khi giảm cân
    "maintain":    1.6,   # Duy trì cơ bắp
    "gain_muscle": 2.2,   # Tối đa hóa tổng hợp cơ
}

# Fat tối thiểu (g/kg) — cần thiết cho hormone và hấp thụ vitamin
FAT_MIN_PER_KG = 0.8

def _calc_bmi(weight_kg: float, height_cm: float) -> tuple[float, str]:
    """Tính BMI và phân loại."""
    bmi = weight_kg / ((height_cm / 100) ** 2)
    if bmi < 18.5:
        category = "Thiếu cân"
    elif bmi < 23:
        category = "Bình thường"
    elif bmi < 25:
        category = "Thừa cân nhẹ"
    elif bmi < 30:
        category = "Thừa cân"
    else:
        category = "Béo phì"
    return round(bmi, 1), category

def _calc_macro_targets(recommended_kcal: float, health_goal: str,
                        weight_kg: float, height_cm: float) -> dict:
    """
    Tính gram mục tiêu cho từng macro dựa trên chỉ số cơ thể.
    - Protein: g/kg cân nặng theo mục tiêu
    - Fat: tối thiểu 0.8g/kg, điều chỉnh theo BMI
    - Carbs: phần còn lại
    """
    bmi, bmi_cat = _calc_bmi(weight_kg, height_cm)

    # Protein theo cân nặng
    protein_per_kg = PROTEIN_PER_KG.get(health_goal, 1.6)
    protein_g = round(protein_per_kg * weight_kg)

    # Fat: tối thiểu 0.8g/kg, giảm nếu BMI cao
    fat_per_kg = FAT_MIN_PER_KG
    if bmi >= 25:
        fat_per_kg = 0.7  # Giảm fat nếu thừa cân
    if health_goal == "lose_weight":
        fat_per_kg = max(0.7, fat_per_kg - 0.1)
    fat_g = round(fat_per_kg * weight_kg)

    # Carbs = phần còn lại sau protein và fat
    protein_kcal = protein_g * 4
    fat_kcal = fat_g * 9
    carbs_kcal = max(0, recommended_kcal - protein_kcal - fat_kcal)
    carbs_g = round(carbs_kcal / 4)

    # Tính % thực tế
    total_kcal = protein_kcal + fat_kcal + carbs_kcal
    return {
        "protein_g":   protein_g,
        "carbs_g":     carbs_g,
        "fat_g":       fat_g,
        "protein_pct": round(protein_kcal / total_kcal * 100) if total_kcal > 0 else 0,
        "carbs_pct":   round(carbs_kcal   / total_kcal * 100) if total_kcal > 0 else 0,
        "fat_pct":     round(fat_kcal     / total_kcal * 100) if total_kcal > 0 else 0,
        "bmi":         bmi,
        "bmi_cat":     bmi_cat,
        "protein_per_kg": protein_per_kg,
    }

# System prompt cơ bản — ngắn gọn, rõ ràng
_BASE_SYSTEM = (
    "Bạn là trợ lý sức khỏe AI. Trả lời HOÀN TOÀN bằng tiếng Việt, ngắn gọn, chuyên nghiệp.\n"
    "QUAN TRỌNG: Tên bài tập PHẢI là tiếng Anh (ví dụ: Push-up, Squat, Plank, Deadlift, Bicep Curl).\n"
    "Ngoại lệ: Chỉ 4 bài tập sau được dùng tiếng Việt: 'Chạy bộ', 'Hít đất', 'Đi bộ', 'Gập bụng'.\n"
    "Tên món ăn và nguyên liệu dùng tiếng Việt.\n"
    "KHÔNG bịa đặt tên người dùng — không có tên trong dữ liệu thì KHÔNG đề cập tên.\n"
    "KHÔNG thêm câu xã giao thừa như 'Vui vẻ!', 'Chúc bạn...', 'Tuyệt vời!', 'Rất vui được...'.\n"
    "Đi thẳng vào nội dung, không mở đầu bằng lời chào hay câu cảm thán.\n\n"
    "PHÂN CHIA CALORIES VÀ MACRO CHO 4 BỮA ĂN/NGÀY:\n"
    "- Bữa sáng: 30% tổng calories\n"
    "- Bữa trưa: 35% tổng calories\n"
    "- Bữa phụ: 10% tổng calories (ăn nhẹ)\n"
    "- Bữa tối: 25% tổng calories\n"
    "Khi gợi ý bữa ăn, tính calories theo tỷ lệ trên.\n\n"
    "KHI GỢI Ý BỮA ĂN:\n"
    "- Chỉ nêu: hôm nay đã ăn bao nhiêu calo, còn lại bao nhiêu\n"
    "- Sau đó gợi ý bữa ăn với nguyên liệu và khẩu phần cụ thể\n"
    "- KHÔNG nêu mục tiêu macro, đã ăn protein/carbs/fat, còn cần bổ sung\n"
    "- KHÔNG nêu quy tắc cân bằng dinh dưỡng, lời khuyên theo BMI\n"
    "- KHÔNG giải thích lý do chọn món\n\n"
    "=== QUY TẮC FORMAT TUYỆT ĐỐI (KHÔNG ĐƯỢC VI PHẠM) ===\n"
    "Chỉ được dùng ĐÚNG 2 loại block đặc biệt sau, KHÔNG được dùng bất kỳ tag nào khác:\n"
    "  1. [ACTION_DATA] ... [/ACTION_DATA]   — chứa JSON bài tập hoặc món ăn\n"
    "  2. [SUGGESTIONS] ... [/SUGGESTIONS]  — chứa JSON array gợi ý\n\n"
    "NGHIÊM CẤM:\n"
    "- Viết 'SUGGESTIONS' không có dấu [ ] bao quanh\n"
    "- Dùng **SUGGESTIONS**, **ACTION_DATA** hay bất kỳ markdown bold nào cho tag\n"
    "- Tự tạo tag mới như [DATA], [CUSTOM_DATA], [RESULT], v.v.\n"
    "- Viết JSON ngoài block [ACTION_DATA]\n\n"
)

# Phần hướng dẫn ACTION_DATA — chỉ thêm khi cần
_ACTION_DATA_GUIDE = (
    "Khi gợi ý món ăn hoặc bài tập CỤ THỂ, PHẢI thêm block [ACTION_DATA] ở CUỐI (trước [SUGGESTIONS]).\n\n"
    "QUY TẮC BẮT BUỘC cho món ăn:\n"
    "- Mỗi action là MỘT nguyên liệu riêng lẻ (ví dụ: 'Gạo tẻ', 'Thịt heo nạc', 'Rau muống')\n"
    "- KHÔNG gộp nhiều nguyên liệu thành 1 action (KHÔNG viết 'Cơm heo quay', 'Bữa tối lành mạnh')\n"
    "- Thêm trường 'meal_name' vào structured để đặt tên tổng quát\n"
    "- QUAN TRỌNG: Mỗi nguyên liệu PHẢI có trường 'dish_name' trong details để ghi tên MÓN ĂN chứa nguyên liệu đó\n"
    "  Ví dụ: Gạo tẻ và Thịt gà đều thuộc món 'Cơm gà' → dish_name: 'Cơm gà'\n"
    "  Ví dụ: Khoai lang và Trứng gà thuộc 2 món khác nhau → dish_name khác nhau\n"
    "- Mỗi nguyên liệu phải có serving_grams cụ thể\n"
    "- calories/protein/carbs/fat là giá trị trên 100g của nguyên liệu đó\n"
    "- QUAN TRỌNG: meal_type phải khớp với bữa ăn đang gợi ý:\n"
    "  * Bữa sáng → meal_type: \"breakfast\"\n"
    "  * Bữa trưa → meal_type: \"lunch\"\n"
    "  * Bữa tối → meal_type: \"dinner\"\n"
    "  * Bữa phụ → meal_type: \"snack\"\n\n"
    "Ví dụ ĐÚNG cho bữa trưa 'Cơm gà':\n"
    "[ACTION_DATA]\n"
    '{"type":"structured","text":"Cơm gà","meal_name":"Cơm gà","actions":[\n'
    '  {"kind":"food","wger_id":0,"name":"Gạo tẻ","details":{"calories":344,"protein":7.9,"carbs":76,"fat":1.0,"meal_type":"lunch","dish_name":"Cơm gà","serving_grams":200}},\n'
    '  {"kind":"food","wger_id":0,"name":"Thịt gà luộc","details":{"calories":165,"protein":31,"carbs":0,"fat":3.6,"meal_type":"lunch","dish_name":"Cơm gà","serving_grams":120}},\n'
    '  {"kind":"food","wger_id":0,"name":"Rau muống xào","details":{"calories":19,"protein":2.6,"carbs":3,"fat":0.2,"meal_type":"lunch","dish_name":"Cơm gà","serving_grams":150}}\n'
    "]}\n"
    "[/ACTION_DATA]\n\n"
    "Ví dụ ĐÚNG cho cả ngày (nhiều món, nhiều bữa):\n"
    "[ACTION_DATA]\n"
    '{"type":"structured","text":"Thực đơn cả ngày","meal_name":"Thực đơn cả ngày","actions":[\n'
    '  {"kind":"food","wger_id":0,"name":"Bánh mì","details":{"calories":249,"protein":7.9,"carbs":52.6,"fat":0.8,"meal_type":"breakfast","dish_name":"Bánh mì trứng","serving_grams":100}},\n'
    '  {"kind":"food","wger_id":0,"name":"Trứng gà","details":{"calories":166,"protein":14.8,"carbs":0.5,"fat":11.6,"meal_type":"breakfast","dish_name":"Bánh mì trứng","serving_grams":60}},\n'
    '  {"kind":"food","wger_id":0,"name":"Gạo tẻ","details":{"calories":344,"protein":7.9,"carbs":76,"fat":1.0,"meal_type":"lunch","dish_name":"Cơm thịt heo xào rau","serving_grams":200}},\n'
    '  {"kind":"food","wger_id":0,"name":"Thịt heo nạc","details":{"calories":139,"protein":19,"carbs":0,"fat":7,"meal_type":"lunch","dish_name":"Cơm thịt heo xào rau","serving_grams":100}},\n'
    '  {"kind":"food","wger_id":0,"name":"Rau cải xanh","details":{"calories":16,"protein":1.7,"carbs":1.9,"fat":0.2,"meal_type":"lunch","dish_name":"Cơm thịt heo xào rau","serving_grams":150}}\n'
    "]}\n"
    "[/ACTION_DATA]\n\n"
    "QUY TẮC BẮT BUỘC cho bài tập:\n"
    "- Tên bài tập PHẢI là tiếng Anh (Push-up, Squat, Plank, Deadlift, Bicep Curl, Tricep Dip, Leg Raise, Lunge, etc.)\n"
    "- NGOẠI LỆ: Chỉ 4 bài tập sau được dùng tiếng Việt: 'Chạy bộ', 'Hít đất', 'Đi bộ', 'Gập bụng'\n"
    "- Các bài tập khác PHẢI dùng tiếng Anh (KHÔNG viết 'Nâng tạ', 'Lắng tay', 'Nhảy dây')\n"
    "- Chỉ dùng bài tập từ danh sách [WGER_EXERCISE id=X] đã cung cấp\n"
    "- wger_id PHẢI là số id thực từ danh sách, KHÔNG dùng 0 nếu có trong danh sách\n"
    "- Mỗi action chỉ có 2 trường trong details: duration (phút) và calories_burned (kcal)\n"
    "- TUYỆT ĐỐI KHÔNG thêm trường 'type', 'category', 'difficulty', 'muscle_group' hay bất kỳ trường nào khác\n"
    "- CHỈ GHI: duration, calories_burned - KHÔNG GHI GÌ THÊM\n\n"
    "Ví dụ ĐÚNG cho bài tập:\n"
    "[ACTION_DATA]\n"
    '{"type":"structured","text":"Bài tập gợi ý","actions":[\n'
    '  {"kind":"exercise","wger_id":0,"name":"Hít đất","details":{"duration":15,"calories_burned":80}},\n'
    '  {"kind":"exercise","wger_id":0,"name":"Squat","details":{"duration":20,"calories_burned":120}},\n'
    '  {"kind":"exercise","wger_id":0,"name":"Gập bụng","details":{"duration":10,"calories_burned":50}}\n'
    "]}\n"
    "[/ACTION_DATA]\n\n"
    "Ví dụ SAI (KHÔNG làm như thế này):\n"
    '  {"kind":"exercise","wger_id":0,"name":"Nâng tạ","details":{...}}  ← SAI, phải dùng "Bicep Curl" hoặc "Deadlift"\n'
    '  {"kind":"exercise","wger_id":0,"name":"Nhảy dây","details":{...}}  ← SAI, phải dùng "Jump Rope"\n'
    '  {"kind":"food","wger_id":0,"name":"Cơm","details":{"meal_type":"breakfast","serving_grams":200}}  ← SAI vì gợi ý bữa trưa nhưng dùng meal_type: "breakfast"\n'
    '  {"kind":"exercise","wger_id":0,"name":"Squat","details":{"duration":30,"calories_burned":120,"type":"strength"}}  ← SAI vì có trường "type"\n\n'
    "Quy tắc wger_id: lấy từ [WGER_EXERCISE id=X] hoặc [WGER_INGREDIENT id=X] nếu có trong dữ liệu tham khảo, không thì dùng 0.\n\n"
)

# Hướng dẫn SUGGESTIONS — luôn thêm, format cứng
_SUGGESTIONS_GUIDE = (
    "=== BLOCK [SUGGESTIONS] ===\n"
    "Cuối MỌI response, PHẢI thêm đúng block này — KHÔNG được bỏ qua:\n\n"
    "[SUGGESTIONS]\n"
    '["Gợi ý câu hỏi 1","Gợi ý câu hỏi 2","Gợi ý câu hỏi 3"]\n'
    "[/SUGGESTIONS]\n\n"
    "Quy tắc:\n"
    "- Phải có đúng dấu [ ở đầu SUGGESTIONS và [/ ở đầu /SUGGESTIONS]\n"
    "- Nội dung là JSON array các string, 2-3 gợi ý liên quan đến cuộc trò chuyện\n"
    "- KHÔNG viết 'SUGGESTIONS' không có dấu ngoặc, KHÔNG dùng **SUGGESTIONS**\n"
)

# Hướng dẫn hỏi thêm thông tin
_CLARIFY_GUIDE = (
    "Nếu yêu cầu chưa đủ thông tin, hỏi ngược lại TỐI ĐA 2 câu ngắn.\n"
    "KHÔNG thêm [ACTION_DATA] khi đang hỏi thêm.\n\n"
)

# Hướng dẫn cân bằng dinh dưỡng — thêm vào nutrition intent
def _nutrition_balance_guide(macro: dict, eaten_protein: float, eaten_carbs: float, eaten_fat: float) -> str:
    remaining_protein = max(0, macro["protein_g"] - eaten_protein)
    remaining_carbs   = max(0, macro["carbs_g"]   - eaten_carbs)
    remaining_fat     = max(0, macro["fat_g"]      - eaten_fat)

    guide = (
        f"Mục tiêu macro/ngày: Protein {macro['protein_g']}g ({macro['protein_per_kg']}g/kg cân nặng) | "
        f"Carbs {macro['carbs_g']}g | Fat {macro['fat_g']}g\n"
    )
    if eaten_protein > 0 or eaten_carbs > 0 or eaten_fat > 0:
        guide += (
            f"Đã ăn hôm nay: Protein {eaten_protein:.0f}g | Carbs {eaten_carbs:.0f}g | Fat {eaten_fat:.0f}g\n"
            f"Còn cần bổ sung: Protein {remaining_protein:.0f}g | Carbs {remaining_carbs:.0f}g | Fat {remaining_fat:.0f}g\n"
        )

    # Lời khuyên theo BMI
    bmi_cat = macro.get("bmi_cat", "Bình thường")
    if bmi_cat == "Thiếu cân":
        guide += "Người dùng thiếu cân — ưu tiên thực phẩm giàu calo lành mạnh (hạt, bơ, cá béo, sữa).\n"
    elif bmi_cat in ("Thừa cân", "Thừa cân nhẹ"):
        guide += "Người dùng thừa cân — ưu tiên rau xanh, protein nạc, hạn chế tinh bột trắng và chất béo bão hòa.\n"
    elif bmi_cat == "Béo phì":
        guide += "Người dùng béo phì — tập trung giảm calo, tăng rau xanh và protein nạc, tránh đường và chất béo xấu.\n"

    guide += (
        "\nQUY TẮC CÂN BẰNG DINH DƯỠNG khi gợi ý bữa ăn:\n"
        "1. Mỗi bữa phải có ĐỦ 3 nhóm: tinh bột (cơm/bún/bánh mì) + đạm (thịt/cá/trứng/đậu) + rau xanh\n"
        "2. Ưu tiên bổ sung macro còn thiếu nhiều nhất\n"
        "3. Tránh gợi ý quá nhiều chất béo hoặc tinh bột nếu đã đủ\n"
        "4. Mỗi bữa ít nhất 1 nguồn protein và 1 loại rau\n"
        "5. Protein nên từ nguồn đa dạng: thịt nạc, cá, trứng, đậu phụ\n\n"
    )
    return guide


class PromptBuilder:
    def _detect_meal_type(self, message: str) -> str | None:
        """Phát hiện bữa ăn nào đang được yêu cầu từ message."""
        import re
        text = message.lower()
        
        # Kiểm tra từ khóa
        if re.search(r'\b(bữa sáng|sáng|breakfast|morning)\b', text):
            return "breakfast"
        if re.search(r'\b(bữa trưa|trưa|lunch|noon)\b', text):
            return "lunch"
        if re.search(r'\b(bữa tối|tối|dinner|evening)\b', text):
            return "dinner"
        if re.search(r'\b(bữa phụ|phụ|snack|xế)\b', text):
            return "snack"
        
        return None
    
    def build(
        self,
        user_context: UserContext,
        rag_chunks: list[KnowledgeChunk],
        history: list[ChatTurn],
        user_message: str,
        intent: Intent = Intent.GENERAL,
        max_history: int = 8,
        wger_exercises_text: str = "",
    ) -> list[dict]:
        bmr = calculate_bmr(
            age=user_context.age,
            gender=user_context.gender,
            height_cm=user_context.height,
            weight_kg=user_context.weight,
        )
        tdee = calculate_tdee(bmr, user_context.activity_level)
        recommended = get_recommended_calories(tdee, user_context.health_goal)
        macro = _calc_macro_targets(recommended, user_context.health_goal,
                                    user_context.weight, user_context.height)

        goal = HEALTH_GOAL_VN.get(user_context.health_goal, user_context.health_goal)
        activity = ACTIVITY_LEVEL_VN.get(user_context.activity_level, user_context.activity_level)
        gender = "Nam" if user_context.gender == "male" else "Nữ"

        # User profile — ngắn gọn cho nutrition, đầy đủ cho các intent khác
        if intent == Intent.NUTRITION_REQUEST:
            # Chỉ cần thông tin calo cho gợi ý bữa ăn - KHÔNG cần macro
            user_profile = (
                f"Calo khuyến nghị: {recommended:.0f} kcal/ngày\n"
                f"Phân chia: Sáng {recommended*0.30:.0f} kcal | Trưa {recommended*0.35:.0f} kcal | "
                f"Phụ {recommended*0.10:.0f} kcal | Tối {recommended*0.25:.0f} kcal\n"
            )
        else:
            # Đầy đủ thông tin cho các intent khác
            user_profile = (
                f"Người dùng: {gender}, {user_context.age} tuổi, "
                f"{user_context.height:.0f}cm, {user_context.weight:.0f}kg | "
                f"BMI: {macro['bmi']} ({macro['bmi_cat']}) | "
                f"Mục tiêu: {goal} | Hoạt động: {activity}\n"
                f"Calo khuyến nghị: {recommended:.0f} kcal/ngày (BMR={bmr:.0f}, TDEE={tdee:.0f})\n"
                f"Macro mục tiêu: Protein {macro['protein_g']}g ({macro['protein_per_kg']}g/kg) | "
                f"Carbs {macro['carbs_g']}g | Fat {macro['fat_g']}g\n"
            )

        # Tính macro đã ăn hôm nay từ today_meals
        eaten_protein = sum(float(m.get("protein", 0)) for m in user_context.today_meals)
        eaten_carbs   = sum(float(m.get("carbs",   0)) for m in user_context.today_meals)
        eaten_fat     = sum(float(m.get("fat",     0)) for m in user_context.today_meals)

        # Today's activity context
        today_context = ""
        if intent == Intent.NUTRITION_REQUEST:
            # Cho nutrition: chỉ cần tóm tắt ngắn gọn
            if user_context.today_calories_consumed is not None and user_context.today_meals_count:
                remaining = recommended - user_context.today_calories_consumed
                today_context = (
                    f"Hôm nay đã ăn: {user_context.today_calories_consumed:.0f} kcal "
                    f"({user_context.today_meals_count} bữa), còn lại: {remaining:.0f} kcal\n"
                )
        else:
            # Cho các intent khác: đầy đủ thông tin
            if user_context.today_calories_consumed is not None or user_context.today_calories_burned is not None:
                today_parts = []
                if user_context.today_calories_consumed is not None and user_context.today_meals_count:
                    remaining = recommended - user_context.today_calories_consumed
                    today_parts.append(
                        f"Hôm nay đã ăn: {user_context.today_calories_consumed:.0f} kcal "
                        f"({user_context.today_meals_count} bữa), còn lại: {remaining:.0f} kcal"
                    )
                if user_context.today_calories_burned is not None and user_context.today_exercises_count:
                    today_parts.append(
                        f"Đã tập: {user_context.today_exercises_count} bài, "
                        f"đốt {user_context.today_calories_burned:.0f} kcal"
                    )
                if today_parts:
                    today_context = "Hoạt động hôm nay: " + " | ".join(today_parts) + "\n"

        # Chi tiết bữa ăn hôm nay - chỉ hiển thị cho intent không phải NUTRITION_REQUEST
        if user_context.today_meals and intent != Intent.NUTRITION_REQUEST:
            meal_type_vn = {"sang": "Sáng", "trua": "Trưa", "toi": "Tối", "phu": "Phụ",
                            "breakfast": "Sáng", "lunch": "Trưa", "dinner": "Tối", "snack": "Phụ"}
            meal_lines = []
            for m in user_context.today_meals:
                mtype = meal_type_vn.get(m.get("meal_type", ""), m.get("meal_type", ""))
                name = m.get("name", "")
                cal = m.get("calories", "?")
                items = m.get("items", [])
                status = "✓" if m.get("is_completed") else "○"
                if items:
                    items_str = ", ".join(items)
                    meal_lines.append(f"  {status} [{mtype}] {name}: {items_str} → {cal} kcal")
                else:
                    meal_lines.append(f"  {status} [{mtype}] {name}: {cal} kcal")
            if meal_lines:
                today_context += (
                    "Bữa ăn hôm nay (CHỈ để tham khảo, KHÔNG được lặp lại trong gợi ý):\n"
                    + "\n".join(meal_lines) + "\n"
                )

        # Chi tiết bài tập hôm nay - chỉ hiển thị cho intent không phải NUTRITION_REQUEST
        if user_context.today_exercises and intent != Intent.NUTRITION_REQUEST:
            ex_lines = []
            for e in user_context.today_exercises:
                name = e.get("name", "")
                dur = e.get("duration", "?")
                cal = e.get("calories_burned", "?")
                ex_lines.append(f"  • {name}: {dur} phút, đốt {cal} kcal")
            if ex_lines:
                today_context += (
                    "Bài tập hôm nay (CHỈ để tham khảo, KHÔNG được lặp lại trong gợi ý):\n"
                    + "\n".join(ex_lines) + "\n"
                )

        if today_context:
            today_context = (
                "--- Dữ liệu hôm nay (CHỈ đọc, KHÔNG echo lại) ---\n"
                + today_context
                + "---\n"
                "LƯU Ý: Khi gợi ý, hãy đề xuất món ĂN MỚI khác với những gì đã ăn hôm nay.\n\n"
            )

        user_profile += today_context + "\n"

        # RAG context
        rag_context = ""
        if rag_chunks:
            lines = []
            for chunk in rag_chunks:
                wger_id = chunk.metadata.get("wger_id")
                if wger_id:
                    tag = "WGER_EXERCISE" if chunk.category == "wger_exercise" else "WGER_INGREDIENT"
                    lines.append(f"[{tag} id={wger_id}] {chunk.title}: {chunk.content[:200]}")
                else:
                    lines.append(f"[{chunk.category.upper()}] {chunk.title}: {chunk.content[:200]}")
            rag_context = "Dữ liệu tham khảo:\n" + "\n".join(lines) + "\n\n"

        # Build system prompt theo intent
        system = _BASE_SYSTEM + user_profile

        if rag_context:
            system += rag_context

        # Inject wger exercises thực (ưu tiên cao hơn RAG)
        if wger_exercises_text:
            system += wger_exercises_text + "\n\n"

        # Thêm hướng dẫn theo intent
        if intent == Intent.NUTRITION_REQUEST:
            # Phát hiện bữa ăn nào đang được gợi ý từ user_message
            detected_meal_type = self._detect_meal_type(user_message)
            
            # KHÔNG thêm nutrition_balance_guide - chỉ cần thông tin meal_type
            
            # Thêm thông tin về bữa ăn đang gợi ý
            if detected_meal_type:
                meal_type_map = {
                    "breakfast": "bữa sáng",
                    "lunch": "bữa trưa", 
                    "dinner": "bữa tối",
                    "snack": "bữa phụ"
                }
                meal_type_vn = meal_type_map.get(detected_meal_type, detected_meal_type)
                system += (
                    f"QUAN TRỌNG: Bạn đang gợi ý {meal_type_vn}.\n"
                    f"Trong [ACTION_DATA], TẤT CẢ các nguyên liệu PHẢI có meal_type: \"{detected_meal_type}\"\n"
                    f"KHÔNG được dùng meal_type khác.\n\n"
                )
            
            system += _CLARIFY_GUIDE
            system += _ACTION_DATA_GUIDE

        elif intent == Intent.EXERCISE_REQUEST:
            system += _CLARIFY_GUIDE
            system += _ACTION_DATA_GUIDE

        elif intent == Intent.PROGRESS_CHECK:
            system += _nutrition_balance_guide(macro, eaten_protein, eaten_carbs, eaten_fat)
            system += (
                "Phân tích hoạt động hôm nay: đã đủ calo chưa, macro có cân bằng không, "
                "có nên tập thêm không. Đưa ra 2-3 lời khuyên thực tế.\n\n"
            )
            system += _ACTION_DATA_GUIDE

        elif intent == Intent.CALCULATION:
            system += (
                "Tính toán chính xác dựa trên thông tin người dùng. "
                "Giải thích rõ ràng từng bước.\n\n"
            )

        elif intent == Intent.HEALTH_QUERY:
            system += (
                "Tư vấn dựa trên thông tin sức khỏe người dùng. "
                "Nếu triệu chứng nghiêm trọng (đau ngực, khó thở, chóng mặt nặng), "
                "khuyên đến gặp bác sĩ ngay.\n\n"
            )
            system += _ACTION_DATA_GUIDE

        else:
            system += _ACTION_DATA_GUIDE

        system += _SUGGESTIONS_GUIDE

        # Build messages
        messages: list[dict] = [{"role": "system", "content": system}]

        for turn in history[-max_history:]:
            role = turn.role if turn.role in ("user", "assistant") else "user"
            messages.append({"role": role, "content": turn.content})

        messages.append({"role": "user", "content": user_message})

        return messages


# Singleton
prompt_builder = PromptBuilder()
