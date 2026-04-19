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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

router = APIRouter()
STREAM_TIMEOUT_SECONDS = 120


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
            await _call_llm(websocket, enriched_request, t0)
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
    await _call_llm(websocket, request, t0, intent=intent)


def _needs_exercise_info(message: str, request: ChatRequest = None) -> bool:
    """Kiểm tra xem message có đủ thông tin để tạo bài tập không."""
    import re
    text = message.lower()

    # Nếu app đã gửi dữ liệu bài tập hôm nay → đủ context, không hỏi thêm
    if request and request.user_context.today_exercises:
        return False

    # Nếu là báo cáo / phân tích hôm nay → KHÔNG cần hỏi thêm, gửi thẳng LLM
    is_report = bool(re.search(
        r'(hôm nay tôi đã|đã ăn|đã tập|phân tích|lời khuyên|nhận xét|tổng kết|báo cáo)',
        text, re.IGNORECASE
    ))
    if is_report:
        return False

    has_muscle = bool(re.search(
        r'\b(ngực|lưng|chân|vai|bụng|toàn thân|core|tay|arm|leg|back|chest|shoulder|abs)\b', text))
    has_duration = bool(re.search(r'\d+\s*(phút|giờ|min|hour)', text))
    has_equipment = bool(re.search(
        r'\b(không có dụng cụ|tạ tay|tạ đòn|gym|dây kháng lực|bodyweight|barbell|dumbbell)\b', text))

    if sum([has_muscle, has_duration, has_equipment]) >= 2:
        return False

    if len(message.split()) <= 5:
        return True

    if not has_muscle and not has_duration:
        return True

    return False


def _needs_nutrition_info(message: str, request: ChatRequest = None) -> bool:
    """Kiểm tra xem message có đủ thông tin để gợi ý bữa ăn không."""
    import re
    text = message.lower()

    # Nếu app đã gửi dữ liệu bữa ăn hôm nay → đủ context, không hỏi thêm
    if request and request.user_context.today_meals:
        return False

    # Nếu là báo cáo / phân tích → KHÔNG cần hỏi thêm
    is_report = bool(re.search(
        r'(hôm nay tôi đã|đã ăn|đã tập|phân tích|lời khuyên|nhận xét|tổng kết|báo cáo)',
        text, re.IGNORECASE
    ))
    if is_report:
        return False

    has_meal_type = bool(re.search(
        r'\b(bữa sáng|bữa trưa|bữa tối|bữa phụ|snack|breakfast|lunch|dinner)\b', text))
    has_goal = bool(re.search(
        r'\b(giảm cân|tăng cơ|duy trì|ít calo|nhiều protein|low carb|keto)\b', text))
    has_specific = bool(re.search(
        r'\b(thực đơn.*ngày|meal plan|7 ngày|cả tuần)\b', text))

    if has_meal_type or has_goal or has_specific:
        return False

    if len(message.split()) <= 4:
        return True

    return False


async def _call_llm(websocket: WebSocket, request: ChatRequest, t0: float,
                    intent: Intent = None):
    """Gọi RAG + LLM và stream kết quả."""
    session_id = request.session_id

    if intent is None:
        intent = intent_classifier.classify(request.message)

    # History
    history = session_store.get_history(session_id, max_turns=8)
    logger.info("📚 History: %d turns", len(history))

    # RAG
    rag_chunks = []
    if intent_classifier.needs_rag(intent):
        logger.info("🔍 RAG query...")
        try:
            async with AsyncSessionLocal() as db:
                rag_chunks = await rag_service.retrieve(query=request.message, db=db)
            logger.info("✅ RAG: %d chunks (%.2fs)", len(rag_chunks), time.time() - t0)
        except Exception as e:
            logger.warning("⚠️  RAG failed: %s", e)
    else:
        logger.info("⏭️  RAG skipped")

    # Prompt
    messages = prompt_builder.build(
        user_context=request.user_context,
        rag_chunks=rag_chunks,
        history=history,
        user_message=request.message,
        intent=intent,
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
    if not suggestions:
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
