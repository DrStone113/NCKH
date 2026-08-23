from datetime import date, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
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


router = APIRouter(prefix="/plans", tags=["plans"])


@router.post("", response_model=PlanDetail)
async def create_plan(request: Request, req: CreatePlanRequest, db: AsyncSession = Depends(get_db)):
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
    planner = request.app.state.planner
    plan_id = await planner.createLongTermPlan(
        req.user_id, req.user_context.health_goal, duration_days, profile, start_date
    )

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
async def get_active_plan(user_id: str, db: AsyncSession = Depends(get_db)):
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
async def get_active_plan_detail(user_id: str, db: AsyncSession = Depends(get_db)):
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
async def update_plan_item(item_id: str, req: UpdatePlanItemRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            """
            UPDATE plan_items
            SET completed = :completed
            WHERE id = :item_id
            """
        ),
        {"item_id": item_id, "completed": req.completed},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Plan item not found")
    return {"ok": True, "item_id": item_id, "completed": req.completed}


@router.post("/checkins")
async def create_plan_checkin(req: PlanCheckinRequest, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text(
            """
            INSERT INTO plan_items (id, plan_id, day_index, plan_date, item_type, title, payload)
            VALUES (:id, :plan_id, 0, CURRENT_DATE, 'exercise', 'checkin', CAST(:payload AS jsonb))
            """
        ),
        {
            "id": str(uuid4()),
            "plan_id": req.plan_id,
            "payload": (
                '{"kind":"checkin","user_id":"%s","weight":%s,"note":%s}'
                % (
                    req.user_id,
                    "null" if req.weight is None else str(req.weight),
                    "null" if not req.note else '"' + req.note.replace('"', "'") + '"',
                )
            ),
        },
    )
    return {"ok": True, "plan_id": req.plan_id}
