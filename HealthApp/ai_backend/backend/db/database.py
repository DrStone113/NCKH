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
