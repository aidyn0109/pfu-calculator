"""Доменная модель компании (не ORM).

CompanyData используется бизнес-логикой расчёта ПФУ. Значения по годам
хранятся как Optional[float]: None означает «данные отсутствуют» (NULL в БД),
что отличается от значения 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.config import YEARS


@dataclass(frozen=True)
class CompanyData:
    """Снимок финансовых данных компании за годы из config.YEARS."""

    bin: str
    name: str

    revenue_2022: Optional[float] = None
    revenue_2023: Optional[float] = None
    revenue_2024: Optional[float] = None

    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None

    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None

    # --- Доступ к значениям по году ------------------------------------------
    def revenue_by_year(self) -> dict[int, Optional[float]]:
        return {year: getattr(self, f"revenue_{year}") for year in YEARS}

    def taxes_by_year(self) -> dict[int, Optional[float]]:
        return {year: getattr(self, f"taxes_{year}") for year in YEARS}

    def payroll_by_year(self) -> dict[int, Optional[float]]:
        return {year: getattr(self, f"payroll_{year}") for year in YEARS}

    def years_present(self) -> list[int]:
        """Годы, по которым есть хотя бы один из показателей (revenue/taxes/payroll)."""
        revenue = self.revenue_by_year()
        taxes = self.taxes_by_year()
        payroll = self.payroll_by_year()
        return [
            year
            for year in YEARS
            if revenue[year] is not None
            or taxes[year] is not None
            or payroll[year] is not None
        ]
