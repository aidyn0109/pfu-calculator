"""Расчёт Показателя финансовой устойчивости (ПФУ).

Только чистые функции. Никакой работы с БД. Вся бизнес-логика строго
по разделу 7 CLAUDE.md. Все константы по умолчанию берутся из app.config.

Один и тот же расчёт обслуживает две вкладки (раздел 7.4 CLAUDE.md):
  * «Калькулятор» — все параметры формул из config (params не передаётся);
  * «Калькулятор MDE» — часть параметров задаёт пользователь (CalcParams).
Второго алгоритма не существует: MDE отличается только значениями
параметров, а не формулами.

Промежуточные вычисления ведутся с полной точностью float; округление —
только для отображения/экспорта (helper round_half_up).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional, Sequence

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
    REVENUE_CAP_BELOW_MIN,
    REVENUE_CAPS,
    REVENUE_FACTOR,
    REVENUE_STEP,
    REVENUE_THRESHOLD,
    TAXES_CAP,
    TAXES_FACTOR,
    TAXES_STEP,
    TAXES_THRESHOLD,
    YEARS,
)
from app.models.company import CompanyData


class AmountValidationError(ValueError):
    """Ошибка валидации суммы S (глобальная, не по конкретной компании)."""


class YearsValidationError(ValueError):
    """Ошибка валидации выбранных годов расчёта."""


class ParamsValidationError(ValueError):
    """Ошибка валидации пользовательских параметров расчёта (вкладка MDE)."""


# --- Параметры расчёта -------------------------------------------------------
@dataclass(frozen=True)
class CalcParams:
    """Параметры формул. По умолчанию — значения из config (обычный ПФУ).

    Вкладка «Калькулятор MDE» подменяет часть из них значениями, которые ввёл
    пользователь. Что можно переопределить (раздел 7.4 CLAUDE.md):

    * `revenue_cap` — кап показателя дохода. None = авто по диапазону S_mrp,
      как в обычном калькуляторе; число = жёстко заданное пользователем
      значение (диапазоны S_mrp тогда не участвуют).
    * `taxes_threshold` / `taxes_step` / `taxes_factor` — числа 3 / 0.1 / 0.5
      в формуле Taxes_indicator; `taxes_cap` — предел 65%.
    * `payroll_threshold` / `payroll_step` / `payroll_factor` — числа
      6.6 / 0.1 / 0.1 в формуле Payroll_indicator; `payroll_cap` — предел 100%.

    Формулы показателя дохода (50 / 0.1 / 0.05) и капы итогового ПФУ
    пользователю не отдаются — они остаются из config.
    """

    revenue_cap: Optional[float] = None
    taxes_threshold: float = TAXES_THRESHOLD
    taxes_step: float = TAXES_STEP
    taxes_factor: float = TAXES_FACTOR
    taxes_cap: float = TAXES_CAP
    payroll_threshold: float = PAYROLL_THRESHOLD
    payroll_step: float = PAYROLL_STEP
    payroll_factor: float = PAYROLL_FACTOR
    payroll_cap: float = PAYROLL_CAP

    def __post_init__(self) -> None:
        # Шаг стоит в знаменателе — ноль обрушил бы расчёт.
        if self.taxes_step == 0:
            raise ParamsValidationError("Шаг в формуле налогов не может быть нулём")
        if self.payroll_step == 0:
            raise ParamsValidationError("Шаг в формуле ФОТ не может быть нулём")


# Параметры обычного калькулятора: всё из config.
DEFAULT_PARAMS = CalcParams()


# --- Вспомогательные функции -------------------------------------------------
def round_half_up(value: float, decimals: int = DISPLAY_DECIMALS) -> float:
    """Стандартное математическое округление half-up до `decimals` знаков."""
    quant = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _cap_for(
    s_mrp: float,
    caps: list[tuple[int, int, float]],
    above_max: float,
    below_min: Optional[float] = None,
) -> float:
    """Вернуть кап по диапазону S_mrp. Диапазоны проверяются по порядку.

    Границы включительны с обеих сторон; благодаря порядку проверки значение
    на стыке (например 1 600 000) попадает в нижний диапазон.

    Суммы ниже нижней границы первого диапазона (800 000 МРП) не отклоняются:
    им назначается `below_min`, а если он не задан — кап первого диапазона.
    """
    for lo, hi, cap in caps:
        if lo <= s_mrp <= hi:
            return cap
    if caps and s_mrp < caps[0][0]:
        return caps[0][2] if below_min is None else below_min
    return above_max


def _sum_metric(values: dict[int, Optional[float]], years: Sequence[int]) -> float:
    """Суммировать показатель по выбранным годам, считая None (NULL) как 0."""
    return sum(v for year, v in values.items() if year in years and v is not None)


def normalize_years(years: Optional[Sequence[int]]) -> list[int]:
    """Проверить и упорядочить выбранные годы расчёта.

    None или пустой список означают «все годы из config.YEARS». Дубликаты
    убираются, порядок — как в config.YEARS. Бросает YearsValidationError,
    если передан год, по которому система не хранит данные.
    """
    if not years:
        return list(YEARS)

    unknown = sorted({y for y in years if y not in YEARS})
    if unknown:
        raise YearsValidationError(
            "Недопустимые годы расчёта: "
            + ", ".join(str(y) for y in unknown)
            + ". Доступны: "
            + ", ".join(str(y) for y in YEARS)
            + "."
        )
    return [year for year in YEARS if year in years]


def validate_amount(amount: float) -> float:
    """Проверить сумму S и вернуть S_mrp. Бросает AmountValidationError.

    Шаг 0 и Шаг 1 из раздела 7.2. Единственное ограничение — сумма строго
    больше нуля. Нижний порог в 800 000 МРП снят: встречаются реальные суммы
    ниже него, и расчёт по ним должен выполняться (капы берутся с нижнего
    уровня — см. _cap_for).
    """
    if amount <= 0:
        raise AmountValidationError("Сумма должна быть больше нуля")
    return amount / MRP


# --- Основной расчёт ---------------------------------------------------------
def calculate_pfu(
    company: CompanyData,
    amount: float,
    years: Optional[Sequence[int]] = None,
    params: Optional[CalcParams] = None,
) -> dict[str, Any]:
    """Рассчитать ПФУ для одной компании по выбранным годам.

    Сумма S считается уже корректной по validate_amount (вызывается отдельно
    на уровне API), но S_mrp всё равно вычисляется здесь для определения капов.

    `years` — годы, выбранные пользователем; None означает все годы из
    config.YEARS. Показатели суммируются только по этим годам.

    `params` — параметры формул. None означает значения из config (обычный
    калькулятор); вкладка MDE передаёт CalcParams с пользовательскими числами.

    Если у компании нет данных ни за один выбранный год — возвращается
    результат с полем `error`; остальные поля показателей отсутствуют.
    """
    p = params if params is not None else DEFAULT_PARAMS
    s = amount
    s_mrp = validate_amount(amount)  # переиспользуем валидацию и расчёт S_mrp
    selected_years = normalize_years(years)

    years_used = company.years_present(selected_years)

    # Данных нет ни за один выбранный год → компания исключается, ошибка по ней.
    if not years_used:
        return {
            "bin": company.bin,
            "name": company.name,
            "years_used": [],
            "warnings": [],
            "error": (
                "Отсутствуют данные по компании за выбранные годы ("
                + ", ".join(str(y) for y in selected_years)
                + "). Расчёт невозможен."
            ),
        }

    warnings: list[str] = []
    missing_years = [y for y in selected_years if y not in years_used]
    if missing_years:
        warnings.append(
            "Отсутствуют данные за "
            + ", ".join(str(y) for y in missing_years)
            + ". Расчёт выполнен по: "
            + ", ".join(str(y) for y in years_used)
            + "."
        )

    # --- Шаг 2: суммы по выбранным годам (NULL = 0) --------------------------
    revenue_sum = _sum_metric(company.revenue_by_year(), selected_years)
    taxes_sum = _sum_metric(company.taxes_by_year(), selected_years)
    payroll_sum = _sum_metric(company.payroll_by_year(), selected_years)

    # --- Шаг 3: показатель дохода --------------------------------------------
    # Формула дохода не настраивается; настраивается только её кап.
    revenue_percent = (revenue_sum / s) * 100
    revenue_indicator_raw = (
        (revenue_percent - REVENUE_THRESHOLD) / REVENUE_STEP
    ) * REVENUE_FACTOR
    revenue_cap = (
        _cap_for(s_mrp, REVENUE_CAPS, REVENUE_CAP_ABOVE_MAX, REVENUE_CAP_BELOW_MIN)
        if p.revenue_cap is None
        else p.revenue_cap
    )
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
            (taxes_percent - p.taxes_threshold) / p.taxes_step
        ) * p.taxes_factor
        taxes_cap_applied = taxes_indicator_raw > p.taxes_cap
        taxes_indicator = min(taxes_indicator_raw, p.taxes_cap)

    # --- Шаг 5: показатель ФОТ -----------------------------------------------
    # Знаменатель — Revenue_sum, а не S: показатель меряет долю дохода,
    # уходящую на оплату труда. Отсюда тот же случай Revenue_sum = 0, что и
    # у налогов, — показатель принимается равным 0 с предупреждением.
    if revenue_sum == 0:
        warnings.append("Сумма доходов равна нулю — показатель ФОТ принят равным 0.")
        payroll_percent = 0.0
        payroll_indicator_raw = 0.0
        payroll_cap_applied = False
        payroll_indicator = 0.0
    else:
        payroll_percent = (payroll_sum / revenue_sum) * 100
        payroll_indicator_raw = (
            (payroll_percent - p.payroll_threshold) / p.payroll_step
        ) * p.payroll_factor
        payroll_cap_applied = payroll_indicator_raw > p.payroll_cap
        payroll_indicator = min(payroll_indicator_raw, p.payroll_cap)

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
        # Фактически применённые капы. Нужны вкладке MDE, чтобы показать, что
        # реально сработало (кап дохода там может быть задан вручную).
        "revenue_cap": revenue_cap,
        "taxes_cap": p.taxes_cap,
        "payroll_cap": p.payroll_cap,
        "pfu_cap": pfu_cap,
    }
