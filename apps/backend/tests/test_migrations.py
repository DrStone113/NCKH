"""Unit tests cho migration loader (`db.database.apply_migrations`).

Tests Requirements 7.3, 7.5.

Tests này không yêu cầu Postgres thật chạy. Thay vào đó dùng fake
``AsyncConnection`` để exercise control flow:
  - tạo bảng `schema_migrations`
  - bỏ qua các version đã apply
  - apply nguyên file SQL qua asyncpg simple-query protocol
  - mark version sau khi apply thành công
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import db.database as db_module


class _FakeResult:
    def __init__(self, has_row: bool) -> None:
        self._has_row = has_row

    def first(self) -> Any | None:
        return (1,) if self._has_row else None


class _FakeAsyncpgConn:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    async def execute(self, sql: str) -> None:  # pragma: no cover - simple stub
        self.executed_sql.append(sql)


class _FakeRawConn:
    def __init__(self, asyncpg_conn: _FakeAsyncpgConn) -> None:
        self.driver_connection = asyncpg_conn


class _FakeAsyncConnection:
    """Đủ giao diện để `apply_migrations` chạy mà không cần Postgres."""

    def __init__(self, applied_versions: set[str] | None = None) -> None:
        self._applied = set(applied_versions or set())
        self.executed_text: list[tuple[str, dict[str, Any]]] = []
        self.asyncpg_conn = _FakeAsyncpgConn()

    async def execute(self, statement: Any, params: dict[str, Any] | None = None):
        sql = str(statement)
        params = params or {}
        self.executed_text.append((sql, params))

        # Mô phỏng SELECT 1 FROM schema_migrations WHERE version = :v
        if "FROM schema_migrations" in sql and "SELECT" in sql.upper():
            return _FakeResult(params.get("v") in self._applied)

        # Mô phỏng INSERT INTO schema_migrations
        if "INSERT INTO schema_migrations" in sql:
            v = params.get("v")
            if v is not None:
                self._applied.add(v)
            return _FakeResult(False)

        # CREATE TABLE schema_migrations - no-op
        return _FakeResult(False)

    async def get_raw_connection(self) -> _FakeRawConn:
        return _FakeRawConn(self.asyncpg_conn)


@pytest.mark.asyncio
async def test_migration_file_exists():
    """Migration file 001 phải tồn tại với tên đúng quy ước (Requirements: 7.5)."""
    migrations_dir = db_module.MIGRATIONS_DIR
    assert migrations_dir.is_dir(), f"Missing migrations dir: {migrations_dir}"

    target = migrations_dir / "001_chatbot_redesign.sql"
    assert target.is_file(), f"Missing migration file: {target}"


@pytest.mark.asyncio
async def test_migration_file_contains_required_ddl():
    """Migration 001 phải chứa toàn bộ DDL theo design.md §10 (Requirements: 7.5)."""
    sql_path = db_module.MIGRATIONS_DIR / "001_chatbot_redesign.sql"
    sql = sql_path.read_text(encoding="utf-8")

    required_fragments = [
        "ADD COLUMN IF NOT EXISTS tool_call_id",
        "ADD COLUMN IF NOT EXISTS tool_name",
        "chat_messages_role_check",
        "role IN ('user', 'assistant', 'tool')",
        "CREATE TABLE IF NOT EXISTS chat_session_memory",
        "CREATE TABLE IF NOT EXISTS user_facts",
        "status IN ('pending', 'confirmed', 'rejected')",
        "CREATE TABLE IF NOT EXISTS tool_invocations",
        "tool_invocations_corr_idx",
        "ADD COLUMN IF NOT EXISTS daily_protein_target",
    ]
    missing = [f for f in required_fragments if f not in sql]
    assert not missing, f"Migration missing required fragments: {missing}"


@pytest.mark.asyncio
async def test_apply_migrations_runs_pending_versions():
    """`apply_migrations` apply file chưa từng được track (Requirements: 7.3)."""
    fake_conn = _FakeAsyncConnection(applied_versions=set())

    applied = await db_module.apply_migrations(conn=fake_conn)  # type: ignore[arg-type]

    assert "001_chatbot_redesign" in applied
    # SQL nguyên file phải được gửi qua asyncpg simple query protocol.
    assert fake_conn.asyncpg_conn.executed_sql, "Migration SQL was not executed"
    executed = fake_conn.asyncpg_conn.executed_sql[0]
    assert "chat_session_memory" in executed
    assert "tool_invocations_corr_idx" in executed


@pytest.mark.asyncio
async def test_apply_migrations_skips_already_applied():
    """Version đã track không apply lại (idempotency của migration runner).

    Đánh dấu TẤT CẢ file trong thư mục migrations là đã apply thay vì
    hardcode một version — nếu không, mỗi lần thêm migration mới test này lại
    hỏng dù runner vẫn đúng.
    """
    all_versions = {p.stem for p in db_module.MIGRATIONS_DIR.glob("*.sql")}
    fake_conn = _FakeAsyncConnection(applied_versions=all_versions)

    applied = await db_module.apply_migrations(conn=fake_conn)  # type: ignore[arg-type]

    assert applied == []
    # Không gửi SQL migration nào xuống asyncpg vì đã track trước đó.
    assert fake_conn.asyncpg_conn.executed_sql == []


@pytest.mark.asyncio
async def test_hybrid_search_migration_present_and_wellformed():
    """Migration 002 dựng hạ tầng full-text cho hybrid retrieval."""
    sql_path = db_module.MIGRATIONS_DIR / "002_hybrid_search.sql"
    assert sql_path.is_file(), f"Missing migration file: {sql_path}"

    sql = sql_path.read_text(encoding="utf-8")
    required = [
        "ADD COLUMN IF NOT EXISTS search_vector",
        "USING GIN (search_vector)",
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    ]
    missing = [fragment for fragment in required if fragment not in sql]
    assert not missing, f"Migration 002 missing fragments: {missing}"

    # Tiếng Việt không có stemmer trong Postgres; 'english' sẽ cắt sai gốc từ.
    assert "to_tsvector('simple'" in sql
    assert "to_tsvector('english'" not in sql


@pytest.mark.asyncio
async def test_chat_message_thoughts_migration_present_and_wellformed():
    """Migration 004 stores the reasoning needed to rebuild chat history UI."""
    sql_path = db_module.MIGRATIONS_DIR / "004_chat_message_thoughts.sql"
    assert sql_path.is_file(), f"Missing migration file: {sql_path}"

    sql = sql_path.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS thoughts" in sql
    assert "TEXT NOT NULL DEFAULT ''" in sql


@pytest.mark.asyncio
async def test_chat_message_structured_data_migration_present_and_wellformed():
    """Migration 005 preserves action cards for chat history rendering."""
    sql_path = db_module.MIGRATIONS_DIR / "005_chat_message_structured_data.sql"
    assert sql_path.is_file(), f"Missing migration file: {sql_path}"

    sql = sql_path.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS structured_data" in sql
    assert "JSONB" in sql


@pytest.mark.asyncio
async def test_chat_message_public_trace_migration_present_and_wellformed():
    sql_path = db_module.MIGRATIONS_DIR / "009_chat_message_public_trace.sql"
    assert sql_path.is_file(), f"Missing migration file: {sql_path}"

    sql = sql_path.read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS public_trace" in sql
    assert "JSONB" in sql


@pytest.mark.asyncio
async def test_nutrition_policy_plan_provenance_migration_present():
    sql_path = db_module.MIGRATIONS_DIR / "007_nutrition_policy_v1.sql"
    assert sql_path.is_file()
    sql = sql_path.read_text(encoding="utf-8")
    assert "nutrition_policy_version" in sql
    assert "nutrition_formula_ids" in sql
    assert "JSONB" in sql
    assert "UPDATE plans" not in sql


@pytest.mark.asyncio
async def test_plan_tool_v2_migration_is_versioned_and_separates_observations():
    sql_path = db_module.MIGRATIONS_DIR / "010_plan_tool_v2.sql"
    assert sql_path.is_file(), f"Missing migration file: {sql_path}"
    sql = sql_path.read_text(encoding="utf-8")
    required = [
        "CREATE TABLE IF NOT EXISTS plan_v2_plans",
        "CREATE TABLE IF NOT EXISTS plan_v2_revisions",
        "CREATE TABLE IF NOT EXISTS plan_v2_items",
        "CREATE TABLE IF NOT EXISTS plan_v2_write_actions",
        "UNIQUE (plan_id, revision_number)",
        "EXCLUDE USING gist",
        "lifecycle_status <> 'ACTIVE'",
        "legacy_plan_v2_classification",
    ]
    assert not [fragment for fragment in required if fragment not in sql]
    assert "INSERT INTO meals" not in sql
    assert "INSERT INTO workout_results" not in sql


@pytest.mark.asyncio
async def test_apply_migrations_handles_missing_dir(monkeypatch, tmp_path: Path):
    """Nếu thư mục migrations không tồn tại thì trả về [] thay vì raise."""
    monkeypatch.setattr(db_module, "MIGRATIONS_DIR", tmp_path / "no_such_dir")
    fake_conn = _FakeAsyncConnection()

    applied = await db_module.apply_migrations(conn=fake_conn)  # type: ignore[arg-type]

    assert applied == []
