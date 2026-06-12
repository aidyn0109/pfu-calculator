"""In-memory кеш компаний для быстрого доступа при расчётах.

Кеш строится из БД при старте приложения и пересобирается после импорта.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import YEARS
from app.db.companies import get_all_companies
from app.db.models import Company
from app.models.company import CompanyData


def _to_domain(company: Company) -> CompanyData:
    """Преобразовать ORM-модель в доменную CompanyData."""
    kwargs: dict[str, object] = {"bin": company.bin, "name": company.name}
    for prefix in ("revenue", "taxes", "payroll"):
        for year in YEARS:
            field = f"{prefix}_{year}"
            kwargs[field] = getattr(company, field)
    return CompanyData(**kwargs)  # type: ignore[arg-type]


class CompanyCache:
    """Потокобезопасный для async-однопоточного цикла кеш компаний по БИН."""

    def __init__(self) -> None:
        self._by_bin: dict[str, CompanyData] = {}

    async def rebuild(self, session: AsyncSession) -> int:
        """Перечитать все компании из БД. Возвращает количество компаний."""
        companies = await get_all_companies(session)
        self._by_bin = {c.bin: _to_domain(c) for c in companies}
        return len(self._by_bin)

    def get(self, bin_: str) -> CompanyData | None:
        return self._by_bin.get(bin_)

    def get_many(self, bins: Iterable[str]) -> tuple[list[CompanyData], list[str]]:
        """Вернуть (найденные, ненайденные_БИН) сохраняя порядок входа."""
        found: list[CompanyData] = []
        missing: list[str] = []
        for bin_ in bins:
            company = self._by_bin.get(bin_)
            if company is None:
                missing.append(bin_)
            else:
                found.append(company)
        return found, missing

    def all(self) -> list[CompanyData]:
        return list(self._by_bin.values())

    def __len__(self) -> int:
        return len(self._by_bin)


# Единый экземпляр кеша на всё приложение.
cache = CompanyCache()
