"""Pydantic-схемы запросов и ответов API.

Структура CompanyResult строго соответствует разделу 8 CLAUDE.md
(её нельзя ломать — на неё завязан экспорт в Excel).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.config import (
    PAYROLL_CAP,
    PAYROLL_FACTOR,
    PAYROLL_STEP,
    PAYROLL_THRESHOLD,
    TAXES_CAP,
    TAXES_FACTOR,
    TAXES_STEP,
    TAXES_THRESHOLD,
    YEARS,
)


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
    revenue_2025: Optional[float] = None
    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None
    taxes_2025: Optional[float] = None
    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None
    payroll_2025: Optional[float] = None

    model_config = {"from_attributes": True}


class CompanyInput(BaseModel):
    """Данные для создания компании вручную (БИН строго 12 цифр)."""

    bin: str = Field(..., pattern=r"^\d{12}$")
    name: str = Field(..., min_length=1)
    revenue_2022: Optional[float] = None
    revenue_2023: Optional[float] = None
    revenue_2024: Optional[float] = None
    revenue_2025: Optional[float] = None
    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None
    taxes_2025: Optional[float] = None
    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None
    payroll_2025: Optional[float] = None


class CompanyUpdate(BaseModel):
    """Данные для обновления компании (БИН не меняется)."""

    name: str = Field(..., min_length=1)
    revenue_2022: Optional[float] = None
    revenue_2023: Optional[float] = None
    revenue_2024: Optional[float] = None
    revenue_2025: Optional[float] = None
    taxes_2022: Optional[float] = None
    taxes_2023: Optional[float] = None
    taxes_2024: Optional[float] = None
    taxes_2025: Optional[float] = None
    payroll_2022: Optional[float] = None
    payroll_2023: Optional[float] = None
    payroll_2024: Optional[float] = None
    payroll_2025: Optional[float] = None


# --- Расчёт ------------------------------------------------------------------
class CalculateRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Сумма в тенге, строго > 0")
    company_bins: list[str] = Field(..., min_length=1)
    # Годы расчёта. None или пустой список = все годы из config.YEARS
    # (обратная совместимость со старыми клиентами).
    years: Optional[list[int]] = Field(
        default=None, description="Годы расчёта; по умолчанию — все доступные"
    )

    @field_validator("years")
    @classmethod
    def _check_years(cls, value: Optional[list[int]]) -> Optional[list[int]]:
        if not value:
            return None
        unknown = sorted({y for y in value if y not in YEARS})
        if unknown:
            raise ValueError(
                "Недопустимые годы расчёта: "
                + ", ".join(str(y) for y in unknown)
                + ". Доступны: "
                + ", ".join(str(y) for y in YEARS)
                + "."
            )
        return [year for year in YEARS if year in value]


class MdeParams(BaseModel):
    """Параметры формул, которые пользователь задаёт на вкладке MDE.

    Значения по умолчанию — из config, поэтому незаполненное поле означает
    «как в обычном калькуляторе». Шаги строго > 0: они стоят в знаменателе.
    """

    # None = кап дохода определяется автоматически по диапазону S_mrp.
    revenue_cap: Optional[float] = Field(default=None, ge=0)

    taxes_threshold: float = Field(default=TAXES_THRESHOLD)
    taxes_step: float = Field(default=TAXES_STEP, gt=0)
    taxes_factor: float = Field(default=TAXES_FACTOR)
    taxes_cap: float = Field(default=TAXES_CAP, ge=0)

    payroll_threshold: float = Field(default=PAYROLL_THRESHOLD)
    payroll_step: float = Field(default=PAYROLL_STEP, gt=0)
    payroll_factor: float = Field(default=PAYROLL_FACTOR)
    payroll_cap: float = Field(default=PAYROLL_CAP, ge=0)


class CalculateMdeRequest(CalculateRequest):
    """Запрос вкладки MDE: то же, что обычный расчёт, плюс параметры формул."""

    params: MdeParams = Field(default_factory=MdeParams)


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

    # Фактически применённые капы (вкладка MDE показывает их пользователю).
    revenue_cap: Optional[float] = None
    taxes_cap: Optional[float] = None
    payroll_cap: Optional[float] = None
    pfu_cap: Optional[float] = None


class CalculateResponse(BaseModel):
    calculation_id: int
    amount: float
    amount_mrp: float
    years: list[int]  # годы, по которым выполнялся расчёт
    results: list[CompanyResult]


class CalculateMdeResponse(CalculateResponse):
    """Ответ вкладки MDE: дополнительно возвращает применённые параметры."""

    params: MdeParams


# --- История -----------------------------------------------------------------
class HistoryItem(BaseModel):
    id: int
    created_at: str
    amount: float
    amount_mrp: float
    companies_count: int
    company_bins: list[str]
    years: list[int]
    kind: str  # "pfu" или "mde" — вкладка, выполнившая расчёт
    params: Optional[MdeParams] = None  # только для расчётов MDE


# --- Импорт ------------------------------------------------------------------
class ImportResponse(BaseModel):
    imported: int
    added: int
    updated: int
    warnings: list[str]
    errors: list[str]
