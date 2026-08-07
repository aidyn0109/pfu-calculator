"""Расчёт Показателя финансовой устойчивости (ПФУ).

Только чистые функции. Никакой работы с БД. Вся бизнес-логика строго
по разделу 7 CLAUDE.md. Все константы берутся из app.config.

Промежуточные вычисления ведутся с полной точностью float; округление —
только для отображения/экспорта (helper round_half_up).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from app.config import (
    DISPLAY_DECIMALS,
    MRP,
    PAYROLL_CAP,
    PAYROLL_FACTOR,
    PAYROLL_STEP,
    PAYROLL_THRESHOLD,
    PFU_CAP_ABOVE_MAX,
    PFU_CAPS,
    REVENUE_CAP_ABOVE_MAX,
    REVENUE_CAPS,
    REVENUE_FACTOR,
    REVENUE_STEP,
    REVENUE_THRESHOLD,
    S_MRP_MIN,
    TAXES_CAP,
    TAXES_FACTOR,
    TAXES_STEP,
    TAXES_THRESHOLD,
    YEARS,
)
from app.models.company import CompanyData


class AmountValidationError(ValueError):
    """Ошибка валидации суммы S (глобальная, не по конкретной компании)."""


# --- Вспомогательные функции -------------------------------------------------
def round_half_up(value: float, decimals: int = DISPLAY_DECIMALS) -> float:
    """Стандартное математическое округление half-up до `decimals` знаков."""
    quant = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _cap_for(s_mrp: float, caps: list[tuple[int, int, float]], above_max: float) -> float:
    """Вернуть кап по диапазону S_mrp. Диапазоны проверяются по порядку.

    Границы включительны с обеих сторон; благодаря порядку проверки значение
    на стыке (например 1 600 000) попадает в нижний диапазон.
    """
    for lo, hi, cap in caps:
        if lo <= s_mrp <= hi:
            return cap
    return above_max


def _sum_metric(values: dict[int, Optional[float]]) -> float:
    """Суммировать показатель по годам, считая None (NULL) как 0."""
    return sum(v for v in values.values() if v is not None)


def validate_amount(amount: float) -> float:
    """Проверить сумму S и вернуть S_mrp. Бросает AmountValidationError.

    Шаг 0 и Шаг 1 из раздела 7.2.
    """
    if amount <= 0:
        raise AmountValidationError("Сумма должна быть больше нуля")
    s_mrp = amount / MRP
    if s_mrp < S_MRP_MIN:
        raise AmountValidationError(
            f"Сумма ниже минимального порога ({S_MRP_MIN} МРП)"
        )
    return s_mrp


# --- Основной расчёт ---------------------------------------------------------
def calculate_pfu(company: CompanyData, amount: float) -> dict[str, Any]:
    """Рассчитать ПФУ для одной компании.

    Сумма S считается уже корректной по validate_amount (вызывается отдельно
    на уровне API), но S_mrp всё равно вычисляется здесь для определения капов.

    Если у компании нет данных ни за один год — возвращается результат с полем
    `error`; остальные поля показателей отсутствуют.
    """
    s = amount
    s_mrp = validate_amount(amount)  # переиспользуем валидацию и расчёт S_mrp

    years_used = company.years_present()

    # Все 3 года NULL → компания исключается, ошибка по ней.
    if not years_used:
        return {
            "bin": company.bin,
            "name": company.name,
            "years_used": [],
            "warnings": [],
            "error": "Отсутствуют данные по компании за все годы. Расчёт невозможен.",
        }

    warnings: list[str] = []
    missing_years = [y for y in YEARS if y not in years_used]
    if missing_years:
        warnings.append(
            "Отсутствуют данные за "
            + ", ".join(str(y) for y in missing_years)
            + ". Расчёт выполнен по: "
            + ", ".join(str(y) for y in years_used)
            + "."
        )

    # --- Шаг 2: суммы по годам (NULL = 0) ------------------------------------
    revenue_sum = _sum_metric(company.revenue_by_year())
    taxes_sum = _sum_metric(company.taxes_by_year())
    payroll_sum = _sum_metric(company.payroll_by_year())

    # --- Шаг 3: показатель дохода --------------------------------------------
    revenue_percent = (revenue_sum / s) * 100
    revenue_indicator_raw = (
        (revenue_percent - REVENUE_THRESHOLD) / REVENUE_STEP
    ) * REVENUE_FACTOR
    revenue_cap = _cap_for(s_mrp, REVENUE_CAPS, REVENUE_CAP_ABOVE_MAX)
    revenue_cap_applied = revenue_indicator_raw > revenue_cap
    revenue_indicator = min(revenue_indicator_raw, revenue_cap)

    # --- Шаг 4: показатель уплаченных налогов --------------------------------
    if revenue_sum == 0:
        # Revenue_sum = 0 → Taxes_indicator = 0, предупреждение.
        warnings.append(
            "Сумма доходов равна нулю — показатель налогов принят равным 0."
        )
        taxes_percent = 0.0
        taxes_indicator_raw = 0.0
        taxes_cap_applied = False
        taxes_indicator = 0.0
    else:
        taxes_percent = (taxes_sum / revenue_sum) * 100
        taxes_indicator_raw = (
            (taxes_percent - TAXES_THRESHOLD) / TAXES_STEP
        ) * TAXES_FACTOR
        taxes_cap_applied = taxes_indicator_raw > TAXES_CAP
        taxes_indicator = min(taxes_indicator_raw, TAXES_CAP)

    # --- Шаг 5: показатель ФОТ -----------------------------------------------
    payroll_percent = (payroll_sum / s) * 100
    payroll_indicator_raw = (
        (payroll_percent - PAYROLL_THRESHOLD) / PAYROLL_STEP
    ) * PAYROLL_FACTOR
    payroll_cap_applied = payroll_indicator_raw > PAYROLL_CAP
    payroll_indicator = min(payroll_indicator_raw, PAYROLL_CAP)

    # --- Шаг 6: итоговый ПФУ -------------------------------------------------
    pfu_raw = revenue_indicator + taxes_indicator + payroll_indicator
    pfu_cap = _cap_for(s_mrp, PFU_CAPS, PFU_CAP_ABOVE_MAX)
    pfu_cap_applied = pfu_raw > pfu_cap
    pfu_final = min(pfu_raw, pfu_cap)

    return {
        "bin": company.bin,
        "name": company.name,
        "years_used": years_used,
        "warnings": warnings,
        "revenue_percent": revenue_percent,
        "revenue_indicator": revenue_indicator,
        "revenue_cap_applied": revenue_cap_applied,
        "taxes_percent": taxes_percent,
        "taxes_indicator": taxes_indicator,
        "taxes_cap_applied": taxes_cap_applied,
        "payroll_percent": payroll_percent,
        "payroll_indicator": payroll_indicator,
        "payroll_cap_applied": payroll_cap_applied,
        "pfu_raw": pfu_raw,
        "pfu_final": pfu_final,
        "pfu_cap_applied": pfu_cap_applied,
    }
