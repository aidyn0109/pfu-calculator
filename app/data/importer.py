"""Импорт данных компаний из Excel: чтение → валидация → upsert в БД.

Excel — инструмент разового/периодического пополнения. Источник истины — БД.
"""

from __future__ import annotations

import math
import os
from io import BytesIO
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import BIN_LENGTH, EXCEL_COLUMNS, IMPORT_FILE_PATH, YEARS
from app.db.companies import upsert_companies


class ImportValidationError(Exception):
    """Ошибка валидации при импорте Excel (нет файла / нет колонок)."""


def _metric_columns() -> dict[str, list[str]]:
    """Сопоставление: префикс поля ORM → список названий колонок Excel по годам."""
    return {
        "revenue": list(EXCEL_COLUMNS["revenue"]),  # type: ignore[arg-type]
        "taxes": list(EXCEL_COLUMNS["taxes"]),  # type: ignore[arg-type]
        "payroll": list(EXCEL_COLUMNS["payroll"]),  # type: ignore[arg-type]
    }


def _required_columns() -> list[str]:
    cols = [EXCEL_COLUMNS["bin"], EXCEL_COLUMNS["name"]]
    for metric_cols in _metric_columns().values():
        cols.extend(metric_cols)
    return [str(c) for c in cols]


def _normalize_bin(raw: Any) -> str | None:
    """Привести БИН к строке из BIN_LENGTH цифр (ведущие нули в Excel теряются)."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    if isinstance(raw, float):
        raw = int(raw)
    digits = str(raw).strip()
    if not digits:
        return None
    return digits.zfill(BIN_LENGTH)


def _to_optional_float(value: Any) -> float | None:
    """NaN/пусто → None, иначе float. Нечисловые значения → None."""
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result):
        return None
    return result


def read_excel(path: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Прочитать и провалидировать Excel с диска.

    Бросает ImportValidationError при отсутствии файла или обязательных колонок.
    """
    if not os.path.exists(path):
        raise ImportValidationError(f"Файл импорта не найден: {path}")

    try:
        df = pd.read_excel(path)
    except Exception as exc:  # noqa: BLE001 — оборачиваем любую ошибку чтения
        raise ImportValidationError(f"Не удалось прочитать Excel: {exc}") from exc

    return _parse_dataframe(df)


def read_excel_bytes(
    content: bytes,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Прочитать и провалидировать Excel из загруженных байтов (upload)."""
    try:
        df = pd.read_excel(BytesIO(content))
    except Exception as exc:  # noqa: BLE001 — оборачиваем любую ошибку чтения
        raise ImportValidationError(f"Не удалось прочитать Excel: {exc}") from exc

    return _parse_dataframe(df)


def _parse_dataframe(
    df: "pd.DataFrame",
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Провалидировать колонки и собрать строки для upsert.

    Возвращает (rows, warnings, errors). Бросает ImportValidationError при
    отсутствии обязательных колонок.
    """
    missing = [c for c in _required_columns() if c not in df.columns]
    if missing:
        raise ImportValidationError(
            "Отсутствуют обязательные колонки: " + ", ".join(missing)
        )

    bin_col = str(EXCEL_COLUMNS["bin"])
    name_col = str(EXCEL_COLUMNS["name"])
    metric_cols = _metric_columns()

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    seen_bins: set[str] = set()

    for idx, record in df.iterrows():
        excel_row = int(idx) + 2  # +1 за заголовок, +1 за 0-based индекс

        bin_ = _normalize_bin(record[bin_col])
        if bin_ is None:
            errors.append(f"Строка {excel_row}: отсутствует или некорректный БИН")
            continue
        if bin_ in seen_bins:
            warnings.append(f"Строка {excel_row}: дубликат БИН {bin_} — перезаписан")
        seen_bins.add(bin_)

        name = record[name_col]
        name = str(name).strip() if not _is_blank(name) else ""
        if not name:
            errors.append(f"Строка {excel_row}: отсутствует наименование (БИН {bin_})")
            continue

        row: dict[str, Any] = {"bin": bin_, "name": name}
        for prefix, cols in metric_cols.items():
            for year, col in zip(YEARS, cols):
                value = _to_optional_float(record[col])
                row[f"{prefix}_{year}"] = value
                if value is None:
                    warnings.append(f"Строка {excel_row}: отсутствует {col}")

        rows.append(row)

    return rows, warnings, errors


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


async def import_from_excel(
    session: AsyncSession, path: str | None = None
) -> dict[str, Any]:
    """Импортировать компании из Excel в БД (upsert по БИН).

    Возвращает сводку по разделу 8 CLAUDE.md.
    """
    path = path or IMPORT_FILE_PATH
    rows, warnings, errors = read_excel(path)
    return await _persist(session, rows, warnings, errors)


async def import_from_bytes(
    session: AsyncSession, content: bytes
) -> dict[str, Any]:
    """Импортировать компании из загруженного Excel-файла (upsert по БИН)."""
    rows, warnings, errors = read_excel_bytes(content)
    return await _persist(session, rows, warnings, errors)


async def _persist(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    warnings: list[str],
    errors: list[str],
) -> dict[str, Any]:
    """Записать строки в БД и вернуть сводку по разделу 8 CLAUDE.md."""
    added, updated = await upsert_companies(session, rows)
    return {
        "imported": len(rows),
        "added": added,
        "updated": updated,
        "warnings": warnings,
        "errors": errors,
    }
