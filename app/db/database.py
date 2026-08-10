"""Инициализация SQLAlchemy (async) и фабрика сессий."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


# Для PostgreSQL через pgbouncer (Supabase) отключаем кеш prepared statements.
# Добавляем statement_cache_size=0 в URL, чтобы asyncpg гарантированно получил параметр.
_final_url = DATABASE_URL
if "postgresql" in _final_url and "statement_cache_size" not in _final_url:
    sep = "&" if "?" in _final_url else "?"
    _final_url = f"{_final_url}{sep}statement_cache_size=0"

# Единый async-движок и фабрика сессий на всё приложение.
engine: AsyncEngine = create_async_engine(
    _final_url, echo=False, future=True
)

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
        await _migrate_columns(conn)


async def _migrate_columns(conn) -> None:
    """Добавить недостающие колонки в существующую таблицу companies.

    Безопасная миграция: ALTER TABLE ADD COLUMN IF NOT EXISTS (или обёртка
    try/except для диалектов, которые этого не поддерживают). Позволяет
    обновить БД на новую схему без потери данных.
    """
    import logging

    from sqlalchemy import text

    from app.config import YEARS

    logger = logging.getLogger(__name__)
    new_years = [y for y in YEARS if y >= 2025]  # колонки, которых могло не быть

    if not new_years:
        return

    for year in new_years:
        for prefix in ("revenue", "taxes", "payroll"):
            col = f"{prefix}_{year}"
            try:
                await conn.execute(
                    text(f"ALTER TABLE companies ADD COLUMN {col} FLOAT")
                )
                logger.info("Миграция: добавлена колонка %s", col)
            except Exception:
                # Колонка уже существует (или диалект не поддерживает IF NOT EXISTS).
                pass
