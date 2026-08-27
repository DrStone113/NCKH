"""Unit tests for ``services.agent.tools.plan_tools``.

Tests Requirements 3.4, 3.5, 3.10, 7.4 from the chatbot-redesign spec.

These tests exercise:

- Tool descriptor metadata (``idempotent=False``, ``side="server"``,
  ``request_id`` required by the JSON Schema).
- Validation of ``create_plan`` arguments (``duration_days`` range, positive
  targets, ISO-8601 ``start_date``) plus the ``end_date = start_date +
  duration_days - 1`` SQL parameter.
- Validation of ``append_plan_items`` — plan lookup, ``day_index`` bounds,
  ``plan_date`` invariant, and bulk-insert SQL shape.

A lightweight fake ``AsyncSession`` is used because the bare functions only
rely on ``session.execute(text_stmt, params)`` and the result of
``.first()`` for the plan lookup. This keeps the test free of Postgres while
still verifying the SQL and parameters that would be sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from models.schemas import PlanItem
from services.agent.tool_registry import ToolDescriptor, ToolRegistry
from services.agent.tools import register_server_tools
from services.agent.tools import plan_tools as pt


# --------------------------------------------------------------------------- #
# Fake AsyncSession
# --------------------------------------------------------------------------- #


@dataclass
class _FakeResult:
    row: tuple[Any, ...] | None = None

    def first(self) -> tuple[Any, ...] | None:
        return self.row


@dataclass
class _FakeAsyncSession:
    """Minimal stand-in for ``sqlalchemy.ext.asyncio.AsyncSession``.

    ``plan_row`` is returned as the first row of the next SELECT against
    ``plans``. ``executed`` records every (sql, params) pair so tests can
    assert on the SQL that would have been emitted to Postgres.
    """

    plan_row: tuple[Any, ...] | None = None
    executed: list[tuple[str, Any]] = field(default_factory=list)

    async def execute(self, statement: Any, params: Any = None):
        sql = str(statement)
        self.executed.append((sql, params))

        if "FROM plans WHERE id" in sql:
            return _FakeResult(self.plan_row)
        if "COUNT(DISTINCT day_index)" in sql:
            inserted_rows = [
                row
                for insert_sql, insert_params in self.executed
                if "INSERT INTO plan_items" in insert_sql
                for row in insert_params
            ]
            meal_rows = [
                row for row in inserted_rows if row["item_type"] == "meal"
            ]
            return _FakeResult(
                (
                    len(inserted_rows),
                    len({row["day_index"] for row in meal_rows}),
                    len(meal_rows),
                )
            )
        return _FakeResult(None)


@dataclass
class _FailingAsyncSession(_FakeAsyncSession):
    fail_on_sql: str = "INSERT"

    async def execute(self, statement: Any, params: Any = None):
        sql = str(statement)
        if self.fail_on_sql in sql:
            raise RuntimeError("database write failed")
        return await super().execute(statement, params)


# --------------------------------------------------------------------------- #
# Descriptor metadata
# --------------------------------------------------------------------------- #


def test_create_plan_descriptor_metadata():
    d = pt.CREATE_PLAN_DESCRIPTOR
    assert isinstance(d, ToolDescriptor)
    assert d.name == "create_plan"
    assert d.side == "server"
    assert d.idempotent is False
    # Module-level descriptor is unbound — the startup path supplies `fn`.
    assert d.fn is None

    schema = d.parameters_schema
    assert "request_id" in schema["required"]
    assert schema["properties"]["duration_days"]["minimum"] == 3
    assert schema["properties"]["duration_days"]["maximum"] == 120
    assert schema["properties"]["daily_kcal_target"]["exclusiveMinimum"] == 0
    assert schema["properties"]["daily_protein_target"]["exclusiveMinimum"] == 0


def test_append_plan_items_descriptor_metadata():
    d = pt.APPEND_PLAN_ITEMS_DESCRIPTOR
    assert isinstance(d, ToolDescriptor)
    assert d.name == "append_plan_items"
    assert d.side == "server"
    assert d.idempotent is False
    assert d.fn is None

    schema = d.parameters_schema
    assert "request_id" in schema["required"]
    assert "plan_id" in schema["required"]
    assert "day_index" in schema["required"]
    assert "items" in schema["required"]


def test_create_long_term_plan_descriptor_generates_every_day_in_one_call():
    descriptor = pt.CREATE_LONG_TERM_PLAN_DESCRIPTOR
    assert descriptor.name == "create_long_term_plan"
    assert descriptor.side == "server"
    assert descriptor.idempotent is False
    assert descriptor.timeout_ms == 120_000
    assert "profile" in descriptor.parameters_schema["required"]
    assert "request_id" in descriptor.parameters_schema["required"]
    assert "TRỌN GÓI" in descriptor.description


@pytest.mark.asyncio
async def test_create_long_term_plan_runs_end_to_end_with_real_catalog_tools():
    start = date(2026, 8, 14)
    session = _FakeAsyncSession(plan_row=(start, 3))
    registry = ToolRegistry()
    register_server_tools(registry, db_session=session)

    result = await pt.create_long_term_plan(
        registry,
        session,  # type: ignore[arg-type]
        user_id="user-1",
        goal="maintain",
        duration_days=3,
        start_date=start,
        profile={
            "user_id": "user-1",
            "age": 30,
            "gender": "male",
            "equation_sex": "male",
            "height_cm": 172,
            "weight_kg": 68,
            "activity_level": "moderate",
            "health_goal": "maintain",
            "dietary_restrictions": [],
        },
        request_id="e2e-plan-1",
    )

    inserts = [
        params
        for sql, params in session.executed
        if "INSERT INTO plan_items" in sql
    ]
    assert result["days_generated"] == 3
    assert result["full_weeks"] == 0
    assert result["remaining_days"] == 3
    assert result["total_weeks"] == 1
    assert len(inserts) == 3
    assert {row[0]["day_index"] for row in inserts} == {1, 2, 3}
    # Friday and Saturday are structured aerobic sessions; Sunday is rest.
    assert [len(rows) for rows in inserts] == [4, 4, 3]
    assert all(
        str(UUID(row["id"])) == row["id"]
        for rows in inserts
        for row in rows
    )


# --------------------------------------------------------------------------- #
# create_plan happy path + SQL shape
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_plan_inserts_with_correct_end_date_and_status():
    session = _FakeAsyncSession()
    plan_id = await pt.create_plan(
        session,  # type: ignore[arg-type]
        user_id="user-1",
        goal="lose_weight",
        duration_days=7,
        start_date="2025-01-01",
        daily_kcal_target=2000.0,
        daily_protein_target=120.0,
        nutrition_policy_version="nutrition-policy-v1.0.1",
        nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
        request_id="req-abc",
    )

    # A UUID-shaped string is returned.
    assert isinstance(plan_id, str)
    assert len(plan_id) >= 32

    # Exactly one INSERT was emitted.
    assert len(session.executed) == 1
    sql, params = session.executed[0]
    assert "INSERT INTO plans" in sql
    assert "'active'" in sql  # status hard-coded into the statement.

    assert params["id"] == plan_id
    assert params["user_id"] == "user-1"
    assert params["goal"] == "lose_weight"
    assert params["duration_days"] == 7
    assert params["start_date"] == date(2025, 1, 1)
    # end_date = start_date + duration_days - 1
    assert params["end_date"] == date(2025, 1, 7)
    assert params["daily_kcal"] == 2000.0
    assert params["daily_protein"] == 120.0


@pytest.mark.asyncio
async def test_create_plan_accepts_date_object_for_start_date():
    session = _FakeAsyncSession()
    await pt.create_plan(
        session,  # type: ignore[arg-type]
        user_id="u",
        goal="maintain",
        duration_days=3,
        start_date=date(2025, 3, 10),
        daily_kcal_target=1800.0,
        daily_protein_target=80.0,
        nutrition_policy_version="nutrition-policy-v1.0.1",
        nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
        request_id="r",
    )
    _, params = session.executed[0]
    assert params["start_date"] == date(2025, 3, 10)
    assert params["end_date"] == date(2025, 3, 12)


@pytest.mark.asyncio
async def test_create_plan_propagates_database_write_failure():
    session = _FailingAsyncSession(fail_on_sql="INSERT INTO plans")

    with pytest.raises(RuntimeError, match="database write failed"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="maintain",
            duration_days=7,
            start_date=date(2025, 3, 10),
            daily_kcal_target=1800.0,
            daily_protein_target=80.0,
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="r",
        )


# --------------------------------------------------------------------------- #
# create_plan validation — Requirements 3.4
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration", [2, 121, 0, -1, 3.5, True, "7"])
async def test_create_plan_rejects_invalid_duration(bad_duration):
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_DURATION"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="g",
            duration_days=bad_duration,  # type: ignore[arg-type]
            start_date="2025-01-01",
            daily_kcal_target=2000.0,
            daily_protein_target=100.0,
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="r",
        )
    # No SQL was emitted on validation failure.
    assert session.executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_kcal", [0, -1, -0.5, "1500"])
async def test_create_plan_rejects_non_positive_kcal(bad_kcal):
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_KCAL"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="g",
            duration_days=7,
            start_date="2025-01-01",
            daily_kcal_target=bad_kcal,  # type: ignore[arg-type]
            daily_protein_target=100.0,
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="r",
        )
    assert session.executed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_protein", [0, -1, "120"])
async def test_create_plan_rejects_non_positive_protein(bad_protein):
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_PROTEIN"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="g",
            duration_days=7,
            start_date="2025-01-01",
            daily_kcal_target=2000.0,
            daily_protein_target=bad_protein,  # type: ignore[arg-type]
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="r",
        )
    assert session.executed == []


@pytest.mark.asyncio
async def test_create_plan_rejects_blank_request_id():
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_REQUEST_ID"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="g",
            duration_days=7,
            start_date="2025-01-01",
            daily_kcal_target=2000.0,
            daily_protein_target=100.0,
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="",
        )


@pytest.mark.asyncio
async def test_create_plan_rejects_invalid_start_date_string():
    session = _FakeAsyncSession()
    with pytest.raises(ValueError, match="INVALID_START_DATE"):
        await pt.create_plan(
            session,  # type: ignore[arg-type]
            user_id="u",
            goal="g",
            duration_days=7,
            start_date="not-a-date",
            daily_kcal_target=2000.0,
            daily_protein_target=100.0,
            nutrition_policy_version="nutrition-policy-v1.0.1",
            nutrition_formula_ids=["RMR_MIFFLIN_ST_JEOR_V1"],
            request_id="r",
        )


# --------------------------------------------------------------------------- #
# append_plan_items happy path + SQL shape
# --------------------------------------------------------------------------- #


def _make_plan_item(
    *,
    plan_id: str,
    day_index: int,
    plan_date: date,
    item_type: str = "meal",
    title: str = "Bữa sáng phở bò",
    target_kcal: float | None = 600.0,
    target_protein: float | None = 30.0,
) -> PlanItem:
    return PlanItem(
        id=str(uuid4()),
        plan_id=plan_id,
        day_index=day_index,
        plan_date=plan_date,
        item_type=item_type,  # type: ignore[arg-type]
        title=title,
        payload={"meal_type": "breakfast", "dish_name": "Phở bò"},
        target_kcal=target_kcal,
        target_protein=target_protein,
        completed=False,
    )


@pytest.mark.asyncio
async def test_append_plan_items_bulk_inserts_with_validated_invariants():
    plan_start = date(2025, 1, 1)
    duration = 14
    plan_id = str(uuid4())

    session = _FakeAsyncSession(plan_row=(plan_start, duration))

    day_index = 5
    expected_date = plan_start + timedelta(days=day_index - 1)
    items = [
        _make_plan_item(plan_id=plan_id, day_index=day_index, plan_date=expected_date),
        _make_plan_item(
            plan_id=plan_id,
            day_index=day_index,
            plan_date=expected_date,
            item_type="exercise",
            title="HIIT 30 phút",
            target_kcal=None,
            target_protein=None,
        ),
    ]

    await pt.append_plan_items(
        session,  # type: ignore[arg-type]
        plan_id=plan_id,
        day_index=day_index,
        items=items,
        request_id="req-1",
    )

    # First call: SELECT FROM plans. Second call: bulk INSERT INTO plan_items.
    assert len(session.executed) == 2
    select_sql, select_params = session.executed[0]
    assert "FROM plans WHERE id" in select_sql
    assert select_params == {"id": plan_id}

    insert_sql, insert_params = session.executed[1]
    assert "INSERT INTO plan_items" in insert_sql
    assert "CAST(:payload AS jsonb)" in insert_sql
    assert isinstance(insert_params, list)
    assert len(insert_params) == 2
    for row in insert_params:
        assert row["plan_id"] == plan_id
        assert row["day_index"] == day_index
        assert row["plan_date"] == expected_date
        # Payload is JSON-encoded so asyncpg can cast to jsonb.
        assert isinstance(row["payload"], str)


@pytest.mark.asyncio
async def test_append_plan_items_accepts_dict_items():
    plan_start = date(2025, 1, 1)
    plan_id = str(uuid4())
    session = _FakeAsyncSession(plan_row=(plan_start, 7))

    raw_item = {
        "day_index": 1,
        "plan_date": plan_start,
        "item_type": "meal",
        "title": "Bún bò",
        "payload": {"meal_type": "lunch"},
        "target_kcal": 700.0,
        "target_protein": 35.0,
    }

    await pt.append_plan_items(
        session,  # type: ignore[arg-type]
        plan_id=plan_id,
        day_index=1,
        items=[raw_item],
        request_id="r",
    )

    _, insert_params = session.executed[-1]
    assert insert_params[0]["plan_id"] == plan_id
    assert insert_params[0]["title"] == "Bún bò"


@pytest.mark.asyncio
async def test_append_plan_items_propagates_database_write_failure():
    plan_start = date(2025, 1, 1)
    plan_id = str(uuid4())
    session = _FailingAsyncSession(
        plan_row=(plan_start, 7),
        fail_on_sql="INSERT INTO plan_items",
    )

    with pytest.raises(RuntimeError, match="database write failed"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=plan_id,
            day_index=1,
            items=[
                _make_plan_item(
                    plan_id=plan_id,
                    day_index=1,
                    plan_date=plan_start,
                )
            ],
            request_id="r",
        )


# --------------------------------------------------------------------------- #
# append_plan_items validation — Requirements 3.5
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_append_plan_items_rejects_non_uuid_plan_id():
    session = _FakeAsyncSession(plan_row=(date(2025, 1, 1), 7))

    with pytest.raises(ValueError, match="INVALID_PLAN_ID"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id="not-a-uuid",
            day_index=1,
            items=[
                _make_plan_item(
                    plan_id="ignored",
                    day_index=1,
                    plan_date=date(2025, 1, 1),
                )
            ],
            request_id="r",
        )

    assert session.executed == []


@pytest.mark.asyncio
async def test_append_plan_items_rejects_when_plan_missing():
    session = _FakeAsyncSession(plan_row=None)
    with pytest.raises(ValueError, match="PLAN_NOT_FOUND"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=str(uuid4()),
            day_index=1,
            items=[
                _make_plan_item(
                    plan_id="ignored",
                    day_index=1,
                    plan_date=date(2025, 1, 1),
                )
            ],
            request_id="r",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_day", [0, -1, 8, 100])
async def test_append_plan_items_rejects_day_index_out_of_range(bad_day):
    plan_start = date(2025, 1, 1)
    session = _FakeAsyncSession(plan_row=(plan_start, 7))
    plan_id = str(uuid4())

    # PlanItem also requires day_index >= 1, so for negatives we trip plan-tools'
    # own validation first before constructing the item.
    if bad_day >= 1:
        items = [
            _make_plan_item(
                plan_id=plan_id,
                day_index=bad_day,
                plan_date=plan_start + timedelta(days=bad_day - 1),
            )
        ]
    else:
        # Provide a syntactically valid PlanItem for the bounds check; the
        # function should reject the day_index argument itself.
        items = [
            _make_plan_item(
                plan_id=plan_id,
                day_index=1,
                plan_date=plan_start,
            )
        ]

    with pytest.raises(ValueError, match="INVALID_DAY_INDEX"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=plan_id,
            day_index=bad_day,
            items=items,
            request_id="r",
        )


@pytest.mark.asyncio
async def test_append_plan_items_rejects_plan_date_mismatch():
    plan_start = date(2025, 1, 1)
    session = _FakeAsyncSession(plan_row=(plan_start, 14))
    plan_id = str(uuid4())

    # day_index=3 ⇒ expected plan_date = 2025-01-03; we feed 2025-01-05.
    bad_item = _make_plan_item(
        plan_id=plan_id,
        day_index=3,
        plan_date=date(2025, 1, 5),
    )

    with pytest.raises(ValueError, match="PLAN_DATE_MISMATCH"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=plan_id,
            day_index=3,
            items=[bad_item],
            request_id="r",
        )


@pytest.mark.asyncio
async def test_append_plan_items_rejects_day_index_mismatch():
    plan_start = date(2025, 1, 1)
    session = _FakeAsyncSession(plan_row=(plan_start, 14))
    plan_id = str(uuid4())

    # The argument says day_index=3, but the item carries day_index=4.
    expected_date = plan_start + timedelta(days=3 - 1)
    bad_item = _make_plan_item(
        plan_id=plan_id,
        day_index=4,
        plan_date=expected_date,
    )

    with pytest.raises(ValueError, match="DAY_INDEX_MISMATCH"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=plan_id,
            day_index=3,
            items=[bad_item],
            request_id="r",
        )


@pytest.mark.asyncio
async def test_append_plan_items_rejects_empty_items():
    plan_start = date(2025, 1, 1)
    session = _FakeAsyncSession(plan_row=(plan_start, 14))
    with pytest.raises(ValueError, match="INVALID_ITEMS"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=str(uuid4()),
            day_index=1,
            items=[],
            request_id="r",
        )


@pytest.mark.asyncio
async def test_append_plan_items_rejects_blank_request_id():
    plan_start = date(2025, 1, 1)
    session = _FakeAsyncSession(plan_row=(plan_start, 14))
    plan_id = str(uuid4())
    with pytest.raises(ValueError, match="INVALID_REQUEST_ID"):
        await pt.append_plan_items(
            session,  # type: ignore[arg-type]
            plan_id=plan_id,
            day_index=1,
            items=[
                _make_plan_item(
                    plan_id=plan_id,
                    day_index=1,
                    plan_date=plan_start,
                )
            ],
            request_id="",
        )
