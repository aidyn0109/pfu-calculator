"""Pydantic-схемы запросов и ответов API.

Структура CompanyResult строго соответствует разделу 8 CLAUDE.md
(её нельзя ломать — на неё завязан экспорт в Excel).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# --- Компании ----------------------------------------------------------------
class CompanyShort(BaseModel):
    bin: str
    name: str


class CompanyFull(BaseModel):
    """Полные данные компании (для админ-таблицы)."""

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

    model_config = {"from_attributes": True}


class CompanyInput(BaseModel):
    """Данные для создания компании вручную (БИН строго 12 цифр)."""

    bin: str = Field(..., pattern=r"^\d{12}$")
    name: str = Field(..., min_length=1)
    revenue_2022: Optional[float] = None
    revenue_2023: Optional[float] = None
    revenue_2024: Optional[float] = None
    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None
    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None


class CompanyUpdate(BaseModel):
    """Данные для обновления компании (БИН не меняется)."""

    name: str = Field(..., min_length=1)
    revenue_2022: Optional[float] = None
    revenue_2023: Optional[float] = None
    revenue_2024: Optional[float] = None
    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None
    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None


# --- Расчёт ------------------------------------------------------------------
class CalculateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Сумма в тенге, строго > 0")
    company_bins: list[str] = Field(..., min_length=1)


class CompanyResult(BaseModel):
    bin: str
    name: str
    years_used: list[int]
    warnings: list[str] = Field(default_factory=list)

    # Поле присутствует только если компания исключена из расчёта.
    error: Optional[str] = None

    revenue_percent: Optional[float] = None
    revenue_indicator: Optional[float] = None
    revenue_cap_applied: Optional[bool] = None

    taxes_percent: Optional[float] = None
    taxes_indicator: Optional[float] = None
    taxes_cap_applied: Optional[bool] = None

    payroll_percent: Optional[float] = None
    payroll_indicator: Optional[float] = None
    payroll_cap_applied: Optional[bool] = None

    pfu_raw: Optional[float] = None
    pfu_final: Optional[float] = None
    pfu_cap_applied: Optional[bool] = None


class CalculateResponse(BaseModel):
    calculation_id: int
    amount: float
    amount_mrp: float
    results: list[CompanyResult]


# --- История -----------------------------------------------------------------
class HistoryItem(BaseModel):
    id: int
    created_at: str
    amount: float
    amount_mrp: float
    companies_count: int
    company_bins: list[str]


# --- Импорт ------------------------------------------------------------------
class ImportResponse(BaseModel):
    imported: int
    added: int
    updated: int
    warnings: list[str]
    errors: list[str]
