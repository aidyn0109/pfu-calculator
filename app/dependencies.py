"""Зависимости FastAPI: сессия БД, доступ к кешу, проверка admin-токена."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.cache import CompanyCache, cache
from app.db.database import async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Выдать async-сессию БД на время запроса."""
    async with async_session_factory() as session:
        yield session


def get_cache() -> CompanyCache:
    """Вернуть глобальный in-memory кеш компаний."""
    return cache
