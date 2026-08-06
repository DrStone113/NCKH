import logging
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
        try:
            await session.commit()
        except Exception:
            pass
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

    def __init__(self, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def execute(self, statement, params=None):
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

    async with engine.begin() as new_conn:
        return await _apply_migrations_with_conn(new_conn)


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
