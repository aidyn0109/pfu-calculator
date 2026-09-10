"""Точка входа FastAPI: инициализация БД, загрузка кеша, авторизация, страницы."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# .env загружается ДО импорта модулей, читающих переменные среды в app.config.
load_dotenv()

from fastapi import FastAPI, Form, Request  # noqa: E402
from fastapi.responses import JSONResponse, RedirectResponse  # noqa: E402
from fastapi.templating import Jinja2Templates  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from app.api.routes import router  # noqa: E402
from app.auth import authenticate  # noqa: E402
from app.config import (  # noqa: E402
    BRAND_COLOR_PRIMARY,
    IMPORT_FILE_PATH,
    LOG_LEVEL,
    MRP,
    PAYROLL_CAP,
    PAYROLL_FACTOR,
    PAYROLL_STEP,
    PAYROLL_THRESHOLD,
    REVENUE_CAP_ABOVE_MAX,
    REVENUE_CAP_BELOW_MIN,
    REVENUE_CAPS,
    ROLE_ADMIN,
    SECRET_KEY,
    TAXES_CAP,
    TAXES_FACTOR,
    TAXES_STEP,
    TAXES_THRESHOLD,
    YEARS,
)
from app.data.cache import cache  # noqa: E402
from app.data.importer import ImportValidationError, import_from_excel  # noqa: E402
from app.db.companies import get_all_companies  # noqa: E402
from app.db.database import async_session_factory, init_db  # noqa: E402

logging.basicConfig(level=getattr(logging, LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Значения по умолчанию для полей параметров на вкладке MDE. Берутся из config,
# чтобы числа формул не дублировались в HTML (раздел 6 CLAUDE.md).
# revenue_cap здесь нет: пустое поле = авто по диапазону суммы.
CALC_DEFAULTS: dict[str, float] = {
    "taxes_threshold": TAXES_THRESHOLD,
    "taxes_step": TAXES_STEP,
    "taxes_factor": TAXES_FACTOR,
    "taxes_cap": TAXES_CAP,
    "payroll_threshold": PAYROLL_THRESHOLD,
    "payroll_step": PAYROLL_STEP,
    "payroll_factor": PAYROLL_FACTOR,
    "payroll_cap": PAYROLL_CAP,
}


def _revenue_cap_tiers() -> list[dict[str, object]]:
    """Ступени капа дохода для подсказки «авто» на вкладке MDE.

    Порядок и правила границ повторяют calculator._cap_for: сначала уровень
    ниже первого диапазона (строгая граница), затем диапазоны по верхней
    включительной границе, затем всё выше максимума. Собирается из config,
    чтобы числа не дублировались в HTML; фактический кап считает сервер.
    """
    tiers: list[dict[str, object]] = [
        {
            "bound": REVENUE_CAPS[0][0],
            "inclusive": False,
            "cap": REVENUE_CAP_BELOW_MIN,
        }
    ]
    tiers += [{"bound": hi, "inclusive": True, "cap": cap} for _lo, hi, cap in REVENUE_CAPS]
    tiers.append({"bound": None, "inclusive": True, "cap": REVENUE_CAP_ABOVE_MAX})
    return tiers


REVENUE_CAP_TIERS: list[dict[str, object]] = _revenue_cap_tiers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Старт: создать таблицы, при необходимости авто-загрузить данные, поднять кеш.

    Авто-импорт срабатывает только если таблица компаний пустая и файл
    data/import/companies.xlsx присутствует. Это наполняет БД при первом
    запуске на новом окружении (например, чистый PostgreSQL на Render),
    не затрагивая уже существующие данные при последующих деплоях.
    """
    await init_db()
    async with async_session_factory() as session:
        existing = await get_all_companies(session)
        if not existing and os.path.exists(IMPORT_FILE_PATH):
            try:
                summary = await import_from_excel(session)
                logger.info(
                    "Авто-импорт при старте: добавлено %d компаний (ошибок: %d)",
                    summary["added"],
                    len(summary["errors"]),
                )
            except ImportValidationError as exc:
                logger.warning("Авто-импорт пропущен: %s", exc)

        count = await cache.rebuild(session)
    logger.info("Кеш загружен: %d компаний", count)
    yield


app = FastAPI(title="Калькулятор ПФУ", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.include_router(router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Любая неожиданная ошибка → 500 без утечки трейсбэка пользователю."""
    logger.exception("Необработанная ошибка при запросе %s", request.url)
    return JSONResponse(
        status_code=500,
        content={"detail": "Произошла ошибка. Обратитесь к администратору"},
    )


def _render(request: Request, template: str, **extra):
    """Отрисовать шаблон с общим контекстом (текущий пользователь, бренд)."""
    context = {
        "request": request,
        "brand_color": BRAND_COLOR_PRIMARY,
        "user": request.session.get("user"),
        "years": list(YEARS),
        "mrp": MRP,
    }
    context.update(extra)
    return templates.TemplateResponse(template, context)


# --- Авторизация -------------------------------------------------------------
@app.get("/login")
async def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=302)
    return _render(request, "login.html")


@app.post("/login")
async def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    user = authenticate(username, password)
    if user is None:
        return _render(
            request, "login.html", error="Неверный логин или пароль", username=username
        )
    request.session["user"] = user
    target = "/admin" if user["role"] == ROLE_ADMIN else "/"
    return RedirectResponse(target, status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# --- Страницы ----------------------------------------------------------------
# Примечание: GET /history занят JSON-эндпоинтом (раздел 8 CLAUDE.md), поэтому
# история отображается секцией на главной странице, а не отдельным маршрутом.
@app.get("/")
async def index(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)
    return _render(request, "index.html")


@app.get("/mde")
async def mde_page(request: Request):
    """Калькулятор MDE — тот же расчёт, но с ручным вводом параметров формул."""
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=302)
    return _render(
        request,
        "mde.html",
        defaults=CALC_DEFAULTS,
        revenue_cap_tiers=REVENUE_CAP_TIERS,
    )


@app.get("/admin")
async def admin_page(request: Request):
    user = request.session.get("user")
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user.get("role") != ROLE_ADMIN:
        # Пользователю без прав админа — обратно на калькулятор.
        return RedirectResponse("/", status_code=302)
    return _render(request, "admin.html")


if __name__ == "__main__":
    import uvicorn

    from app.config import PORT

    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT)
