"""Тесты импортёра Excel: нормализация значений и чтение реального файла."""

from __future__ import annotations

import math
import os

import pytest

from app.config import IMPORT_FILE_PATH
from app.data.importer import (
    _normalize_bin,
    _to_optional_float,
    read_excel,
)


# --- Нормализация БИН --------------------------------------------------------
def test_normalize_bin_pads_to_12() -> None:
    assert _normalize_bin(10740001450) == "010740001450"
    assert _normalize_bin(340001900) == "000340001900"


def test_normalize_bin_float_and_blank() -> None:
    assert _normalize_bin(10740001450.0) == "010740001450"
    assert _normalize_bin(None) is None
    assert _normalize_bin(float("nan")) is None
    assert _normalize_bin("") is None


# --- Преобразование чисел ----------------------------------------------------
def test_to_optional_float() -> None:
    assert _to_optional_float(123) == 123.0
    assert _to_optional_float("123.5") == 123.5
    assert _to_optional_float(None) is None
    assert _to_optional_float("") is None
    assert _to_optional_float("   ") is None
    assert _to_optional_float(float("nan")) is None
    assert _to_optional_float("abc") is None


# --- Чтение реального файла --------------------------------------------------
@pytest.mark.skipif(
    not os.path.exists(IMPORT_FILE_PATH), reason="нет файла импорта"
)
def test_read_excel_real_file() -> None:
    rows, warnings, errors = read_excel(IMPORT_FILE_PATH)
    assert len(rows) == 46
    assert errors == []
    # Все БИН нормализованы до 12 цифр.
    for row in rows:
        assert len(row["bin"]) == 12
        assert row["bin"].isdigit()
        assert row["name"]
        # Каждая строка содержит все 9 метрик (значение или None).
        for prefix in ("revenue", "taxes", "payroll"):
            for year in (2022, 2023, 2024):
                key = f"{prefix}_{year}"
                assert key in row, f"Отсутствует колонка {key} в строке"
                value = row[key]
                assert value is None or isinstance(value, float), f"Некорректное значение {key}: {value!r}"


def test_read_excel_missing_file() -> None:
    from app.data.importer import ImportValidationError

    with pytest.raises(ImportValidationError):
        read_excel("data/import/__does_not_exist__.xlsx")
