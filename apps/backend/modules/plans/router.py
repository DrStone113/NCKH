import json
from datetime import date, datetime
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from models.schemas import (
    CreatePlanRequest,
    PlanCheckinRequest,
    PlanDetail,
    PlanItem,
    PlanSummary,
    UpdatePlanItemRequest,
)
from services.agent.planner import PlannerError
from services.agent.planner import PlannerAgent
from services.agent.tools import dish, tdee, workout
from services.agent.tools.plan_tools import append_plan_items, create_plan as create_plan_row
from services.auth import AuthenticatedPrincipal, require_authenticated_principal, require_owner


router = APIRouter(prefix="/plans", tags=["plans"])


_PLANNER_ERROR_MESSAGES = {
    "INPUT_UNAVAILABLE": "Cần bổ sung thông tin ước tính năng lượng trước khi tạo kế hoạch.",
    "UNSUPPORTED": "Hồ sơ hiện cần hướng dẫn chuyên môn trước khi tạo kế hoạch.",
    "INVALID_PROFILE": "Thông tin hồ sơ chưa hợp lệ để tạo kế hoạch.",
    "INVALID_DURATION": "Thời lượng kế hoạch chưa hợp lệ.",
    "INVALID_GOAL": "Mục tiêu kế hoạch chưa hợp lệ.",
}


def _planner_http_error(error: PlannerError) -> HTTPException:
    code = error.code
    is_service_error = code == "PLAN_INCOMPLETE" or code.startswith("MISSING_TOOL_")
    return HTTPException(
        status_code=503 if is_service_error else 422,
        detail={
            "code": code,
            "message": (
                "Hệ thống tạo kế hoạch đang tạm thời không khả dụng. Vui lòng thử lại sau."
                if is_service_error
                else _PLANNER_ERROR_MESSAGES.get(
                    code,
                    "Chưa thể tạo kế hoạch lúc này. Vui lòng kiểm tra hồ sơ và thử lại.",
                )
            ),
        },
    )


def _legacy_rest_planner(db: AsyncSession) -> PlannerAgent:
    """Build the private legacy REST adapter without exposing write tools to AI."""

    tools = SimpleNamespace(
        calculate_tdee=tdee.calculate_tdee,
        create_plan=partial(create_plan_row, db),
        suggest_dish=dish.suggest_dish,
        suggest_workout=workout.suggest_workout,
        append_plan_items=partial(append_plan_items, db),
    )
    return PlannerAgent(tools, db_session=db)


@router.post("", response_model=PlanDetail)
async def create_plan(
    req: CreatePlanRequest,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    require_owner(principal, req.user_id)
    duration_days = req.duration.days
    start_date = date.today()
    profile = {
        "user_id": req.user_id,
        "age": req.user_context.age,
        "gender": req.user_context.gender,
        "equation_sex": req.user_context.equation_sex,
        "nutrition_safety_profile": req.user_context.nutrition_safety_profile.model_dump(
            mode="json"
        ),
        "height_cm": req.user_context.height,
        "weight_kg": req.user_context.weight,
        "activity_level": req.user_context.activity_level,
        "health_goal": req.user_context.health_goal,
        "dietary_restrictions": [],
    }
    planner = _legacy_rest_planner(db)
    try:
        plan_id = await planner.createLongTermPlan(
            req.user_id, req.user_context.health_goal, duration_days, profile, start_date
        )
    except PlannerError as error:
        raise _planner_http_error(error) from error

    plan_row = (await db.execute(text("SELECT id, user_id, goal, start_date, end_date, duration_days, daily_kcal_target, daily_protein_target, COALESCE(nutrition_policy_version, 'LEGACY') AS nutrition_policy_version, COALESCE(nutrition_formula_ids, '[]'::jsonb) AS nutrition_formula_ids, status, created_at FROM plans WHERE id = :id"), {"id": plan_id})).mappings().first()
    item_rows = (await db.execute(text("SELECT id, plan_id, day_index, plan_date, item_type, title, payload, target_kcal, target_protein, completed FROM plan_items WHERE plan_id = :plan_id ORDER BY day_index ASC, item_type ASC"), {"plan_id": plan_id})).mappings().all()
    if not plan_row:
        raise HTTPException(status_code=500, detail="Planner did not create plan")
    items = [PlanItem(**{**dict(r), "id": str(r["id"]), "plan_id": str(r["plan_id"])}) for r in item_rows]

    return PlanDetail(
        **{**dict(plan_row), "id": str(plan_row["id"])},
        items=items,
    )


@router.get("/{user_id}/active", response_model=PlanSummary)
async def get_active_plan(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    require_owner(principal, user_id)
    from db.db_status import is_db_offline
    if is_db_offline():
        raise HTTPException(status_code=503, detail="Active plan storage unavailable")
    try:
        row = (
            await db.execute(
                text(
                    """
                    SELECT id, user_id, goal, start_date, end_date, duration_days, daily_kcal_target, daily_protein_target, COALESCE(nutrition_policy_version, 'LEGACY') AS nutrition_policy_version, COALESCE(nutrition_formula_ids, '[]'::jsonb) AS nutrition_formula_ids, status, created_at
                    FROM plans
                    WHERE user_id = :user_id AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().first()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Active plan read failed") from exc

    if not row:
        raise HTTPException(status_code=404, detail="No active plan found")

    return PlanSummary(**{**dict(row), "id": str(row["id"])})


@router.get("/{user_id}/active/detail", response_model=PlanDetail)
async def get_active_plan_detail(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    require_owner(principal, user_id)
    from db.db_status import is_db_offline
    if is_db_offline():
        raise HTTPException(status_code=503, detail="Active plan storage unavailable")
    try:
        plan_row = (
            await db.execute(
                text(
                    """
                    SELECT id, user_id, goal, start_date, end_date, duration_days, daily_kcal_target, daily_protein_target, COALESCE(nutrition_policy_version, 'LEGACY') AS nutrition_policy_version, COALESCE(nutrition_formula_ids, '[]'::jsonb) AS nutrition_formula_ids, status, created_at
                    FROM plans
                    WHERE user_id = :user_id AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().first()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Active plan read failed") from exc

    if not plan_row:
        raise HTTPException(status_code=404, detail="No active plan found")

    item_rows = (
        await db.execute(
            text(
                """
                SELECT id, plan_id, day_index, plan_date, item_type, title, payload, target_kcal, target_protein, completed
                FROM plan_items
                WHERE plan_id = :plan_id
                ORDER BY day_index ASC, item_type ASC
                """
            ),
            {"plan_id": plan_row["id"]},
        )
    ).mappings().all()

    items = [PlanItem(**{**dict(r), "id": str(r["id"]), "plan_id": str(r["plan_id"])}) for r in item_rows]
    return PlanDetail(**{**dict(plan_row), "id": str(plan_row["id"])}, items=items)


@router.patch("/items/{item_id}")
async def update_plan_item(
    item_id: str,
    req: UpdatePlanItemRequest,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    result = await db.execute(
        text(
            """
            UPDATE plan_items
            SET completed = :completed
            WHERE id = :item_id
              AND EXISTS (
                  SELECT 1 FROM plans p
                  WHERE p.id = plan_items.plan_id AND p.user_id = :owner
              )
            """
        ),
        {"item_id": item_id, "completed": req.completed, "owner": principal.user_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plan item not found")
    return {"ok": True, "item_id": item_id, "completed": req.completed}


@router.post("/checkins")
async def create_plan_checkin(
    req: PlanCheckinRequest,
    db: AsyncSession = Depends(get_db),
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
):
    require_owner(principal, req.user_id)
    result = await db.execute(
        text(
            """
            INSERT INTO plan_items (id, plan_id, day_index, plan_date, item_type, title, payload)
            SELECT :id, p.id, 0, CURRENT_DATE, 'exercise', 'checkin', CAST(:payload AS jsonb)
            FROM plans p
            WHERE p.id = :plan_id AND p.user_id = :owner
            """
        ),
        {
            "id": str(uuid4()),
            "plan_id": req.plan_id,
            "owner": principal.user_id,
            "payload": json.dumps(
                {
                    "kind": "checkin",
                    "user_id": principal.user_id,
                    "weight": req.weight,
                    "note": req.note,
                },
                ensure_ascii=False,
            ),
        },
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"ok": True, "plan_id": req.plan_id}
