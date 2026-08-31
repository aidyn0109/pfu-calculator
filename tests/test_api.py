"""Тесты API на изолированной БД (без обращения к рабочему pfu.db)."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.routes import router
from app.auth import require_admin, require_login
from app.config import IMPORT_FILE_PATH, MRP, YEARS
from app.data.cache import CompanyCache
from app.db.companies import upsert_companies
from app.db.database import Base
from app.dependencies import get_cache, get_session

SEED_BIN = "000000000001"
FAKE_ADMIN = {"username": "test", "role": "admin"}


@pytest_asyncio.fixture
async def client(tmp_path):
    """Поднять приложение с временной SQLite-БД и одной засеянной компанией."""
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    test_cache = CompanyCache()

    async with factory() as session:
        await upsert_companies(
            session,
            [
                {
                    "bin": SEED_BIN,
                    "name": "ТОО Тест",
                    "revenue_2022": 1_000_000_000,
                    "revenue_2023": 1_000_000_000,
                    "revenue_2024": 1_000_000_000,
                    "revenue_2025": 1_000_000_000,
                    "taxes_2022": 50_000_000,
                    "taxes_2023": 50_000_000,
                    "taxes_2024": 50_000_000,
                    "taxes_2025": 50_000_000,
                    "payroll_2022": 200_000_000,
                    "payroll_2023": 200_000_000,
                    "payroll_2024": 100_000_000,
                    "payroll_2025": 100_000_000,
                }
            ],
        )
        await test_cache.rebuild(session)

    app = FastAPI()
    app.include_router(router)

    async def _get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    app.dependency_overrides[get_cache] = lambda: test_cache
    # Авторизация подменяется фиктивным админом (сессии в тестовом приложении нет).
    app.dependency_overrides[require_login] = lambda: FAKE_ADMIN
    app.dependency_overrides[require_admin] = lambda: FAKE_ADMIN

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await engine.dispose()


async def test_companies(client: AsyncClient) -> None:
    resp = await client.get("/companies")
    assert resp.status_code == 200
    data = resp.json()
    assert data == [{"bin": SEED_BIN, "name": "ТОО Тест"}]


async def test_calculate_ok(client: AsyncClient) -> None:
    resp = await client.post(
        "/calculate", json={"amount": 5_000_000_000, "company_bins": [SEED_BIN]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["calculation_id"] >= 1
    assert data["amount_mrp"] == pytest.approx(5_000_000_000 / MRP)
    r = data["results"][0]
    # revenue 15.0 + taxes 10.0 + payroll 5.4 = 30.4 (с 2025 годом)
    assert r["pfu_final"] == pytest.approx(30.4)
    assert r["years_used"] == list(YEARS)
    # Годы не переданы → расчёт по всем.
    assert data["years"] == list(YEARS)


async def test_calculate_with_selected_years(client: AsyncClient) -> None:
    """Выбранные годы применяются к расчёту и попадают в ответ и историю."""
    resp = await client.post(
        "/calculate",
        json={
            "amount": 5_000_000_000,
            "company_bins": [SEED_BIN],
            "years": [2024, 2022],  # намеренно не по порядку
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["years"] == [2022, 2024]  # порядок нормализован
    assert data["results"][0]["years_used"] == [2022, 2024]

    hist = await client.get("/history")
    item = next(h for h in hist.json() if h["id"] == data["calculation_id"])
    assert item["years"] == [2022, 2024]


async def test_calculate_rejects_unknown_year(client: AsyncClient) -> None:
    resp = await client.post(
        "/calculate",
        json={"amount": 5_000_000_000, "company_bins": [SEED_BIN], "years": [2019]},
    )
    assert resp.status_code == 422


async def test_calculate_empty_years_means_all(client: AsyncClient) -> None:
    """Пустой список годов трактуется как «все годы» (обратная совместимость)."""
    resp = await client.post(
        "/calculate",
        json={"amount": 5_000_000_000, "company_bins": [SEED_BIN], "years": []},
    )
    assert resp.status_code == 200
    assert resp.json()["years"] == list(YEARS)


async def test_calculate_below_800k_mrp_succeeds(client: AsyncClient) -> None:
    """Порог в 800 000 МРП снят — малая сумма считается, а не отклоняется."""
    resp = await client.post(
        "/calculate", json={"amount": 1_000_000, "company_bins": [SEED_BIN]}
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert "error" not in result or result["error"] is None
    # Нижний уровень: Revenue_cap = 100%, PFU_cap = 365%.
    assert result["revenue_indicator"] == 100.0
    assert result["pfu_final"] <= 365.0


async def test_calculate_amount_not_positive(client: AsyncClient) -> None:
    resp = await client.post(
        "/calculate", json={"amount": 0, "company_bins": [SEED_BIN]}
    )
    assert resp.status_code == 422  # отсекается pydantic (gt=0)


async def test_calculate_unknown_bin(client: AsyncClient) -> None:
    resp = await client.post(
        "/calculate", json={"amount": 5_000_000_000, "company_bins": ["999999999999"]}
    )
    assert resp.status_code == 400
    assert "999999999999" in resp.json()["detail"]


async def test_history_and_export(client: AsyncClient) -> None:
    calc = await client.post(
        "/calculate", json={"amount": 5_000_000_000, "company_bins": [SEED_BIN]}
    )
    calc_id = calc.json()["calculation_id"]

    hist = await client.get("/history")
    assert hist.status_code == 200
    assert any(item["id"] == calc_id for item in hist.json())

    export = await client.get(f"/export/{calc_id}")
    assert export.status_code == 200
    assert export.content[:2] == b"PK"  # zip-сигнатура xlsx

    missing = await client.get("/export/999999")
    assert missing.status_code == 404


async def test_import_upload_rejects_non_excel(client: AsyncClient) -> None:
    resp = await client.post(
        "/admin/import-excel-upload",
        files={"file": ("data.txt", b"not excel", "text/plain")},
    )
    assert resp.status_code == 400


@pytest.mark.skipif(not os.path.exists(IMPORT_FILE_PATH), reason="нет файла импорта")
async def test_import_upload_ok(client: AsyncClient) -> None:
    with open(IMPORT_FILE_PATH, "rb") as f:
        content = f.read()
    resp = await client.post(
        "/admin/import-excel-upload",
        files={
            "file": (
                "companies.xlsx",
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] >= 1
    assert data["errors"] == []
