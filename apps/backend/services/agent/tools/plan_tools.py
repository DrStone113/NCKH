"""Server-side write tools for long-term plans (``create_plan``, ``append_plan_items``).

Implements §4.6 and §5 of ``backend/.kiro/specs/chatbot-redesign/design.md``.
Validates Requirements 3.4, 3.5, 3.10, 7.4.

Both tools are write operations (``idempotent=False``) and therefore require
``request_id`` in their arguments. Idempotency replay (skipping a duplicate
``request_id``) is enforced by the dispatcher layer (task 8.3); the bare
functions in this module always perform their writes.

Module-level descriptors ``CREATE_PLAN_DESCRIPTOR`` and
``APPEND_PLAN_ITEMS_DESCRIPTOR`` are exported but NOT auto-registered. The
``register_server_tools`` startup hook (task 12.1) is responsible for binding
the bare async functions to a live ``AsyncSession`` provider before passing a
populated descriptor to ``ToolRegistry.register``.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, timedelta
from typing import Any, Iterable
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import PlanItem
from services.agent.tool_registry import ToolDescriptor

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# JSON Schemas (Ollama function calling)
# --------------------------------------------------------------------------- #

# `create_plan` parameters. Mirrors `Plan` validation rules in design.md §6.1
# and §6.3:
#   - duration_days ∈ [3, 120]
#   - daily_kcal_target > 0
#   - daily_protein_target > 0
#   - end_date = start_date + duration_days - 1 (computed by the tool)
#
# `request_id` is required because this tool is non-idempotent (Requirement
# 2.6 / 2.8).
CREATE_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {
            "type": "string",
            "minLength": 1,
            "description": "Owner of the plan.",
        },
        "goal": {
            "type": "string",
            "minLength": 1,
            "description": "Plan goal, e.g. 'lose_weight', 'maintain', 'gain_muscle'.",
        },
        "duration_days": {
            "type": "integer",
            "minimum": 3,
            "maximum": 120,
            "description": "Plan length in days; end_date = start_date + duration_days - 1.",
        },
        "start_date": {
            "type": "string",
            "format": "date",
            "description": "ISO-8601 calendar date the plan starts on.",
        },
        "daily_kcal_target": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Target kcal per day; must be strictly positive.",
        },
        "daily_protein_target": {
            "type": "number",
            "exclusiveMinimum": 0,
            "description": "Target protein (g) per day; must be strictly positive.",
        },
        "nutrition_policy_version": {
            "type": "string",
            "const": "nutrition-policy-v1.0.1",
        },
        "nutrition_formula_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "uniqueItems": True,
        },
        "request_id": {
            "type": "string",
            "minLength": 1,
            "description": "Idempotency key; required because this tool is non-idempotent.",
        },
    },
    "required": [
        "user_id",
        "goal",
        "duration_days",
        "start_date",
        "daily_kcal_target",
        "daily_protein_target",
        "nutrition_policy_version",
        "nutrition_formula_ids",
        "request_id",
    ],
    "additionalProperties": False,
}


# High-level plan generation schema. Unlike ``create_plan`` this operation
# creates the plan header and every meal/workout item in one deterministic
# server-side run, so the LLM never has to orchestrate one day per chat step.
CREATE_LONG_TERM_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "minLength": 1},
        "goal": {
            "type": "string",
            "enum": ["lose_weight", "maintain", "gain_muscle"],
        },
        "duration_days": {"type": "integer", "minimum": 3, "maximum": 120},
        "start_date": {"type": "string", "format": "date"},
        "profile": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "minLength": 1},
                "age": {"type": "integer", "minimum": 10, "maximum": 120},
                "gender": {"type": ["string", "null"]},
                "equation_sex": {
                    "type": ["string", "null"],
                    "enum": ["male", "female", None],
                },
                "nutrition_safety_profile": {
                    "type": "object",
                    "properties": {
                        field: {
                            "type": "string",
                            "enum": ["YES", "NO", "UNKNOWN", "NOT_PROVIDED"],
                        }
                        for field in (
                            "pregnancy",
                            "lactation",
                            "eating_disorder_risk_or_history",
                            "serious_renal_condition",
                            "fluid_restricted_cardiac_condition",
                            "clinically_complex_metabolic_condition",
                        )
                    },
                    "additionalProperties": False,
                },
                "height_cm": {"type": "number", "minimum": 100, "maximum": 250},
                "weight_kg": {"type": "number", "minimum": 30, "maximum": 300},
                "activity_level": {
                    "type": "string",
                    "enum": [
                        "sedentary",
                        "light",
                        "moderate",
                        "active",
                        "very_active",
                    ],
                },
                "health_goal": {
                    "type": "string",
                    "enum": ["lose_weight", "maintain", "gain_muscle"],
                },
                "dietary_restrictions": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "user_id",
                "age",
                "height_cm",
                "weight_kg",
                "activity_level",
                "health_goal",
            ],
            "additionalProperties": False,
        },
        "request_id": {"type": "string", "minLength": 1},
    },
    "required": [
        "user_id",
        "goal",
        "duration_days",
        "start_date",
        "profile",
        "request_id",
    ],
    "additionalProperties": False,
}


# `append_plan_items` parameters. Each item must point at a valid day in the
# parent plan; the function loads the plan and verifies invariants from
# design.md §6.3 before bulk-inserting into ``plan_items``.
APPEND_PLAN_ITEMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_id": {
            "type": "string",
            "minLength": 1,
            "description": "UUID of the parent plan.",
        },
        "day_index": {
            "type": "integer",
            "minimum": 1,
            "description": "Day index in the plan (1-based, ≤ plan.duration_days).",
        },
        "items": {
            "type": "array",
            "minItems": 1,
            "description": "Plan items to append for the given day.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "plan_id": {"type": "string"},
                    "day_index": {"type": "integer", "minimum": 1},
                    "plan_date": {"type": "string", "format": "date"},
                    "item_type": {
                        "type": "string",
                        "enum": ["meal", "exercise"],
                    },
                    "title": {"type": "string", "minLength": 1},
                    "payload": {"type": "object"},
                    "target_kcal": {"type": ["number", "null"]},
                    "target_protein": {"type": ["number", "null"]},
                    "completed": {"type": "boolean"},
                },
                "required": [
                    "day_index",
                    "plan_date",
                    "item_type",
                    "title",
                    "payload",
                ],
                "additionalProperties": True,
            },
        },
        "request_id": {
            "type": "string",
            "minLength": 1,
            "description": "Idempotency key; required because this tool is non-idempotent.",
        },
    },
    "required": ["plan_id", "day_index", "items", "request_id"],
    "additionalProperties": False,
}


# --------------------------------------------------------------------------- #
# Module-level ToolDescriptors (NOT auto-registered)
# --------------------------------------------------------------------------- #

CREATE_PLAN_DESCRIPTOR = ToolDescriptor(
    name="create_plan",
    description=(
        "Tool cấp thấp chỉ tạo header kế hoạch (status='active') và trả về "
        "`plan_id`, KHÔNG tạo lịch từng ngày. Không dùng trực tiếp khi người "
        "dùng yêu cầu một kế hoạch hoàn chỉnh; hãy dùng `create_long_term_plan`. "
        "Ánh xạ mục tiêu: giảm cân/giảm mỡ → goal='lose_weight'; "
        "tăng cơ/tăng cân → goal='gain_muscle'; giữ dáng/duy trì → goal='maintain'. "
        "duration_days tính bằng NGÀY, quy đổi từ tuần: N tuần → duration_days = N*7 "
        "(tối đa 120 ngày ≈ 17 tuần). "
        "Chỉ dùng cho sửa chữa/nâng cao cần tự quản lý plan_items."
    ),
    parameters_schema=CREATE_PLAN_SCHEMA,
    side="server",
    fn=None,  # Bound by register_server_tools (task 12.1) with an AsyncSession.
    idempotent=False,
)


CREATE_LONG_TERM_PLAN_DESCRIPTOR = ToolDescriptor(
    name="create_long_term_plan",
    description=(
        "Tạo TRỌN GÓI kế hoạch nhiều ngày trong một lần: tự tính mục tiêu, tạo "
        "header và điền đủ thực đơn + bài tập cho mọi ngày. BẮT BUỘC dùng tool "
        "này khi người dùng yêu cầu tạo/làm trọn kế hoạch dài hạn; không gọi "
        "create_plan, suggest_dish, suggest_workout hay append_plan_items thủ "
        "công theo từng ngày và không hỏi xác nhận lại khi hồ sơ đã đủ. Quy đổi "
        "N tuần thành duration_days=N*7. Lộ trình được chia thành block tuần 7 "
        "ngày theo thứ trong tuần; ví dụ 60 ngày = 8 tuần đủ + 4 ngày của tuần "
        "9, có phân kỳ cường độ và ngày nghỉ/phục hồi. Ánh xạ giảm cân/giảm mỡ → "
        "goal='lose_weight'; tăng cơ/tăng cân → goal='gain_muscle'; giữ dáng → "
        "goal='maintain'."
    ),
    parameters_schema=CREATE_LONG_TERM_PLAN_SCHEMA,
    side="server",
    fn=None,
    idempotent=False,
    timeout_ms=120_000,
)


APPEND_PLAN_ITEMS_DESCRIPTOR = ToolDescriptor(
    name="append_plan_items",
    description=(
        "Bulk insert các plan_items cho một (plan_id, day_index). "
        "Verify mọi item có plan_date == plan.start_date + (day_index - 1) "
        "và day_index ∈ [1, plan.duration_days]."
    ),
    parameters_schema=APPEND_PLAN_ITEMS_SCHEMA,
    side="server",
    fn=None,  # Bound by register_server_tools (task 12.1) with an AsyncSession.
    idempotent=False,
)


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _coerce_date(value: Any, *, field: str) -> date:
    """Coerce ``value`` to a :class:`datetime.date` or raise ``ValueError``.

    Accepts either an ISO-8601 string (``YYYY-MM-DD``) or a ``date`` instance.
    """
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:  # pragma: no cover - error path
            raise ValueError(f"INVALID_{field.upper()}") from exc
    raise ValueError(f"INVALID_{field.upper()}")


def _validate_duration_days(duration_days: Any) -> int:
    # ``bool`` is a subclass of ``int`` in Python; reject explicitly so callers
    # cannot smuggle ``True``/``False`` into a "valid" integer slot.
    if isinstance(duration_days, bool) or not isinstance(duration_days, int):
        raise ValueError("INVALID_DURATION")
    if not (3 <= duration_days <= 120):
        raise ValueError("INVALID_DURATION")
    return duration_days


def _validate_positive(value: Any, *, code: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(code)
    value = float(value)
    if value <= 0:
        raise ValueError(code)
    return value


# --------------------------------------------------------------------------- #
# Bare async implementations
# --------------------------------------------------------------------------- #


async def create_plan(
    session: AsyncSession,
    *,
    user_id: str,
    goal: str,
    duration_days: int,
    start_date: date | str,
    daily_kcal_target: float,
    daily_protein_target: float,
    nutrition_policy_version: str,
    nutrition_formula_ids: list[str],
    request_id: str,
) -> str:
    """Insert a new ``plans`` row with ``status='active'`` and return its id.

    Parameters
    ----------
    session:
        Active SQLAlchemy ``AsyncSession``. The caller is responsible for
        committing (or rolling back) the surrounding transaction.
    user_id, goal:
        Owner and goal label (e.g. ``"lose_weight"``).
    duration_days:
        Must be an integer in ``[3, 120]``. Bool is rejected.
    start_date:
        ``date`` instance or ISO-8601 string.
    daily_kcal_target, daily_protein_target:
        Strictly positive numeric targets.
    request_id:
        Idempotency key. Validated to be a non-empty string. Idempotency
        replay (skipping duplicates) is enforced one layer up by the
        dispatcher (task 8.3); this function always inserts.

    Raises
    ------
    ValueError
        With one of: ``"INVALID_USER_ID"``, ``"INVALID_GOAL"``,
        ``"INVALID_DURATION"``, ``"INVALID_START_DATE"``, ``"INVALID_KCAL"``,
        ``"INVALID_PROTEIN"``, ``"INVALID_REQUEST_ID"``.

    Returns
    -------
    str
        UUID of the freshly created plan, suitable as a tool result.
    """
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("INVALID_USER_ID")
    if not isinstance(goal, str) or not goal:
        raise ValueError("INVALID_GOAL")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("INVALID_REQUEST_ID")

    duration = _validate_duration_days(duration_days)
    kcal = _validate_positive(daily_kcal_target, code="INVALID_KCAL")
    protein = _validate_positive(daily_protein_target, code="INVALID_PROTEIN")
    if nutrition_policy_version != "nutrition-policy-v1.0.1":
        raise ValueError("INVALID_NUTRITION_POLICY_VERSION")
    if (
        not isinstance(nutrition_formula_ids, list)
        or not nutrition_formula_ids
        or any(not isinstance(item, str) or not item for item in nutrition_formula_ids)
    ):
        raise ValueError("INVALID_NUTRITION_FORMULA_IDS")
    start = _coerce_date(start_date, field="start_date")

    end = start + timedelta(days=duration - 1)

    plan_id = str(uuid4())
    await session.execute(
        text(
            """
            INSERT INTO plans (
                id, user_id, goal,
                start_date, end_date, duration_days,
                daily_kcal_target, daily_protein_target,
                nutrition_policy_version, nutrition_formula_ids,
                status
            )
            VALUES (
                :id, :user_id, :goal,
                :start_date, :end_date, :duration_days,
                :daily_kcal, :daily_protein,
                :nutrition_policy_version, CAST(:nutrition_formula_ids AS jsonb),
                'active'
            )
            """
        ),
        {
            "id": plan_id,
            "user_id": user_id,
            "goal": goal,
            "start_date": start,
            "end_date": end,
            "duration_days": duration,
            "daily_kcal": kcal,
            "daily_protein": protein,
            "nutrition_policy_version": nutrition_policy_version,
            "nutrition_formula_ids": json.dumps(nutrition_formula_ids),
        },
    )

    logger.info(
        "create_plan inserted plan id=%s user=%s duration=%d kcal=%.1f protein=%.1f",
        plan_id,
        user_id,
        duration,
        kcal,
        protein,
    )
    return plan_id


async def create_long_term_plan(
    registry: Any,
    session: AsyncSession,
    *,
    user_id: str,
    goal: str,
    duration_days: int,
    start_date: date | str,
    profile: dict[str, Any],
    request_id: str,
) -> dict[str, Any]:
    """Generate a complete plan in one high-level tool invocation."""
    from services.agent.planner import PlannerAgent

    start = _coerce_date(start_date, field="start_date")
    _ = request_id  # Idempotency is enforced by ToolDispatcher.
    plan_id = await PlannerAgent(registry, db_session=session).createLongTermPlan(
        user_id=user_id,
        goal=goal,
        duration_days=duration_days,
        profile=profile,
        start_date=start,
    )

    return {
        "plan_id": str(plan_id),
        "duration_days": duration_days,
        "days_generated": duration_days,
        "full_weeks": duration_days // 7,
        "remaining_days": duration_days % 7,
        "total_weeks": math.ceil(duration_days / 7),
        "start_date": start.isoformat(),
        "status": "active",
    }


def _coerce_plan_item(raw: Any) -> PlanItem:
    """Coerce ``raw`` to a :class:`PlanItem`. Accepts dict or PlanItem."""
    if isinstance(raw, PlanItem):
        return raw
    if isinstance(raw, dict):
        # Fill missing surrogate fields so PlanItem validation succeeds. The
        # tool is the source of truth for ``id`` / ``plan_id`` since callers
        # may not know the just-created plan_id ahead of time.
        data = dict(raw)
        data.setdefault("id", str(uuid4()))
        data.setdefault("plan_id", "")
        data.setdefault("completed", False)
        return PlanItem.model_validate(data)
    raise ValueError("INVALID_ITEMS")


async def append_plan_items(
    session: AsyncSession,
    *,
    plan_id: str,
    day_index: int,
    items: Iterable[PlanItem | dict[str, Any]],
    request_id: str,
) -> None:
    """Bulk-insert ``items`` into ``plan_items`` for ``(plan_id, day_index)``.

    Verifies the invariants from design.md §6.3:

    - ``day_index ∈ [1, plan.duration_days]``
    - ``item.plan_date == plan.start_date + (day_index - 1)`` for every item
    - ``item.day_index == day_index`` for every item

    Parameters
    ----------
    session:
        Active SQLAlchemy ``AsyncSession``.
    plan_id:
        UUID of an existing row in ``plans``.
    day_index:
        Day to which ``items`` belong (1-based).
    items:
        ``PlanItem`` instances or dicts shaped like one. Mixed input is
        accepted; dicts are coerced via :class:`PlanItem.model_validate`.
    request_id:
        Idempotency key. Validated to be a non-empty string.

    Raises
    ------
    ValueError
        With one of: ``"INVALID_PLAN_ID"``, ``"INVALID_REQUEST_ID"``,
        ``"PLAN_NOT_FOUND"``, ``"INVALID_DAY_INDEX"``, ``"INVALID_ITEMS"``,
        ``"PLAN_DATE_MISMATCH"``, ``"DAY_INDEX_MISMATCH"``.
    """
    if not isinstance(plan_id, str) or not plan_id:
        raise ValueError("INVALID_PLAN_ID")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("INVALID_REQUEST_ID")
    if isinstance(day_index, bool) or not isinstance(day_index, int):
        raise ValueError("INVALID_DAY_INDEX")

    import uuid

    try:
        uuid.UUID(plan_id)
    except (ValueError, TypeError):
        raise ValueError("INVALID_PLAN_ID") from None

    plan_row = (
        await session.execute(
            text("SELECT start_date, duration_days FROM plans WHERE id = :id"),
            {"id": plan_id},
        )
    ).first()
    if plan_row is None:
        raise ValueError("PLAN_NOT_FOUND")
    plan_start: date = plan_row[0]
    plan_duration: int = int(plan_row[1])

    if not (1 <= day_index <= plan_duration):
        raise ValueError("INVALID_DAY_INDEX")

    expected_plan_date = plan_start + timedelta(days=day_index - 1)

    materialised: list[PlanItem] = [_coerce_plan_item(it) for it in items]
    if not materialised:
        raise ValueError("INVALID_ITEMS")

    for item in materialised:
        if item.plan_date != expected_plan_date:
            raise ValueError("PLAN_DATE_MISMATCH")
        if item.day_index != day_index:
            raise ValueError("DAY_INDEX_MISMATCH")

    # Bulk insert. SQLAlchemy ``executemany`` over ``text`` with a list of
    # parameter dicts emits one INSERT per row but in a single round-trip
    # batch on asyncpg, which is the standard pattern for parameterised bulk
    # writes against the asyncpg driver.
    insert_sql = text(
        """
        INSERT INTO plan_items (
            id, plan_id, day_index, plan_date,
            item_type, title, payload,
            target_kcal, target_protein, completed
        )
        VALUES (
            :id, :plan_id, :day_index, :plan_date,
            :item_type, :title, CAST(:payload AS jsonb),
            :target_kcal, :target_protein, :completed
        )
        """
    )

    rows = [
        {
            "id": item.id or str(uuid4()),
            "plan_id": plan_id,
            "day_index": item.day_index,
            "plan_date": item.plan_date,
            "item_type": item.item_type,
            "title": item.title,
            "payload": json.dumps(item.payload),
            "target_kcal": item.target_kcal,
            "target_protein": item.target_protein,
            "completed": bool(item.completed),
        }
        for item in materialised
    ]

    await session.execute(insert_sql, rows)

    logger.info(
        "append_plan_items inserted %d items plan_id=%s day_index=%d",
        len(rows),
        plan_id,
        day_index,
    )


__all__ = [
    "APPEND_PLAN_ITEMS_DESCRIPTOR",
    "APPEND_PLAN_ITEMS_SCHEMA",
    "CREATE_LONG_TERM_PLAN_DESCRIPTOR",
    "CREATE_LONG_TERM_PLAN_SCHEMA",
    "CREATE_PLAN_DESCRIPTOR",
    "CREATE_PLAN_SCHEMA",
    "append_plan_items",
    "create_long_term_plan",
    "create_plan",
]
