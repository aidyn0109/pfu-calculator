"""CRUD для таблицы companies, включая upsert по БИН."""

from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import engine
from app.db.models import Company


def _dialect_insert():
    """Вернуть insert-конструктор под текущий диалект БД.

    И SQLite, и PostgreSQL поддерживают on_conflict_do_update с одинаковой
    сигнатурой, поэтому код upsert остаётся единым для обоих драйверов.
    """
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert

# Колонки, которые обновляются при upsert (всё кроме PK и imported_at-логики).
_UPSERT_COLUMNS = (
    "name",
    "revenue_2022",
    "revenue_2023",
    "revenue_2024",
    "revenue_2025",
    "taxes_2022",
    "taxes_2023",
    "taxes_2024",
    "taxes_2025",
    "payroll_2022",
    "payroll_2023",
    "payroll_2024",
    "payroll_2025",
)


async def get_all_companies(session: AsyncSession) -> Sequence[Company]:
    """Вернуть все компании."""
    result = await session.execute(select(Company))
    return result.scalars().all()


async def get_company(session: AsyncSession, bin_: str) -> Company | None:
    """Вернуть компанию по БИН или None."""
    return await session.get(Company, bin_)


async def create_company(session: AsyncSession, data: dict[str, object]) -> Company:
    """Создать новую компанию. Бросает ValueError, если БИН уже существует."""
    bin_ = str(data["bin"])
    existing = await session.get(Company, bin_)
    if existing is not None:
        raise ValueError(f"Компания с БИН {bin_} уже существует")

    company = Company(**data)
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def update_company(
    session: AsyncSession, bin_: str, data: dict[str, object]
) -> Company:
    """Обновить существующую компанию. Бросает ValueError, если её нет.

    БИН (первичный ключ) не меняется — обновляются только остальные поля.
    """
    company = await session.get(Company, bin_)
    if company is None:
        raise ValueError(f"Компания с БИН {bin_} не найдена")

    for column in _UPSERT_COLUMNS:
        if column in data:
            setattr(company, column, data[column])

    await session.commit()
    await session.refresh(company)
    return company


async def upsert_companies(
    session: AsyncSession, rows: Iterable[dict[str, object]]
) -> tuple[int, int]:
    """Массовый upsert по БИН (INSERT ... ON CONFLICT DO UPDATE).

    Новые компании добавляются, существующие обновляются, отсутствующие в
    Excel компании не удаляются.

    Возвращает кортеж (added, updated).
    """
    rows = list(rows)
    if not rows:
        return (0, 0)

    incoming_bins = {str(row["bin"]) for row in rows}

    existing_result = await session.execute(
        select(Company.bin).where(Company.bin.in_(incoming_bins))
    )
    existing_bins = set(existing_result.scalars().all())

    added = len(incoming_bins - existing_bins)
    updated = len(incoming_bins & existing_bins)

    stmt = _dialect_insert()(Company)
    update_set = {col: getattr(stmt.excluded, col) for col in _UPSERT_COLUMNS}
    stmt = stmt.on_conflict_do_update(index_elements=["bin"], set_=update_set)

    await session.execute(stmt, rows)
    await session.commit()

    return (added, updated)
