from fastapi import APIRouter, Request, Query, Body, Depends
from typing import Optional

from models.schemas import (
    ProactiveNudgeResponse,
    CheckinRespondRequest,
    CheckinRespondResult,
    CheckinSettings,
    UserContext,
)
from services.auth import AuthenticatedPrincipal, require_authenticated_principal, require_owner

router = APIRouter(prefix="/checkin", tags=["checkin"])


def _get_service(request: Request):
    service = getattr(request.app.state, "proactive_service", None)
    if service is None:
        # Fallback khởi tạo đơn giản nếu chưa có service.
        # Không có llm_client nên nudge sẽ dùng template — vẫn chạy được.
        from services.proactive_service import ProactiveService

        service = ProactiveService()
    return service


@router.get("/active", response_model=Optional[ProactiveNudgeResponse])
async def get_active_checkin(
    request: Request,
    user_id: str | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    """Lấy check-in chủ động — bản không kèm ngữ cảnh.

    Giữ lại cho tương thích ngược. Không có dữ liệu hôm nay của người dùng nên
    nudge chỉ dựa vào khung giờ. Client nên gọi ``POST /checkin/active`` để
    nhận lời nhắc cá nhân hóa.
    """
    if user_id is not None:
        require_owner(principal, user_id)
    service = _get_service(request)
    return await service.generate_active_nudge(user_id=principal.user_id)


@router.post("/active", response_model=Optional[ProactiveNudgeResponse])
async def get_active_checkin_with_context(
    request: Request,
    user_id: str | None = Query(None),
    user_context: Optional[UserContext] = Body(None),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    """Lấy check-in chủ động dựa trên dữ liệu thật của hôm nay.

    Flutter đã có sẵn số bữa đã ghi, calo nạp vào/đốt ra và số buổi tập —
    truyền vào đây để lời nhắc bám theo tình hình thực tế thay vì lặp lại một
    câu cố định theo giờ. Trả về ``null`` khi không có gì đáng nhắc: im lặng
    đúng lúc cũng là một phần của việc nhắc đúng.
    """
    if user_id is not None:
        require_owner(principal, user_id)
    service = _get_service(request)
    return await service.generate_active_nudge(
        user_id=principal.user_id, user_context=user_context
    )


@router.post("/respond", response_model=CheckinRespondResult)
async def respond_to_checkin(
    request: Request,
    body: CheckinRespondRequest = Body(...),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    """Tiếp nhận phản hồi check-in từ người dùng (nút chọn nhanh hoặc tin nhắn tự do)."""
    proactive_service = getattr(request.app.state, "proactive_service", None)
    if not proactive_service:
        from services.proactive_service import ProactiveService
        proactive_service = ProactiveService()

    if body.user_id != "default_user":
        require_owner(principal, body.user_id)
    body = body.model_copy(update={"user_id": principal.user_id})
    result = await proactive_service.process_response(body)
    return result


@router.get("/settings", response_model=CheckinSettings)
async def get_checkin_settings(
    request: Request,
    user_id: str | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    """Đọc cấu hình bật/tắt check-in chủ động của người dùng."""
    proactive_service = getattr(request.app.state, "proactive_service", None)
    if not proactive_service:
        from services.proactive_service import ProactiveService
        proactive_service = ProactiveService()

    if user_id is not None:
        require_owner(principal, user_id)
    return proactive_service.get_user_settings(principal.user_id)


@router.put("/settings", response_model=CheckinSettings)
async def update_checkin_settings(
    request: Request,
    body: CheckinSettings = Body(...),
    user_id: str | None = Query(None),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    """Cập nhật cấu hình bật/tắt check-in chủ động của người dùng."""
    proactive_service = getattr(request.app.state, "proactive_service", None)
    if not proactive_service:
        from services.proactive_service import ProactiveService
        proactive_service = ProactiveService()

    if user_id is not None:
        require_owner(principal, user_id)
    return proactive_service.update_user_settings(principal.user_id, body)
