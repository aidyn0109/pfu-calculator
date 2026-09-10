"""Инициализация SQLAlchemy (async) и фабрика сессий."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


# --- Настройки движка для PostgreSQL через pgbouncer (Supabase/Render) --------
# Pgbouncer в режиме transaction/statement переиспользует одно серверное
# соединение между разными клиентами. asyncpg по умолчанию именует prepared
# statements по счётчику (__asyncpg_stmt_1__, ...), поэтому новое клиентское
# соединение натыкается на имя, оставшееся от предыдущего клиента:
#   DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_1__"
#   already exists
# Отключения кеша (statement_cache_size=0) НЕДОСТАТОЧНО: имена всё равно
# нумеруются. Нужны уникальные имена — prepared_statement_name_func.
# NullPool обязателен, чтобы не копить неиспользуемые statements на сервере.
_engine_kwargs: dict[str, object] = {"echo": False, "future": True}
if "postgresql" in DATABASE_URL:
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {
        # Кеш prepared statements самого asyncpg.
        "statement_cache_size": 0,
        # Кеш prepared statements на уровне диалекта SQLAlchemy.
        "prepared_statement_cache_size": 0,
        # Уникальное имя на каждый prepared statement.
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }

# Единый async-движок и фабрика сессий на всё приложение.
engine: AsyncEngine = create_async_engine(DATABASE_URL, **_engine_kwargs)  # type: ignore[arg-type]

async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def init_db() -> None:
    """Создать таблицы при старте, если их ещё нет, и мигрировать колонки."""
    # Импортируем модели, чтобы они зарегистрировались в метаданных Base.
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await _migrate_columns()


async def _migrate_columns() -> None:
    """Добавить недостающие колонки в существующие таблицы.

    Сначала читаем фактический список колонок через inspector и добавляем
    только те, которых нет, — так не полагаемся на try/except вокруг ALTER
    (в PostgreSQL упавшая команда обрывает всю транзакцию, и последующие
    ALTER молча не выполняются). Каждый ALTER — в отдельной транзакции.
    """
    import logging

    from sqlalchemy import inspect, text

    from app.config import YEARS

    logger = logging.getLogger(__name__)

    # Ожидаемые колонки: (таблица, колонка, SQL-тип).
    expected: list[tuple[str, str, str]] = [
        ("companies", f"{prefix}_{year}", "FLOAT")
        for year in YEARS
        for prefix in ("revenue", "taxes", "payroll")
    ]
    # Годы расчёта в истории (появились вместе с выбором года на калькуляторе).
    expected.append(("calculations", "years", "TEXT"))
    # Вкладка-источник расчёта и её пользовательские параметры (вкладка MDE).
    expected.append(("calculations", "kind", "VARCHAR"))
    expected.append(("calculations", "params", "TEXT"))

    tables = {table for table, _, _ in expected}
    async with engine.connect() as conn:
        existing = {
            table: await conn.run_sync(
                lambda sync_conn, t=table: {
                    col["name"] for col in inspect(sync_conn).get_columns(t)
                }
            )
            for table in tables
        }

    for table, col, sql_type in expected:
        if col in existing[table]:
            continue
        async with engine.begin() as conn:
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}")
            )
        logger.info("Миграция: добавлена колонка %s.%s", table, col)
