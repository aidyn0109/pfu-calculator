"""REST API эндпоинты калькулятора ПФУ."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    CalculateRequest,
    CalculateResponse,
    CompanyFull,
    CompanyInput,
    CompanyShort,
    CompanyUpdate,
    HistoryItem,
    ImportResponse,
)
from app.config import MRP
from app.core.calculator import (
    AmountValidationError,
    calculate_pfu,
    normalize_years,
    validate_amount,
)
from app.data.cache import CompanyCache
from app.data.exporter import build_export
from app.data.importer import (
    ImportValidationError,
    import_from_bytes,
    import_from_excel,
)
from app.db.calculations import (
    get_calculation,
    get_recent_calculations,
    save_calculation,
    years_of,
)
from app.auth import require_admin, require_login
from app.db.companies import create_company, get_all_companies, update_company
from app.dependencies import get_cache, get_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/companies",
    response_model=list[CompanyShort],
    dependencies=[Depends(require_login)],
)
async def list_companies(cache: CompanyCache = Depends(get_cache)) -> list[CompanyShort]:
    """Список всех компаний из кеша (для мультиселекта)."""
    return [CompanyShort(bin=c.bin, name=c.name) for c in cache.all()]


@router.post(
    "/calculate",
    response_model=CalculateResponse,
    dependencies=[Depends(require_login)],
)
async def calculate(
    payload: CalculateRequest,
    cache: CompanyCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> CalculateResponse:
    """Рассчитать ПФУ по выбранным компаниям и годам, сохранить расчёт."""
    # Шаг 0/1: валидация суммы (S<=0 отсекается pydantic → 422; S_mrp<min → 400).
    try:
        validate_amount(payload.amount)
    except AmountValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Годы уже проверены схемой; normalize_years приводит None к полному списку.
    selected_years = normalize_years(payload.years)

    found, missing = cache.get_many(payload.company_bins)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Компании не найдены по БИН: " + ", ".join(missing),
        )

    results: list[dict[str, Any]] = [
        calculate_pfu(company, payload.amount, selected_years) for company in found
    ]

    amount_mrp = payload.amount / MRP
    calc = await save_calculation(
        session,
        amount=payload.amount,
        amount_mrp=amount_mrp,
        company_bins=payload.company_bins,
        results=results,
        years=selected_years,
    )

    return CalculateResponse(
        calculation_id=calc.id,
        amount=payload.amount,
        amount_mrp=amount_mrp,
        years=selected_years,
        results=results,  # type: ignore[arg-type]
    )


@router.get(
    "/history",
    response_model=list[HistoryItem],
    dependencies=[Depends(require_login)],
)
async def history(session: AsyncSession = Depends(get_session)) -> list[HistoryItem]:
    """Последние 20 расчётов."""
    records = await get_recent_calculations(session, limit=20)
    return [
        HistoryItem(
            id=rec.id,
            created_at=str(rec.created_at),
            amount=rec.amount,
            amount_mrp=rec.amount_mrp,
            companies_count=rec.companies_count,
            company_bins=json.loads(rec.company_bins),
            years=years_of(rec),
        )
        for rec in records
    ]


@router.get("/export/{calculation_id}", dependencies=[Depends(require_login)])
async def export(
    calculation_id: int, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    """Excel-файл с результатами расчёта по calculation_id."""
    calc = await get_calculation(session, calculation_id)
    if calc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Расчёт #{calculation_id} не найден",
        )

    content = build_export(calc)
    filename = f"pfu_calculation_{calculation_id}.xlsx"
    return StreamingResponse(
        iter([content]),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/admin/import-excel",
    response_model=ImportResponse,
    dependencies=[Depends(require_admin)],
)
async def import_excel(
    cache: CompanyCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> ImportResponse:
    """Импорт компаний из Excel (upsert по БИН) и пересборка кеша."""
    try:
        summary = await import_from_excel(session)
    except ImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await cache.rebuild(session)
    return ImportResponse(**summary)


@router.post(
    "/admin/import-excel-upload",
    response_model=ImportResponse,
    dependencies=[Depends(require_admin)],
)
async def import_excel_upload(
    file: UploadFile = File(...),
    cache: CompanyCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> ImportResponse:
    """Импорт компаний из загруженного через браузер Excel-файла (upsert по БИН)."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ожидается файл Excel (.xlsx или .xls)",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Файл пустой"
        )

    try:
        summary = await import_from_bytes(session, content)
    except ImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await cache.rebuild(session)
    return ImportResponse(**summary)


@router.get(
    "/admin/companies",
    response_model=list[CompanyFull],
    dependencies=[Depends(require_admin)],
)
async def admin_list_companies(
    session: AsyncSession = Depends(get_session),
) -> list[CompanyFull]:
    """Полный список компаний со всеми показателями (для админ-таблицы)."""
    companies = await get_all_companies(session)
    return [CompanyFull.model_validate(c) for c in companies]


@router.post(
    "/admin/companies",
    response_model=CompanyFull,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def admin_create_company(
    payload: CompanyInput,
    cache: CompanyCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> CompanyFull:
    """Добавить одну компанию вручную (без Excel)."""
    try:
        company = await create_company(session, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await cache.rebuild(session)
    return CompanyFull.model_validate(company)


@router.put(
    "/admin/companies/{bin}",
    response_model=CompanyFull,
    dependencies=[Depends(require_admin)],
)
async def admin_update_company(
    bin: str,
    payload: CompanyUpdate,
    cache: CompanyCache = Depends(get_cache),
    session: AsyncSession = Depends(get_session),
) -> CompanyFull:
    """Обновить данные одной компании (БИН не меняется)."""
    try:
        company = await update_company(session, bin, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    await cache.rebuild(session)
    return CompanyFull.model_validate(company)
