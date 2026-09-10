"""Центральная конфигурация калькулятора ПФУ.

ВСЕ константы (МРП, капы, пороги, шаги, факторы) определяются ТОЛЬКО здесь.
Никогда не хардкодить эти значения в формулах или других модулях.
"""

from __future__ import annotations

import os

# --- Константы МРП -----------------------------------------------------------
MRP: int = 4_325  # тенге, актуальное значение на 2024 год

# --- Годы, по которым ведётся расчёт ----------------------------------------
YEARS: tuple[int, int, int, int] = (2022, 2023, 2024, 2025)

# --- Диапазоны суммы в МРП и капы для Revenue_indicator ----------------------
# Каждый элемент: (S_mrp_min, S_mrp_max, cap_percent). Границы включительны
# с обеих сторон; диапазоны проверяются по порядку — первый подходящий выигрывает.
REVENUE_CAPS: list[tuple[int, int, float]] = [
    (800_000, 1_600_000, 200.0),
    (1_600_000, 3_200_000, 500.0),
]
REVENUE_CAP_ABOVE_MAX: float = 700.0
# Суммы ниже 800 000 МРП (порог валидации снят) — отдельный нижний уровень.
REVENUE_CAP_BELOW_MIN: float = 100.0

# --- Капы для индивидуальных показателей -------------------------------------
TAXES_CAP: float = 65.0  # %
PAYROLL_CAP: float = 100.0  # %

# --- Диапазоны и капы для итогового ПФУ --------------------------------------
PFU_CAPS: list[tuple[int, int, float]] = [
    (800_000, 1_600_000, 365.0),
    (1_600_000, 3_200_000, 665.0),
]
PFU_CAP_ABOVE_MAX: float = 865.0

# --- Нижняя граница базового уровня капов ------------------------------------
# Раньше служила минимальным порогом суммы: расчёт ниже 800 000 МРП отклонялся.
# Валидация снята (встречаются реальные суммы ниже порога), значение осталось
# как справочная граница нижнего уровня REVENUE_CAPS / PFU_CAPS.
S_MRP_MIN: int = 800_000

# --- Пороговые значения формул -----------------------------------------------
REVENUE_THRESHOLD: float = 50.0
TAXES_THRESHOLD: float = 3.0
PAYROLL_THRESHOLD: float = 6.6

# --- Шаги и факторы формул ----------------------------------------------------
REVENUE_STEP: float = 0.1
REVENUE_FACTOR: float = 0.05
TAXES_STEP: float = 0.1
TAXES_FACTOR: float = 0.5
PAYROLL_STEP: float = 0.1
PAYROLL_FACTOR: float = 0.1

# --- Вкладки-источники расчёта -----------------------------------------------
# Хранится в calculations.kind; NULL = KIND_PFU (записи до появления MDE).
KIND_PFU: str = "pfu"
KIND_MDE: str = "mde"

# --- Округление для отображения/экспорта -------------------------------------
DISPLAY_DECIMALS: int = 2

# --- База данных и окружение -------------------------------------------------
def _normalize_database_url(url: str) -> str:
    """Привести DATABASE_URL к async-драйверу.

    Render/Heroku выдают URL вида ``postgres://`` или ``postgresql://`` без
    указания async-драйвера. SQLAlchemy async требует ``+asyncpg``. SQLite-URL
    для локальной разработки не трогаем.
    """
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    return url


# Fallback на локальный SQLite; на Render задаётся переменной окружения.
DATABASE_URL: str = _normalize_database_url(
    os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./pfu.db")
)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
MAX_HISTORY_RECORDS: int = 1000

# Порт берётся из окружения (Render задаёт PORT автоматически).
PORT: int = int(os.getenv("PORT", "8000"))

# --- Авторизация и роли ------------------------------------------------------
# Ключ подписи cookie-сессии. В продакшене ОБЯЗАТЕЛЬНО задать SECRET_KEY в env.
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")

ROLE_ADMIN: str = "admin"
ROLE_USER: str = "user"

# Учётные записи берутся из окружения (логин/пароль на роль).
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
USER_USERNAME: str = os.getenv("USER_USERNAME", "user")
USER_PASSWORD: str = os.getenv("USER_PASSWORD", "user")

# --- Ожидаемые столбцы в Excel ------------------------------------------------
# Точные названия сверены с фактическим файлом data/import/companies.xlsx.
EXCEL_COLUMNS: dict[str, object] = {
    "bin": "БИН ТОО",
    "name": "Наименование ТОО",
    "revenue": ["Доходы 2022", "Доходы 2023", "Доходы 2024", "Доходы 2025"],
    "taxes": [
        "Уплаченные налоги 2022",
        "Уплаченные налоги 2023",
        "Уплаченные налоги 2024",
        "Уплаченные налоги 2025",
    ],
    "payroll": ["ФОТ 2022", "ФОТ 2023", "ФОТ 2024", "ФОТ 2025"],
}

# Длина БИН для нормализации (ведущие нули при импорте из Excel теряются).
BIN_LENGTH: int = 12

# --- Корпоративный стиль BI Group --------------------------------------------
BRAND_COLOR_PRIMARY: str = "#0060FE"
BRAND_COLOR_SECONDARY: str = "#FFFFFF"

# --- Путь для загрузки Excel при импорте -------------------------------------
IMPORT_FILE_PATH: str = "data/import/companies.xlsx"
