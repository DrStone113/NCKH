import logging
import time
import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    pool_recycle=settings.db_pool_recycle_seconds,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Thư mục chứa các file migration (`backend/db/migrations/*.sql`)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session — Requirements: 8.1"""
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        try:
            await session.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            await session.close()
        except Exception:
            pass


class ScopedSession:
    """Session-shaped facade that runs each statement on its own connection.

    A single :class:`AsyncSession` cannot serve overlapping awaits: asyncpg
    raises ``another operation is in progress`` / ``this session is in
    'prepared' state`` and the session stays permanently broken afterwards.

    The chat stack has three sources of overlap that all shared one session:

    * ``ChatGateway`` spawns a task per incoming message, so a second message
      arriving mid-turn runs concurrently with the first.
    * ``AgentOrchestrator`` schedules the rolling-summary update as a
      background task that outlives the turn that started it.
    * Server-side tools were bound to a process-wide session at startup while
      the WebSocket used its own request-scoped one.

    The visible damage was silent: ``_load_recent_turns`` failed, chat history
    came back empty, and the model — no longer able to see what it had already
    suggested — invented dish names instead of calling ``suggest_dish``.

    This facade exposes only what the codebase actually uses (``execute``,
    ``commit``, ``rollback``), so existing call sites are untouched. Each
    ``execute`` acquires a fresh session, commits, and releases it, which means
    concurrent callers can never collide. The trade-off is that a caller cannot
    span several statements in one transaction; nothing in the chat path does,
    and the multi-statement writer (``KnowledgeIngestService``) is handed a real
    session instead.
    """

    supports_concurrent_statements = True

    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        *,
        metrics=None,
        admission_controller=None,
    ) -> None:
        self._session_factory = session_factory
        self._metrics = metrics
        self._admission_controller = admission_controller

    async def execute(self, statement, params=None):
        started = time.perf_counter()
        failed = False
        failure_text = ""
        try:
            async with self._session_factory() as session:
                result = (
                    await session.execute(statement, params)
                    if params is not None
                    else await session.execute(statement)
                )
                # Detach the rows before the connection goes back to the pool;
                # a closed session cannot stream a server-side cursor.
                try:
                    buffered = _BufferedResult(result.fetchall(), result.rowcount)
                except Exception:
                    # Non-row-returning statement (INSERT/UPDATE/DDL).
                    buffered = _BufferedResult([], getattr(result, "rowcount", -1))
                await session.commit()
                return buffered
        except Exception as exc:
            failed = True
            failure_text = str(exc)
            raise
        finally:
            if self._metrics is not None:
                self._metrics.increment("db.statements")
                self._metrics.observe(
                    "db.statement_ms", (time.perf_counter() - started) * 1000
                )
                if failed:
                    self._metrics.increment("db.statement_failures")
                with contextlib.suppress(Exception):
                    checked_out = engine.pool.checkedout()
                    capacity = engine.pool.size() + settings.db_max_overflow
                    utilization = checked_out / max(1, capacity)
                    self._metrics.gauge("db.pool_checked_out", checked_out)
                    self._metrics.gauge("db.pool_utilization", utilization)
                    if self._admission_controller is not None:
                        self._admission_controller.observe_pressure(
                            db_utilization=utilization,
                            timed_out=failed and "timeout" in failure_text.casefold(),
                        )

    async def fetch_chat_context(self, session_id: str, limit: int):
        """Fetch history, summary and owner-scoped facts in one statement."""

        result = await self.execute(
            text(
                """
                WITH recent AS (
                    SELECT id, session_id, role, content, tool_call_id,
                           tool_name, public_trace, created_at
                    FROM chat_messages
                    WHERE session_id = :sid
                    ORDER BY created_at DESC, id DESC
                    LIMIT :lim
                ), owner AS (
                    SELECT user_id FROM chat_sessions WHERE id = :sid
                )
                SELECT
                    COALESCE((
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', id, 'session_id', session_id,
                                'role', role, 'content', content,
                                'tool_call_id', tool_call_id,
                                'tool_name', tool_name,
                                'public_trace', public_trace,
                                'created_at', created_at
                            ) ORDER BY created_at ASC, id ASC
                        ) FROM recent
                    ), '[]'::jsonb) AS history,
                    COALESCE((
                        SELECT rolling_summary FROM chat_session_memory
                        WHERE session_id = :sid
                    ), '') AS rolling_summary,
                    COALESCE((
                        SELECT jsonb_agg(
                            jsonb_build_object(
                                'id', f.id, 'user_id', f.user_id,
                                'category', f.category, 'fact', f.fact,
                                'status', f.status,
                                'source_msg_id', f.source_msg_id,
                                'created_at', f.created_at
                            ) ORDER BY f.created_at ASC
                        )
                        FROM user_facts f
                        JOIN owner o ON o.user_id = f.user_id
                        WHERE f.status = 'confirmed'
                    ), '[]'::jsonb) AS pinned_facts
                """
            ),
            {"sid": session_id, "lim": max(0, int(limit))},
        )
        row = result.first()
        if row is None:
            return [], "", []
        return row[0] or [], row[1] or "", row[2] or []

    async def commit(self) -> None:
        """No-op: :meth:`execute` already commits per statement."""

    async def rollback(self) -> None:
        """No-op: each statement runs in its own committed transaction."""

    async def close(self) -> None:
        """No-op: sessions are created and released per statement."""


class _BufferedResult:
    """The subset of SQLAlchemy's ``Result`` API the codebase relies on."""

    __slots__ = ("_rows", "rowcount")

    def __init__(self, rows, rowcount) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return list(self._rows)

    def all(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        row = self.first()
        return row[0] if row is not None else None

    def scalar_one_or_none(self):
        return self.scalar()

    def scalars(self):
        return _ScalarResult([row[0] for row in self._rows if row is not None])

    def mappings(self):
        return _MappingResult([row._mapping for row in self._rows])

    def __iter__(self):
        return iter(self._rows)


class _ScalarResult:
    __slots__ = ("_values",)

    def __init__(self, values) -> None:
        self._values = values

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None

    def __iter__(self):
        return iter(self._values)


class _MappingResult:
    __slots__ = ("_rows",)

    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


async def _ensure_migrations_table(conn: AsyncConnection) -> None:
    """Tạo bảng `schema_migrations` nếu chưa có để track các migration đã apply."""
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )


async def _is_migration_applied(conn: AsyncConnection, version: str) -> bool:
    result = await conn.execute(
        text("SELECT 1 FROM schema_migrations WHERE version = :v"),
        {"v": version},
    )
    return result.first() is not None


async def _mark_migration_applied(conn: AsyncConnection, version: str) -> None:
    await conn.execute(
        text(
            """
            INSERT INTO schema_migrations (version)
            VALUES (:v)
            ON CONFLICT (version) DO NOTHING
            """
        ),
        {"v": version},
    )


async def apply_migrations(conn: AsyncConnection | None = None) -> list[str]:
    """Apply pending SQL migrations từ ``backend/db/migrations``.

    Mỗi file ``*.sql`` được track qua bảng ``schema_migrations`` (key = tên file
    không có đuôi ``.sql``). Nếu version đã được apply trước đó thì bỏ qua.

    Có thể gọi với một ``AsyncConnection`` đã có sẵn, hoặc gọi không tham số để
    hàm tự mở connection mới từ ``engine``.

    Trả về danh sách version mới được apply trong lần gọi này.

    Requirements: 7.3, 7.5
    """
    if conn is not None:
        return await _apply_migrations_with_conn(conn)
    return await _apply_migrations_managed()


def _is_autocommit_migration(sql: str) -> bool:
    return "-- migration-mode: autocommit" in sql[:256].casefold()


def _autocommit_statements(sql: str) -> list[str]:
    """Split the deliberately simple online-index migration format."""

    without_comments = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    return [item.strip() for item in without_comments.split(";") if item.strip()]


async def _apply_migrations_managed() -> list[str]:
    if not MIGRATIONS_DIR.is_dir():
        return []
    applied: list[str] = []
    async with engine.begin() as conn:
        await _ensure_migrations_table(conn)

    for sql_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = sql_path.stem
        sql = sql_path.read_text(encoding="utf-8")
        async with engine.begin() as check_conn:
            if await _is_migration_applied(check_conn, version):
                continue
        if _is_autocommit_migration(sql):
            async with engine.connect() as raw_conn:
                auto_conn = await raw_conn.execution_options(
                    isolation_level="AUTOCOMMIT"
                )
                for statement in _autocommit_statements(sql):
                    await auto_conn.execute(text(statement))
            async with engine.begin() as mark_conn:
                await _mark_migration_applied(mark_conn, version)
        else:
            async with engine.begin() as migration_conn:
                raw = await migration_conn.get_raw_connection()
                await raw.driver_connection.execute(sql)
                await _mark_migration_applied(migration_conn, version)
        applied.append(version)
        logger.info("Migration %s applied", version)
    return applied


async def _apply_migrations_with_conn(conn: AsyncConnection) -> list[str]:
    await _ensure_migrations_table(conn)

    if not MIGRATIONS_DIR.is_dir():
        logger.info("No migrations directory at %s - skipping", MIGRATIONS_DIR)
        return []

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.info("No migration files found in %s", MIGRATIONS_DIR)
        return []

    applied: list[str] = []
    for sql_path in sql_files:
        version = sql_path.stem  # ví dụ "001_chatbot_redesign"
        if await _is_migration_applied(conn, version):
            logger.debug("Migration %s already applied - skipping", version)
            continue

        sql = sql_path.read_text(encoding="utf-8")
        if _is_autocommit_migration(sql) and hasattr(conn, "get_isolation_level"):
            isolation = await conn.get_isolation_level()
            if str(isolation).upper() != "AUTOCOMMIT":
                raise RuntimeError("AUTOCOMMIT_MIGRATION_REQUIRES_MANAGED_CONNECTION")
        logger.info("Applying migration %s", version)
        # asyncpg KHÔNG cho phép nhiều statement trong một prepared statement.
        # Để gửi nguyên file (nhiều CREATE TABLE / ALTER TABLE) phải dùng raw
        # driver connection và simple query protocol (`execute`).
        raw = await conn.get_raw_connection()
        # `raw.driver_connection` là `asyncpg.Connection` thật (qua wrapper
        # AsyncAdapt_asyncpg_connection của SQLAlchemy).
        asyncpg_conn = raw.driver_connection
        await asyncpg_conn.execute(sql)
        await _mark_migration_applied(conn, version)
        applied.append(version)
        logger.info("Migration %s applied", version)

    return applied
