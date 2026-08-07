"""Тесты бизнес-логики расчёта ПФУ (раздел 12 CLAUDE.md).

Реализованы ВСЕ тесты из списка. Формулы не меняются — при расхождении
исправляется calculator, а не тест.

Примечание по капам ПФУ: сумма индивидуальных капов в каждом диапазоне
(200+65+100=365; 500+65+100=665; 700+65+100=865) РАВНА соответствующему
PFU_cap (365/665/865). Поэтому PFU_raw может достичь PFU_cap, но не превысить
его, и pfu_final = min(pfu_raw, pfu_cap). Тесты PFU-капа проверяют корректность
ВЫБОРА капа по диапазону S_mrp и равенство pfu_final = min(pfu_raw, pfu_cap).
"""

from __future__ import annotations

import pytest

from app.config import (
    MRP,
    PFU_CAP_ABOVE_MAX,
    PFU_CAPS,
    REVENUE_CAP_ABOVE_MAX,
    REVENUE_CAPS,
    YEARS,
)
from app.core.calculator import (
    AmountValidationError,
    _cap_for,
    calculate_pfu,
    round_half_up,
)
from app.models.company import CompanyData


# --- Хелперы -----------------------------------------------------------------
def make_company(**kwargs) -> CompanyData:
    """Удобный конструктор CompanyData с дефолтами bin/name."""
    kwargs.setdefault("bin", "000000000001")
    kwargs.setdefault("name", "ТОО Тест")
    return CompanyData(**kwargs)


def s_for_mrp(s_mrp: float) -> float:
    """Сумма в тенге для заданного S_mrp."""
    return s_mrp * MRP


# Сумма в диапазоне [800 000; 1 600 000] МРП (кап дохода 200, ПФУ 365).
S_RANGE1 = 5_000_000_000  # S_mrp ≈ 1 156 069


# --- Тесты -------------------------------------------------------------------
def test_basic_calculation() -> None:
    """Эталонный расчёт с известным результатом, без срабатывания капов."""
    company = make_company(
        revenue_2022=1_000_000_000,
        revenue_2023=1_000_000_000,
        revenue_2024=1_000_000_000,
        revenue_2025=1_000_000_000,  # Revenue_sum = 4e9
        taxes_2022=50_000_000,
        taxes_2023=50_000_000,
        taxes_2024=50_000_000,
        taxes_2025=50_000_000,  # Taxes_sum = 2e8
        payroll_2022=200_000_000,
        payroll_2023=200_000_000,
        payroll_2024=100_000_000,
        payroll_2025=100_000_000,  # Payroll_sum = 6e8
    )
    r = calculate_pfu(company, S_RANGE1)

    assert r["years_used"] == list(YEARS)
    assert r["warnings"] == []

    # Revenue_sum 4e9 / S 5e9 = 80% → indicator = ((80-50)/0.1)*0.05 = 15.0
    assert r["revenue_percent"] == pytest.approx(80.0)
    assert r["revenue_indicator"] == pytest.approx(15.0)
    assert r["revenue_cap_applied"] is False

    # Taxes_sum 2e8 / Revenue_sum 4e9 = 5% → indicator = ((5-3)/0.1)*0.5 = 10.0
    assert r["taxes_percent"] == pytest.approx(5.0)
    assert r["taxes_indicator"] == pytest.approx(10.0)
    assert r["taxes_cap_applied"] is False

    # Payroll_sum 6e8 / S 5e9 = 12% → indicator = ((12-6.6)/0.1)*0.1 = 5.4
    assert r["payroll_percent"] == pytest.approx(12.0)
    assert r["payroll_indicator"] == pytest.approx(5.4)
    assert r["payroll_cap_applied"] is False

    # PFU_raw = 15.0 + 10.0 + 5.4 = 30.4
    assert r["pfu_raw"] == pytest.approx(30.4)
    assert r["pfu_final"] == pytest.approx(30.4)
    assert r["pfu_cap_applied"] is False


def test_revenue_cap_200() -> None:
    """S_mrp в [800k; 1.6m] → Revenue_cap = 200%."""
    company = make_company(
        revenue_2022=30_000_000_000,  # огромный доход → индикатор > 200
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["revenue_cap_applied"] is True
    assert r["revenue_indicator"] == pytest.approx(200.0)


def test_revenue_cap_500() -> None:
    """S_mrp в (1.6m; 3.2m] → Revenue_cap = 500%."""
    s = s_for_mrp(2_000_000)
    company = make_company(
        revenue_2022=100_000_000_000,
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, s)
    assert r["revenue_cap_applied"] is True
    assert r["revenue_indicator"] == pytest.approx(500.0)


def test_revenue_cap_700() -> None:
    """S_mrp > 3.2m → Revenue_cap = 700%."""
    s = s_for_mrp(4_000_000)
    company = make_company(
        revenue_2022=300_000_000_000,
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, s)
    assert r["revenue_cap_applied"] is True
    assert r["revenue_indicator"] == pytest.approx(700.0)


def test_revenue_cap_not_applied() -> None:
    """Revenue_indicator < cap → возвращается фактическое значение."""
    company = make_company(
        revenue_2022=3_000_000_000,  # Revenue_sum = 3e9 → 60% → индикатор 5.0
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["revenue_cap_applied"] is False
    assert r["revenue_indicator"] == pytest.approx(5.0)


def test_taxes_cap_65() -> None:
    """Taxes_indicator ограничен 65%."""
    company = make_company(
        revenue_2022=1_000_000_000,  # Revenue_sum = 1e9
        taxes_2022=2_000_000_000,  # Taxes% = 200% → индикатор раw 985 > 65
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["taxes_cap_applied"] is True
    assert r["taxes_indicator"] == pytest.approx(65.0)


def test_payroll_cap_100() -> None:
    """Payroll_indicator ограничен 100%."""
    company = make_company(
        revenue_2022=1_000_000_000,
        taxes_2022=1_000_000,
        payroll_2022=6_000_000_000,  # Payroll% = 120% → индикатор раw 113.4 > 100
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["payroll_cap_applied"] is True
    assert r["payroll_indicator"] == pytest.approx(100.0)


def test_pfu_cap_365() -> None:
    """В диапазоне [800k; 1.6m] PFU_cap = 365% и pfu_final = min(pfu_raw, 365)."""
    s_mrp = S_RANGE1 / MRP
    assert _cap_for(s_mrp, PFU_CAPS, PFU_CAP_ABOVE_MAX) == 365.0

    # Максимизируем все показатели — pfu_raw достигает максимума 200+65+100=365.
    company = make_company(
        revenue_2022=30_000_000_000,  # revenue_indicator → 200 (cap)
        taxes_2022=2_000_000_000_000,  # taxes_indicator → 65 (cap)
        payroll_2022=6_000_000_000,  # payroll_indicator → 100 (cap)
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["pfu_raw"] == pytest.approx(365.0)
    assert r["pfu_final"] == pytest.approx(min(r["pfu_raw"], 365.0))
    assert r["pfu_final"] <= 365.0


def test_pfu_cap_665() -> None:
    """В диапазоне (1.6m; 3.2m] PFU_cap = 665% и pfu_final = min(pfu_raw, 665)."""
    s = s_for_mrp(2_000_000)
    assert _cap_for(s / MRP, PFU_CAPS, PFU_CAP_ABOVE_MAX) == 665.0

    company = make_company(
        revenue_2022=100_000_000_000,  # → 500 (cap)
        taxes_2022=2_000_000_000_000,  # → 65 (cap)
        payroll_2022=20_000_000_000,  # → 100 (cap)
    )
    r = calculate_pfu(company, s)
    assert r["pfu_raw"] == pytest.approx(665.0)
    assert r["pfu_final"] == pytest.approx(min(r["pfu_raw"], 665.0))
    assert r["pfu_final"] <= 665.0


def test_pfu_cap_865() -> None:
    """При S_mrp > 3.2m PFU_cap = 865% и pfu_final = min(pfu_raw, 865)."""
    s = s_for_mrp(4_000_000)
    assert _cap_for(s / MRP, PFU_CAPS, PFU_CAP_ABOVE_MAX) == 865.0

    company = make_company(
        revenue_2022=300_000_000_000,  # → 700 (cap)
        taxes_2022=2_000_000_000_000,  # → 65 (cap)
        payroll_2022=40_000_000_000,  # → 100 (cap)
    )
    r = calculate_pfu(company, s)
    assert r["pfu_raw"] == pytest.approx(865.0)
    assert r["pfu_final"] == pytest.approx(min(r["pfu_raw"], 865.0))
    assert r["pfu_final"] <= 865.0


def test_negative_indicators() -> None:
    """Отрицательные показатели не обнуляются."""
    company = make_company(
        revenue_2022=1_000_000_000,  # 20% → revenue_indicator = -15
        taxes_2022=10_000_000,  # 1% от дохода → taxes_indicator = (1-3)*5 = -10.0
        payroll_2022=100_000_000,  # 2% → payroll_indicator = -4.6
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["revenue_indicator"] == pytest.approx(-15.0)
    assert r["taxes_indicator"] == pytest.approx(-10.0)
    assert r["payroll_indicator"] == pytest.approx(-4.6)
    # PFU_raw = -15 - 10 - 4.6 = -29.6
    assert r["pfu_raw"] == pytest.approx(-29.6)
    assert r["pfu_final"] == pytest.approx(-29.6)


def test_revenue_sum_zero() -> None:
    """Revenue_sum = 0 → Taxes_indicator = 0 + предупреждение."""
    company = make_company(
        revenue_2022=0,
        revenue_2023=0,
        revenue_2024=0,  # Revenue_sum = 0
        taxes_2022=50_000_000,
        payroll_2022=200_000_000,
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["taxes_indicator"] == 0.0
    assert r["taxes_cap_applied"] is False
    assert any("доход" in w.lower() for w in r["warnings"])


def test_missing_one_year() -> None:
    """Один год NULL → предупреждение, расчёт по трём оставшимся годам."""
    company = make_company(
        revenue_2022=1_000_000_000,
        revenue_2023=1_000_000_000,
        revenue_2024=1_000_000_000,
        revenue_2025=None,  # 2025 отсутствует целиком
        taxes_2022=50_000_000,
        taxes_2023=50_000_000,
        taxes_2024=50_000_000,
        taxes_2025=None,
        payroll_2022=200_000_000,
        payroll_2023=200_000_000,
        payroll_2024=100_000_000,
        payroll_2025=None,
    )
    r = calculate_pfu(company, S_RANGE1)
    assert r["years_used"] == [2022, 2023, 2024]
    assert any(str(YEARS[-1]) in w for w in r["warnings"])  # предупреждение о 2025
    # Revenue_sum = 3e9 → 60% → индикатор = 5.0
    assert r["revenue_percent"] == pytest.approx(60.0)


def test_all_years_missing() -> None:
    """Все 3 года NULL → ошибка по компании, показатели отсутствуют."""
    company = make_company()  # все метрики None
    r = calculate_pfu(company, S_RANGE1)
    assert r["years_used"] == []
    assert "error" in r
    assert "revenue_indicator" not in r


def test_s_below_minimum() -> None:
    """S_mrp < 800 000 и S <= 0 → ошибка валидации."""
    company = make_company(revenue_2022=1_000_000_000)
    with pytest.raises(AmountValidationError):
        calculate_pfu(company, 1_000_000)  # S_mrp ≈ 231
    with pytest.raises(AmountValidationError):
        calculate_pfu(company, 0)


def test_boundary_1_600_000() -> None:
    """Ровно 1 600 000 МРП → Revenue_cap = 200% (не 500%)."""
    s = s_for_mrp(1_600_000)
    assert _cap_for(1_600_000, REVENUE_CAPS, REVENUE_CAP_ABOVE_MAX) == 200.0
    company = make_company(
        revenue_2022=200_000_000_000,  # индикатор заведомо > 500
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, s)
    assert r["revenue_indicator"] == pytest.approx(200.0)  # кап 200, не 500


def test_boundary_3_200_000() -> None:
    """Ровно 3 200 000 МРП → Revenue_cap = 500% (не 700%)."""
    s = s_for_mrp(3_200_000)
    assert _cap_for(3_200_000, REVENUE_CAPS, REVENUE_CAP_ABOVE_MAX) == 500.0
    company = make_company(
        revenue_2022=400_000_000_000,  # индикатор заведомо > 700
        taxes_2022=1_000_000,
        payroll_2022=1_000_000,
    )
    r = calculate_pfu(company, s)
    assert r["revenue_indicator"] == pytest.approx(500.0)  # кап 500, не 700


def test_round_half_up() -> None:
    """Проверка округления half-up для отображения."""
    assert round_half_up(9.405) == 9.41
    assert round_half_up(2.5, 0) == 3.0
    assert round_half_up(123.455) == 123.46
