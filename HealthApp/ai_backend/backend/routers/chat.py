"""
WebSocket endpoint /chat/stream
"""

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from db.database import AsyncSessionLocal
from db.session_store import session_store
from models.schemas import ChatRequest, ErrorMessage
from services.intent_classifier import intent_classifier, Intent
from services.conversation_flow import flow_manager
from services.llm_service import llm_service
from services.prompt_builder import prompt_builder
from services.rag_service import rag_service
from services.response_parser import response_parser
from services.wger_search import wger_search_service
from services.dish_optimizer import dish_optimizer, MacroTarget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

router = APIRouter()
STREAM_TIMEOUT_SECONDS = 180

# Map từ khóa → meal type
_MEAL_KEYWORDS = {
    "bữa sáng": "breakfast", "ăn sáng": "breakfast", "sáng": "breakfast",
    "bữa trưa": "lunch",     "ăn trưa": "lunch",     "trưa": "lunch",
    "bữa tối": "dinner",     "ăn tối": "dinner",      "tối": "dinner",
    "bữa phụ": "snack",      "ăn phụ": "snack",       "snack": "snack",
}

def _extract_meal_types(message: str) -> list[str]:
    """
    Phát hiện các bữa ăn được đề cập trong message.
    Ví dụ: 'gợi ý bữa trưa và bữa tối' → ['lunch', 'dinner']
    """
    import re
    text = message.lower()
    found: list[str] = []
    seen: set[str] = set()
    # Sắp xếp theo độ dài giảm dần để match cụm dài trước
    for kw, meal_type in sorted(_MEAL_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if re.search(rf'\b{re.escape(kw)}\b', text) and meal_type not in seen:
            found.append(meal_type)
            seen.add(meal_type)
    # Sắp xếp theo thứ tự tự nhiên trong ngày
    order = ["breakfast", "lunch", "snack", "dinner"]
    found.sort(key=lambda x: order.index(x) if x in order else 99)
    return found


@router.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("🔌 WebSocket connected")
    try:
        while True:
            data = await websocket.receive_json()
            request = ChatRequest(**data)
            logger.info("📨 '%s'", request.message[:80])

            try:
                await asyncio.wait_for(
                    _handle_chat(websocket, request),
                    timeout=STREAM_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.error("⏰ TIMEOUT after %ds", STREAM_TIMEOUT_SECONDS)
                await websocket.send_json(
                    ErrorMessage(code="TIMEOUT", message="Phản hồi quá lâu. Vui lòng thử lại.").model_dump()
                )

    except WebSocketDisconnect:
        logger.info("🔌 WebSocket disconnected")
    except Exception as e:
        logger.exception("💥 Unexpected error: %s", e)
        try:
            await websocket.send_json(ErrorMessage(code="INTERNAL_ERROR", message=str(e)).model_dump())
        except Exception:
            pass


async def _send_local(websocket: WebSocket, text: str, suggestions: list[str],
                      structured=None, options: list[str] = None):
    """Gửi response local với typing effect nhẹ."""
    # Stream từng từ
    words = text.split(" ")
    for i, word in enumerate(words):
        await websocket.send_json({"type": "token", "content": word + (" " if i < len(words) - 1 else "")})
        await asyncio.sleep(0.015)

    await websocket.send_json({
        "type": "done",
        "full_response": text,
        "structured": structured,
        "suggestions": suggestions,
        "options": options or [],
    })


async def _handle_chat(websocket: WebSocket, request: ChatRequest) -> None:
    t0 = time.time()
    session_id = request.session_id
    message = request.message.strip()

    # ── 1. Kiểm tra đang trong conversation flow ──────────────────────────
    flow_state = flow_manager.get_state(session_id)
    if flow_state.is_active():
        result = flow_manager.process_answer(session_id, message)
        logger.info("🔄 Flow answer → status=%s", result["status"])

        if result["status"] == "continue":
            # Hỏi tiếp
            await _send_local(
                websocket,
                result["message"],
                suggestions=result.get("suggestions", []),
                options=result.get("options", []),
            )
            session_store.append_turn(session_id, role="user", content=message)
            session_store.append_turn(session_id, role="assistant", content=result["message"])
            return

        elif result["status"] == "cancelled":
            await _send_local(websocket, result["message"], result.get("suggestions", []))
            session_store.append_turn(session_id, role="user", content=message)
            session_store.append_turn(session_id, role="assistant", content=result["message"])
            return

        elif result["status"] == "complete":
            # Flow hoàn thành, gọi LLM với enriched message
            enriched = result.get("enriched_message", message)
            logger.info("✅ Flow complete → enriched: '%s'", enriched)
            
            # Lưu turn của user
            session_store.append_turn(session_id, role="user", content=message)
            
            # Tạo request mới với enriched message và gọi LLM
            enriched_request = ChatRequest(
                session_id=session_id,
                message=enriched,
                user_context=request.user_context,
            )
            # Truyền flag from_flow=True để thay đổi suggestions
            await _call_llm(websocket, enriched_request, t0, from_flow=True,
                            enriched_message=enriched)
            return

    # ── 2. Classify intent ────────────────────────────────────────────────
    intent = intent_classifier.classify(message)
    logger.info("🎯 Intent: %s", intent.value)

    # ── 3. Local response (greeting, v.v.) ───────────────────────────────
    if not intent_classifier.needs_llm(intent):
        local_text = intent_classifier.get_local_response(intent)
        suggestions = intent_classifier.get_default_suggestions(intent)
        logger.info("⚡ Local response (%.2fs)", time.time() - t0)
        await _send_local(websocket, local_text, suggestions)
        session_store.append_turn(session_id, role="user", content=message)
        session_store.append_turn(session_id, role="assistant", content=local_text)
        return

    # ── 4. Bắt đầu conversation flow nếu thiếu thông tin ─────────────────
    if intent == Intent.EXERCISE_REQUEST and _needs_exercise_info(message, request):
        result = flow_manager.start_exercise_flow(session_id)
        logger.info("🔄 Starting exercise flow")
        await _send_local(
            websocket,
            result["message"],
            suggestions=result.get("suggestions", []),
            options=result.get("options", []),
        )
        session_store.append_turn(session_id, role="user", content=message)
        session_store.append_turn(session_id, role="assistant", content=result["message"])
        return

    if intent == Intent.NUTRITION_REQUEST and _needs_nutrition_info(message, request):
        result = flow_manager.start_nutrition_flow(session_id)
        logger.info("🔄 Starting nutrition flow")
        await _send_local(
            websocket,
            result["message"],
            suggestions=result.get("suggestions", []),
            options=result.get("options", []),
        )
        session_store.append_turn(session_id, role="user", content=message)
        session_store.append_turn(session_id, role="assistant", content=result["message"])
        return

    # ── 5. Gọi LLM ───────────────────────────────────────────────────────
    # Kiểm tra yêu cầu nhiều bữa ăn cùng lúc → tách thành từng request
    if intent == Intent.NUTRITION_REQUEST:
        meal_types = _extract_meal_types(message)
        if len(meal_types) >= 2:
            logger.info("🍽 Multi-meal request: %s → splitting", meal_types)
            await _handle_multi_meal(websocket, request, meal_types, t0)
            return

    await _call_llm(websocket, request, t0, intent=intent)


def _needs_exercise_info(message: str, request: ChatRequest = None) -> bool:
    """Kiểm tra xem message có đủ thông tin để tạo bài tập không."""
    import re
    text = message.lower()

    # Nếu là báo cáo / phân tích hôm nay → gửi thẳng LLM
    if re.search(r'(hôm nay tôi đã|đã ăn|đã tập|phân tích|lời khuyên|nhận xét|tổng kết|báo cáo)', text):
        return False

    has_muscle = bool(re.search(
        r'\b(ngực|lưng|chân|vai|bụng|toàn thân|tay|core|arm|leg|back|chest|shoulder|abs)\b', text))
    has_duration = bool(re.search(r'\d+\s*(phút|giờ|min|hour)', text))
    has_equipment = bool(re.search(
        r'\b(không có dụng cụ|tạ tay|tạ đòn|gym|dây kháng lực|bodyweight|barbell|dumbbell)\b', text))

    # Đủ 2/3 thông tin → không cần hỏi thêm
    if sum([has_muscle, has_duration, has_equipment]) >= 2:
        return False

    # Có đủ muscle + duration → không cần hỏi thêm
    if has_muscle and has_duration:
        return False

    # Thiếu thông tin → cần hỏi
    return True


def _needs_nutrition_info(message: str, request: ChatRequest = None) -> bool:
    """Kiểm tra xem message có đủ thông tin để gợi ý bữa ăn không."""
    import re
    text = message.lower()

    # Nếu là báo cáo / phân tích → gửi thẳng LLM
    if re.search(r'(hôm nay tôi đã|đã ăn|đã tập|phân tích|lời khuyên|nhận xét|tổng kết|báo cáo)', text):
        return False

    # Nhận diện loại bữa ăn — cả dạng đầy đủ lẫn rút gọn
    has_meal_type = bool(re.search(
        r'\b(bữa sáng|bữa trưa|bữa tối|bữa phụ|snack|breakfast|lunch|dinner'
        r'|sáng nay|trưa nay|tối nay|buổi sáng|buổi trưa|buổi tối'
        r'|ăn sáng|ăn trưa|ăn tối|ăn phụ'
        r'|sáng|trưa|tối)\b',
        text))
    has_goal = bool(re.search(
        r'\b(giảm cân|tăng cơ|duy trì|ít calo|nhiều protein|low carb|keto)\b', text))
    has_specific = bool(re.search(
        r'\b(thực đơn|meal plan|7 ngày|cả tuần|hôm nay)\b', text))

    if has_meal_type or has_goal or has_specific:
        return False

    # Thiếu thông tin → cần hỏi
    return True


async def _handle_single_meal_optimized(
    websocket: WebSocket, request: ChatRequest, t0: float, from_flow: bool
) -> None:
    """
    Xử lý single meal request bằng optimizer.
    Nhanh hơn LLM (< 1s vs 15s), chính xác hơn về macro.
    """
    from services.meal_optimizer import MacroTarget
    from services.tdee_calculator import calculate_bmr, calculate_tdee, get_recommended_calories
    from services.prompt_builder import _calc_macro_targets
    from services.ingredient_translator import translate_ingredient_name

    # Phát hiện meal type
    meal_type = _extract_meal_types(request.message)
    if not meal_type:
        meal_type = ["lunch"]  # Default
    meal_type = meal_type[0]

    meal_vn = {
        "breakfast": "Bữa sáng", "lunch": "Bữa trưa",
        "dinner": "Bữa tối", "snack": "Bữa phụ",
    }
    meal_ratios = {
        "breakfast": 0.30, "lunch": 0.35, "dinner": 0.25, "snack": 0.10,
    }

    # Tính macro target
    ctx = request.user_context
    bmr = calculate_bmr(ctx.age, ctx.gender, ctx.height, ctx.weight)
    tdee = calculate_tdee(bmr, ctx.activity_level)
    daily_cal = get_recommended_calories(tdee, ctx.health_goal)
    daily_macro = _calc_macro_targets(daily_cal, ctx.health_goal, ctx.weight, ctx.height)

    meal_cal = daily_cal * meal_ratios[meal_type]
    meal_target = MacroTarget(
        calories=meal_cal,
        protein_g=daily_macro["protein_g"] * meal_ratios[meal_type],
        carbs_g=daily_macro["carbs_g"] * meal_ratios[meal_type],
        fat_g=daily_macro["fat_g"] * meal_ratios[meal_type],
    )

    logger.info(f"🍽 Optimizing {meal_vn[meal_type]}: target={meal_cal:.0f} kcal")

    # Get recent dish IDs (thay vì ingredient IDs)
    recent_dish_ids = await _get_recent_dish_ids(request.session_id)

    async with AsyncSessionLocal() as db:
        try:
            # Gọi dish_optimizer thay vì meal_optimizer
            dish = await dish_optimizer.optimize_meal(
                db=db,
                target=meal_target,
                meal_type=meal_type,
                recent_dish_ids=recent_dish_ids,
            )

            if not dish:
                await websocket.send_json({
                    "type": "error",
                    "content": "Không tìm thấy món ăn phù hợp. Vui lòng thử lại."
                })
                return

            # Format output
            total_cal = dish.total_calories
            total_protein = dish.total_protein
            total_carbs = dish.total_carbs
            total_fat = dish.total_fat

            # Stream text với typing effect
            text_parts = [f"**{dish.name}** ({total_cal:.0f} kcal):\n\n"]
            for comp in dish.components:
                text_parts.append(
                    f"• **{comp.name}**: {comp.serving_grams}g "
                    f"— {comp.calories:.0f} kcal (P:{comp.protein:.0f}g, C:{comp.carbs:.0f}g, F:{comp.fat:.0f}g)\n"
                )
            text_parts.append(
                f"\n**Tổng cộng**: {total_cal:.0f} kcal | "
                f"Protein {total_protein:.0f}g | Carbs {total_carbs:.0f}g | Fat {total_fat:.0f}g"
            )

            full_text = "".join(text_parts)
            for word in full_text.split(" "):
                await websocket.send_json({"type": "token", "content": word + " "})
                await asyncio.sleep(0.01)

            # Build structured
            actions = []
            for comp in dish.components:
                actions.append({
                    "kind": "food",
                    "wger_id": 0,  # Không cần wger_id nữa
                    "name": comp.name,
                    "details": {
                        "calories": comp.energy_per_100g,
                        "protein": comp.protein / (comp.serving_grams / 100.0),
                        "carbs": comp.carbs / (comp.serving_grams / 100.0),
                        "fat": comp.fat / (comp.serving_grams / 100.0),
                        "meal_type": meal_type,
                        "dish_name": dish.name,  # Tên món
                        "serving_grams": comp.serving_grams,
                    },
                })

            structured = {
                "type": "structured",
                "text": dish.name,
                "meal_name": dish.name,
                "actions": actions,
            }

            # Suggestions
            if from_flow:
                suggestions = ["Tạo bài tập mới", "Gợi ý bữa ăn khác", "Phân tích hôm nay"]
            else:
                suggestions = ["Gợi ý bữa ăn khác", "Phân tích dinh dưỡng", "Tính calo"]

            # Done
            await websocket.send_json({
                "type": "done",
                "full_response": full_text,
                "structured": structured,
                "suggestions": suggestions,
                "options": [],
            })

            session_store.append_turn(request.session_id, role="user", content=request.message)
            session_store.append_turn(request.session_id, role="assistant", content=full_text)

            logger.info(f"✅ Optimized meal in {time.time() - t0:.2f}s")

        except Exception as e:
            logger.error(f"❌ Optimizer error: {e}", exc_info=True)
            # Fallback to LLM
            await _call_llm_fallback(websocket, request, t0, Intent.NUTRITION_REQUEST, from_flow)


async def _call_llm_fallback(websocket: WebSocket, request: ChatRequest, t0: float,
                              intent: Intent, from_flow: bool):
    """Fallback khi optimizer fail — gọi LLM như cũ."""
    logger.warning("⚠️  Falling back to LLM")
    # Copy logic từ _call_llm cũ (phần sau "# History")
    history = session_store.get_history(request.session_id, max_turns=8)
    messages = prompt_builder.build(
        user_context=request.user_context,
        rag_chunks=[],
        history=history,
        user_message=request.message,
        intent=intent,
    )

    full_response_parts: list[str] = []
    try:
        async for token in llm_service.stream_chat(messages=messages):
            full_response_parts.append(token)
            await websocket.send_json({"type": "token", "content": token})
    except Exception as e:
        logger.error("❌ LLM error: %s", e)
        await websocket.send_json(ErrorMessage(code="LLM_UNAVAILABLE", message=str(e)).model_dump())
        return

    full_response = "".join(full_response_parts)
    clean_text, structured, suggestions = response_parser.parse(full_response)

    if from_flow:
        suggestions = ["Tạo bài tập mới", "Gợi ý bữa ăn", "Phân tích hôm nay"]
    elif not suggestions:
        suggestions = intent_classifier.get_default_suggestions(intent)

    await websocket.send_json({
        "type": "done",
        "full_response": clean_text,
        "structured": structured.model_dump() if structured else None,
        "suggestions": suggestions,
        "options": [],
    })
    session_store.append_turn(request.session_id, role="user", content=request.message)
    session_store.append_turn(request.session_id, role="assistant", content=clean_text)


async def _handle_multi_meal(websocket: WebSocket, request: ChatRequest,
                             meal_types: list[str], t0: float) -> None:
    """
    Xử lý yêu cầu nhiều bữa ăn bằng Meal Optimizer.
    Mỗi bữa được tối ưu riêng, stream kết quả với separator rõ ràng.
    """
    from services.meal_optimizer import MacroTarget
    from services.tdee_calculator import calculate_bmr, calculate_tdee, get_recommended_calories
    from services.prompt_builder import _calc_macro_targets
    from services.ingredient_translator import translate_ingredient_name

    meal_vn = {
        "breakfast": "Bữa sáng", "lunch": "Bữa trưa",
        "dinner": "Bữa tối",     "snack": "Bữa phụ",
    }
    meal_ratios = {
        "breakfast": 0.30, "lunch": 0.35, "dinner": 0.25, "snack": 0.10,
    }

    # Tính macro targets
    ctx = request.user_context
    bmr = calculate_bmr(ctx.age, ctx.gender, ctx.height, ctx.weight)
    tdee = calculate_tdee(bmr, ctx.activity_level)
    daily_cal = get_recommended_calories(tdee, ctx.health_goal)
    daily_macro = _calc_macro_targets(daily_cal, ctx.health_goal, ctx.weight, ctx.height)

    all_structured = []
    final_suggestions: list[str] = []

    # Lấy recent dishes để tránh lặp
    recent_dish_ids = await _get_recent_dish_ids(request.session_id)

    async with AsyncSessionLocal() as db:
        for i, meal_type in enumerate(meal_types):
            is_last = (i == len(meal_types) - 1)
            label = meal_vn.get(meal_type, meal_type)

            # Separator
            if i > 0:
                await websocket.send_json({"type": "token", "content": f"\n\n---\n\n"})

            # Header
            await websocket.send_json({"type": "token", "content": f"**{label}**\n"})

            # Tính macro target cho bữa này
            meal_cal = daily_cal * meal_ratios[meal_type]
            meal_target = MacroTarget(
                calories=meal_cal,
                protein_g=daily_macro["protein_g"] * meal_ratios[meal_type],
                carbs_g=daily_macro["carbs_g"] * meal_ratios[meal_type],
                fat_g=daily_macro["fat_g"] * meal_ratios[meal_type],
            )

            logger.info(f"🍽 Optimizing {label}: target={meal_cal:.0f} kcal")
            t_meal = time.time()

            try:
                # Gọi dish_optimizer
                dish = await dish_optimizer.optimize_meal(
                    db=db,
                    target=meal_target,
                    meal_type=meal_type,
                    recent_dish_ids=recent_dish_ids,
                )

                if not dish:
                    await websocket.send_json({"type": "token", "content": f"\n(Không tìm thấy món phù hợp cho {label})\n"})
                    continue

                # Format kết quả
                total_cal = dish.total_calories
                total_protein = dish.total_protein
                total_carbs = dish.total_carbs
                total_fat = dish.total_fat

                # Stream text
                text_parts = [f"**{dish.name}** ({total_cal:.0f} kcal):\n\n"]
                for comp in dish.components:
                    text_parts.append(
                        f"• **{comp.name}**: {comp.serving_grams}g "
                        f"— {comp.calories:.0f} kcal (P:{comp.protein:.0f}g, C:{comp.carbs:.0f}g, F:{comp.fat:.0f}g)\n"
                    )
                text_parts.append(
                    f"\n**Tổng**: {total_cal:.0f} kcal | "
                    f"Protein {total_protein:.0f}g | Carbs {total_carbs:.0f}g | Fat {total_fat:.0f}g\n"
                )

                full_text = "".join(text_parts)
                for word in full_text.split(" "):
                    await websocket.send_json({"type": "token", "content": word + " "})
                    await asyncio.sleep(0.01)

                # Build structured data
                actions = []
                for comp in dish.components:
                    actions.append({
                        "kind": "food",
                        "wger_id": 0,
                        "name": comp.name,
                        "details": {
                            "calories": comp.energy_per_100g,
                            "protein": comp.protein / (comp.serving_grams / 100.0),
                            "carbs": comp.carbs / (comp.serving_grams / 100.0),
                            "fat": comp.fat / (comp.serving_grams / 100.0),
                            "meal_type": meal_type,
                            "dish_name": dish.name,  # Tên món
                            "serving_grams": comp.serving_grams,
                        },
                    })

                structured = {
                    "type": "structured",
                    "text": dish.name,
                    "meal_name": dish.name,
                    "actions": actions,
                }
                all_structured.append(structured)

                # Update recent_dish_ids
                recent_dish_ids.append(dish.id)

                logger.info(f"✅ {label}: {dish.name} in {time.time() - t_meal:.2f}s")

            except Exception as e:
                logger.error(f"❌ Optimizer error for {label}: {e}", exc_info=True)
                await websocket.send_json({"type": "token", "content": f"\n(Lỗi khi tối ưu {label})\n"})
                continue

    if not final_suggestions:
        final_suggestions = ["Phân tích dinh dưỡng hôm nay", "Gợi ý bài tập", "Tính calo"]

    # Done
    await websocket.send_json({
        "type": "done",
        "full_response": "",
        "structured": all_structured[0] if len(all_structured) == 1 else (all_structured or None),
        "suggestions": final_suggestions,
        "options": [],
    })

    session_store.append_turn(request.session_id, role="user", content=request.message)
    session_store.append_turn(
        request.session_id, role="assistant",
        content=f"[Đã tối ưu {len(meal_types)} bữa ăn bằng thuật toán]"
    )


async def _get_recent_ingredient_ids(session_id: str, days: int = 3) -> list[int]:
    """Lấy danh sách ingredient IDs đã dùng trong N ngày gần đây để tránh lặp."""
    # TODO: Query từ DB history
    # Tạm thời return empty để không block
    return []


async def _get_recent_dish_ids(session_id: str, days: int = 3) -> list[int]:
    """Lấy danh sách dish IDs đã dùng trong N ngày gần đây để tránh lặp."""
    # TODO: Query từ DB history
    # Tạm thời return empty để không block
    return []


async def _call_llm(websocket: WebSocket, request: ChatRequest, t0: float,
                    intent: Intent = None, from_flow: bool = False,
                    enriched_message: str = ""):
    """Gọi RAG + wger search + LLM và stream kết quả."""
    session_id = request.session_id

    if intent is None:
        intent = intent_classifier.classify(request.message)

    # ── Nutrition request → dùng optimizer thay vì LLM ──────────────────
    if intent == Intent.NUTRITION_REQUEST:
        await _handle_single_meal_optimized(websocket, request, t0, from_flow)
        return

    # History
    history = session_store.get_history(session_id, max_turns=8)
    logger.info("📚 History: %d turns", len(history))

    # RAG + wger exercise search (chạy song song)
    rag_chunks = []
    wger_exercises_text = ""

    if intent_classifier.needs_rag(intent):
        logger.info("🔍 RAG + wger search...")
        try:
            # RAG và wger search chạy song song
            if intent == Intent.EXERCISE_REQUEST:
                search_params = wger_search_service.parse_search_params(
                    message=request.message,
                    enriched_message=enriched_message or request.message,
                )
                async with AsyncSessionLocal() as db:
                    rag_task = rag_service.retrieve(query=request.message, db=db)
                    wger_task = wger_search_service.search_exercises(search_params)
                    rag_chunks, wger_exercises = await asyncio.gather(rag_task, wger_task)
                wger_exercises_text = wger_search_service.format_for_prompt(wger_exercises)
                logger.info("✅ wger exercises: %d found (%.2fs)", len(wger_exercises), time.time() - t0)
            else:
                async with AsyncSessionLocal() as db:
                    rag_chunks = await rag_service.retrieve(query=request.message, db=db)

            logger.info("✅ RAG: %d chunks (%.2fs)", len(rag_chunks), time.time() - t0)
        except Exception as e:
            logger.warning("⚠️  RAG/wger search failed: %s", e)
    else:
        logger.info("⏭️  RAG skipped")

    # Prompt
    messages = prompt_builder.build(
        user_context=request.user_context,
        rag_chunks=rag_chunks,
        history=history,
        user_message=request.message,
        intent=intent,
        wger_exercises_text=wger_exercises_text,
    )
    logger.info("📝 Prompt: %d messages", len(messages))

    # LLM stream
    logger.info("🤖 Ollama → '%s'", request.message[:40])
    t_llm = time.time()
    full_response_parts: list[str] = []
    token_count = 0

    try:
        async for token in llm_service.stream_chat(messages=messages):
            full_response_parts.append(token)
            token_count += 1
            if token_count == 1:
                logger.info("⚡ First token (%.2fs)", time.time() - t_llm)
            await websocket.send_json({"type": "token", "content": token})
    except Exception as e:
        logger.error("❌ LLM error: %s", e)
        await websocket.send_json(ErrorMessage(code="LLM_UNAVAILABLE", message=str(e)).model_dump())
        return

    full_response = "".join(full_response_parts)
    logger.info("✅ %d tokens in %.2fs", token_count, time.time() - t0)

    # Parse
    clean_text, structured, suggestions = response_parser.parse(full_response)
    
    # Nếu đến từ conversation flow, thay suggestions bằng gợi ý flow mới
    if from_flow:
        suggestions = [
            "Tạo bài tập mới",
            "Gợi ý bữa ăn",
            "Phân tích hôm nay",
        ]
    elif not suggestions:
        suggestions = intent_classifier.get_default_suggestions(intent)

    # Done
    await websocket.send_json({
        "type": "done",
        "full_response": clean_text,
        "structured": structured.model_dump() if structured else None,
        "suggestions": suggestions,
        "options": [],
    })
    session_store.append_turn(session_id, role="user", content=request.message)
    session_store.append_turn(session_id, role="assistant", content=clean_text)
