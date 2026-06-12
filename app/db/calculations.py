"""CRUD для таблицы calculations: сохранение расчётов и обрезка истории."""

from __future__ import annotations

import json
from typing import Any, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import MAX_HISTORY_RECORDS
from app.db.models import Calculation


async def save_calculation(
    session: AsyncSession,
    *,
    amount: float,
    amount_mrp: float,
    company_bins: Sequence[str],
    results: list[dict[str, Any]],
) -> Calculation:
    """Сохранить расчёт и обрезать историю до MAX_HISTORY_RECORDS."""
    calc = Calculation(
        amount=amount,
        amount_mrp=amount_mrp,
        company_bins=json.dumps(list(company_bins), ensure_ascii=False),
        results=json.dumps(results, ensure_ascii=False),
        companies_count=len(results),
    )
    session.add(calc)
    await session.commit()
    await session.refresh(calc)

    await _trim_history(session)
    return calc


async def get_recent_calculations(
    session: AsyncSession, limit: int = 20
) -> Sequence[Calculation]:
    """Вернуть последние `limit` расчётов (новые сверху)."""
    result = await session.execute(
        select(Calculation).order_by(Calculation.id.desc()).limit(limit)
    )
    return result.scalars().all()


async def get_calculation(session: AsyncSession, calc_id: int) -> Calculation | None:
    """Вернуть расчёт по id или None."""
    return await session.get(Calculation, calc_id)


async def _trim_history(session: AsyncSession) -> None:
    """Удалить самые старые записи сверх лимита MAX_HISTORY_RECORDS."""
    count = await session.scalar(select(func.count()).select_from(Calculation))
    if count is None or count <= MAX_HISTORY_RECORDS:
        return

    # id записей, которые нужно оставить (самые новые).
    keep_subq = (
        select(Calculation.id)
        .order_by(Calculation.id.desc())
        .limit(MAX_HISTORY_RECORDS)
        .scalar_subquery()
    )
    await session.execute(delete(Calculation).where(Calculation.id.notin_(keep_subq)))
    await session.commit()
