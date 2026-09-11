# CLAUDE.md — Калькулятор ПФУ (Показатель финансовой устойчивости)

> Этот файл является источником истины для разработки.  
> Читай его полностью перед началом любой задачи.  
> Не изменяй бизнес-логику без явного указания пользователя.

---

## 1. ОПИСАНИЕ ПРОЕКТА

Веб-калькулятор для расчёта Показателя финансовой устойчивости (ПФУ).

**Что делает система:**
- Пользователь вводит сумму в тенге
- Выбирает одну или несколько компаний из списка
- Система рассчитывает ПФУ по каждой компании отдельно
- Отображает промежуточные показатели и итоговый ПФУ
- Показывает предупреждения если данные по компании неполные
- Позволяет экспортировать результаты в Excel

**Две вкладки расчёта:**
- **Калькулятор** — все параметры формул берутся из `config.py`.
- **Калькулятор MDE** — те же формулы, но пороги, шаги, коэффициенты и
  ограничения показателей налогов и ФОТ, а также кап показателя дохода
  вводит пользователь. Кроме того, к итоговому ПФУ на этой вкладке
  ограничение не применяется. Второго алгоритма нет — отличаются только
  числа и этот режим.

**Целевой пользователь:** внутренний сотрудник организации BI Group  
**Платформа:** веб-приложение, только десктоп  
**Язык интерфейса:** русский

---

## 2. АРХИТЕКТУРА ДАННЫХ

### Источник данных — два уровня:

```
Excel-файл (разовый импорт)
        ↓
   [admin/import-excel]
        ↓
   SQLite (основная БД)
    ├── таблица companies     ← данные компаний (постоянно)
    └── таблица calculations  ← история расчётов (постоянно)
        ↓
   In-memory кеш (dict)      ← загружается из БД при старте
        ↓
   Расчёт ПФУ
```

### Ключевые принципы:
- **Excel — инструмент импорта** (первоначальный и последующие пополнения). После импорта файл можно удалить.
- **SQLite — единственный источник истины** для данных компаний.
- **In-memory кеш** — для быстрого доступа при расчётах. Строится из БД при старте.
- Обновление данных = новый импорт из Excel через `/admin/import-excel` (upsert: добавляет новые, обновляет существующие, не удаляет старые).

---

## 3. СТЕК ТЕХНОЛОГИЙ

### Backend
- **Python 3.11** (закреплён: `.python-version`, `runtime.txt`)
- **FastAPI** — REST API фреймворк
- **Pydantic v2** — валидация входных данных и схемы ответов
- **pandas** — загрузка и валидация Excel при импорте
- **openpyxl** — экспорт результатов в Excel
- **SQLAlchemy 2.0** — ORM (async), работает с обоими драйверами без изменений в коде
- **aiosqlite** — async драйвер SQLite (локальная разработка)
- **asyncpg** — async драйвер PostgreSQL (продакшен, например Render)
- **Starlette SessionMiddleware** (+ itsdangerous) — cookie-сессии для авторизации
- **python-dotenv** — загрузка `.env`; **python-multipart** — загрузка Excel через форму
- **uvicorn** — ASGI-сервер

### Frontend
- **Vanilla HTML + Alpine.js** (CDN, без npm/сборки)
- **Tom Select** (CDN) — мультиселект с поиском компаний
- **Jinja2** — шаблонизатор (шаблоны отдаются FastAPI)

### Деплой
- **Render** (free tier): web-сервис + управляемый PostgreSQL — см. `render.yaml`, `DEPLOY.md`
- **Docker + docker-compose + Nginx** — альтернативный вариант self-hosted

---

## 4. СТРУКТУРА ПРОЕКТА

```
pfu_calculator/
├── CLAUDE.md                  # этот файл
├── README.md
├── DEPLOY.md                  # инструкция по деплою на Render
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── render.yaml                # Render Blueprint (web + PostgreSQL)
├── runtime.txt               # python-3.11.0 (для Render/Heroku-формат)
├── .python-version           # 3.11.0 (для pyenv/Render)
├── requirements.txt
├── .env.example
│
├── app/
│   ├── main.py                # точка входа FastAPI, авторизация, страницы
│   ├── config.py              # ВСЕ константы: МРП, капы, пороги; настройки окружения
│   ├── dependencies.py        # зависимости FastAPI (кеш, сессия БД)
│   ├── auth.py                # авторизация по cookie-сессии, роли admin/user
│   │
│   ├── api/
│   │   ├── routes.py          # все эндпоинты
│   │   └── schemas.py         # Pydantic-схемы запросов и ответов
│   │
│   ├── core/                  # БИЗНЕС-ЛОГИКА — только чистые функции
│   │   └── calculator.py      # расчёт ПФУ, все формулы
│   │
│   ├── db/                    # слой базы данных
│   │   ├── database.py        # инициализация SQLAlchemy, создание таблиц
│   │   ├── models.py          # ORM-модели: Company, Calculation
│   │   ├── companies.py       # CRUD + upsert (диалект-независимый: SQLite/PostgreSQL)
│   │   └── calculations.py    # CRUD для таблицы calculations
│   │
│   ├── data/                  # работа с Excel и кеш
│   │   ├── importer.py        # чтение Excel (диск/upload) → валидация → запись в БД
│   │   ├── exporter.py        # формирование Excel-выгрузки результатов
│   │   └── cache.py           # in-memory кеш, строится из БД
│   │
│   ├── models/                # доменные модели (не ORM)
│   │   └── company.py         # dataclass CompanyData
│   │
│   └── templates/
│       ├── base.html
│       ├── login.html         # страница входа
│       ├── index.html         # калькулятор (+ история секцией)
│       ├── mde.html            # калькулятор MDE (ручной ввод параметров формул)
│       └── admin.html         # администрирование (импорт/CRUD компаний)
│
├── data/
│   └── import/
│       └── companies.xlsx         # Excel для локального авто-импорта.
│                                  # НЕ коммитить (на деплое — загрузка через UI).
│
├── exports/                   # временные Excel-экспорты (gitignore)
├── pfu.db                     # SQLite база данных, локально (gitignore)
│
└── tests/
    ├── test_calculator.py     # тесты формул — ОБЯЗАТЕЛЬНЫ
    ├── test_importer.py
    └── test_api.py
```

---

## 5. БАЗА ДАННЫХ

### Таблица `companies`

```sql
CREATE TABLE companies (
    bin         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    revenue_2022    REAL,
    revenue_2023    REAL,
    revenue_2024    REAL,
    revenue_2025    REAL,
    taxes_2022      REAL,
    taxes_2023      REAL,
    taxes_2024      REAL,
    taxes_2025      REAL,
    payroll_2022    REAL,
    payroll_2023    REAL,
    payroll_2024    REAL,
    payroll_2025    REAL,
    imported_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

- Набор годов задаётся `config.YEARS`; колонки называются `<metric>_<year>`.
- NULL в колонках года = данные отсутствуют (не 0)
- При импорте из Excel: **upsert по БИН** (INSERT OR REPLACE). Новые компании добавляются, существующие обновляются, удалённых из Excel компаний в БД не трогаем.
- Недостающие колонки годов добавляются автоматически при старте
  (`app/db/database.py:_migrate_columns` — сверка с inspector, каждый ALTER в
  своей транзакции). Данные при этом не теряются.

### Таблица `calculations`

```sql
CREATE TABLE calculations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount          REAL NOT NULL,
    amount_mrp      REAL NOT NULL,
    company_bins    TEXT NOT NULL,  -- JSON array
    results         TEXT NOT NULL,  -- JSON array результатов
    companies_count INTEGER NOT NULL,
    years           TEXT,           -- JSON array годов расчёта; NULL = все годы
    kind            TEXT,           -- 'pfu' | 'mde'; NULL = 'pfu'
    params          TEXT            -- JSON параметров MDE; NULL у обычного расчёта
);
```

- Хранить последние 1000 записей (при превышении — удалять старые)
- `years` = NULL у записей, созданных до появления выбора года; такие расчёты
  трактуются как выполненные по всем годам (`app/db/calculations.py:years_of`).
- `kind` = NULL у записей, созданных до появления вкладки MDE; такие расчёты
  трактуются как `pfu` (`app/db/calculations.py:kind_of`).
- `params` заполняется только вкладкой MDE — это те числа, которые ввёл
  пользователь (`app/db/calculations.py:params_of`). Нужны, чтобы история и
  Excel-выгрузка показывали, при каких параметрах получен результат.
- Обе колонки добавляются авто-миграцией при старте, как и колонки годов.

---

## 6. КОНФИГУРАЦИЯ (`app/config.py`)

**Все константы — только здесь. Никогда не хардкодить в формулах.**

```python
# Константы МРП
MRP = 4_325  # тенге, актуальное значение на 2024 год

# Годы, по которым ведётся расчёт. Единственное место, где задаётся набор лет:
# от него зависят колонки БД, столбцы Excel, чипы выбора года на UI и суммы.
YEARS = (2022, 2023, 2024, 2025)

# Диапазоны суммы в МРП и соответствующие капы для Revenue_indicator
REVENUE_CAPS = [
    (800_000,   1_600_000, 200.0),
    (1_600_000, 3_200_000, 500.0),
]
REVENUE_CAP_ABOVE_MAX = 700.0
# Суммы ниже 800 000 МРП — отдельный нижний уровень (только для дохода).
REVENUE_CAP_BELOW_MIN = 100.0

# Капы для индивидуальных показателей
TAXES_CAP   = 65.0   # %
PAYROLL_CAP = 100.0  # %

# Диапазоны и капы для итогового ПФУ
PFU_CAPS = [
    (800_000,   1_600_000, 365.0),
    (1_600_000, 3_200_000, 665.0),
]
PFU_CAP_ABOVE_MAX = 865.0

# Нижняя граница базового уровня капов. Валидация по ней СНЯТА — значение
# осталось границей между REVENUE_CAP_BELOW_MIN и первым уровнем REVENUE_CAPS.
S_MRP_MIN = 800_000

# Вкладки-источники расчёта (хранятся в calculations.kind)
KIND_PFU = "pfu"
KIND_MDE = "mde"

# Пороговые значения формул. На вкладке MDE значения налогов и ФОТ
# (порог/шаг/коэффициент/кап) подменяются пользовательскими — см. раздел 7.4.
REVENUE_THRESHOLD  = 50.0
TAXES_THRESHOLD    = 3.0
PAYROLL_THRESHOLD  = 6.6

# Шаги и факторы формул
REVENUE_STEP   = 0.1
REVENUE_FACTOR = 0.05
TAXES_STEP     = 0.1
TAXES_FACTOR   = 0.5
PAYROLL_STEP   = 0.1
PAYROLL_FACTOR = 0.1

# БД (из окружения, fallback на локальный SQLite).
# postgres:// и postgresql:// автоматически приводятся к postgresql+asyncpg://.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./pfu.db")
MAX_HISTORY_RECORDS = 1000

# Порт берётся из окружения (Render задаёт PORT автоматически)
PORT = int(os.getenv("PORT", "8000"))

# Авторизация и роли (учётные записи — из окружения)
SECRET_KEY     = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")
ROLE_ADMIN     = "admin"
ROLE_USER      = "user"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
USER_USERNAME  = os.getenv("USER_USERNAME", "user")
USER_PASSWORD  = os.getenv("USER_PASSWORD", "user")

# Ожидаемые столбцы в Excel (сверены с фактическим файлом companies.xlsx)
EXCEL_COLUMNS = {
    "bin":     "БИН ТОО",
    "name":    "Наименование ТОО",
    "revenue": ["Доходы 2022", "Доходы 2023", "Доходы 2024", "Доходы 2025"],
    "taxes":   ["Уплаченные налоги 2022", ..., "Уплаченные налоги 2025"],
    "payroll": ["ФОТ 2022", "ФОТ 2023", "ФОТ 2024", "ФОТ 2025"],
}
BIN_LENGTH = 12  # БИН нормализуется до 12 цифр (ведущие нули в Excel теряются)

# Корпоративный стиль BI Group
BRAND_COLOR_PRIMARY   = "#0060FE"
BRAND_COLOR_SECONDARY = "#FFFFFF"

# Путь для локального авто-импорта Excel
IMPORT_FILE_PATH = "data/import/companies.xlsx"
```

> ⚠️ Если изменяется МРП или пороговые значения — менять **только в `config.py`**.  
> ⚠️ Названия столбцов Excel сверены с реальным файлом и зафиксированы выше.

---

## 7. БИЗНЕС-ЛОГИКА РАСЧЁТА ПФУ

### 7.1 Термины и обозначения

| Переменная | Описание |
|---|---|
| `S` | Сумма в тенге, введённая пользователем |
| `S_mrp` | Сумма в МРП: `S / MRP` |
| `Y` | Годы расчёта, выбранные пользователем (подмножество `config.YEARS`) |
| `Revenue_sum` | Сумма доходов за годы `Y` |
| `Taxes_sum` | Сумма уплаченных налогов за годы `Y` |
| `Payroll_sum` | Сумма ФОТ за годы `Y` |
| `Revenue_indicator` | Показатель дохода (%) |
| `Taxes_indicator` | Показатель налогов (%) |
| `Payroll_indicator` | Показатель ФОТ (%) |
| `PFU_raw` | ПФУ до итогового капа |
| `PFU_final` | Итоговый ПФУ — финальный результат |

---

### 7.2 Пошаговый алгоритм

#### Шаг 0 — Валидация входных данных
```
Если S <= 0         → ошибка: "Сумма должна быть больше нуля"
Если год ∉ YEARS    → ошибка: "Недопустимые годы расчёта: ..."
Y не задан / пуст   → Y = все годы из config.YEARS
```

> Минимальный порог суммы (`S_mrp ≥ 800 000`) **снят**: встречаются реальные
> суммы ниже него. Единственное ограничение по сумме — `S > 0`. Суммы ниже
> 800 000 МРП считаются с `Revenue_cap = 100%` (шаг 3); `PFU_cap` для них
> остаётся 365% (шаг 6).

#### Шаг 1 — Перевод суммы в МРП
```
S_mrp = S / 4325
```

#### Шаг 2 — Суммирование по выбранным годам
```
Revenue_sum = Σ Revenue_year  для year ∈ Y
Taxes_sum   = Σ Taxes_year    для year ∈ Y
Payroll_sum = Σ Payroll_year  для year ∈ Y
```

Годы вне `Y` в суммы не входят вообще — это и есть выбор года на UI.

**Правило для отсутствующих данных (NULL в БД):**
- NULL за год → считать как 0, суммировать по имеющимся
- Добавить в `warnings`: `"Отсутствуют данные за [год(ы)]. Расчёт выполнен по: [список лет]."`
  (пропущенные годы считаются относительно `Y`, а не всех `YEARS`)
- Если данных нет ни за один год из `Y` → исключить компанию, вернуть ошибку по ней

#### Шаг 3 — Показатель дохода
```
Revenue_percent   = (Revenue_sum / S) * 100
Revenue_indicator = ((Revenue_percent - 50) / 0.1) * 0.05
Revenue_indicator = min(Revenue_indicator, Revenue_cap)
```

Определение `Revenue_cap` по `S_mrp`:
```
S_mrp < 800 000               → Revenue_cap = 100%
800 000 ≤ S_mrp ≤ 1 600 000   → Revenue_cap = 200%
1 600 000 < S_mrp ≤ 3 200 000 → Revenue_cap = 500%
S_mrp > 3 200 000             → Revenue_cap = 700%
```

> Отрицательный `Revenue_indicator` допустим — не обнулять.

#### Шаг 4 — Показатель уплаченных налогов
```
Taxes_percent   = (Taxes_sum / Revenue_sum) * 100
Taxes_indicator = ((Taxes_percent - 3) / 0.1) * 0.5
Taxes_indicator = min(Taxes_indicator, 65%)
```

> Если `Revenue_sum = 0` → `Taxes_indicator = 0`, добавить предупреждение.  
> Отрицательный `Taxes_indicator` допустим — не обнулять.

#### Шаг 5 — Показатель ФОТ
```
Payroll_percent   = (Payroll_sum / Revenue_sum) * 100
Payroll_indicator = ((Payroll_percent - 6.6) / 0.1) * 0.1
Payroll_indicator = min(Payroll_indicator, 100%)
```

> Знаменатель — **`Revenue_sum`, а не `S`**: показатель меряет долю дохода,
> уходящую на оплату труда. Отсюда тот же случай, что и у налогов:
> если `Revenue_sum = 0` → `Payroll_indicator = 0`, добавить предупреждение.
>
> Отрицательный `Payroll_indicator` допустим — не обнулять.

#### Шаг 6 — Итоговый ПФУ
```
PFU_raw   = Revenue_indicator + Taxes_indicator + Payroll_indicator
PFU_final = min(PFU_raw, PFU_cap)
```

Определение `PFU_cap` по `S_mrp`:
```
S_mrp ≤ 1 600 000             → PFU_cap = 365%
1 600 000 < S_mrp ≤ 3 200 000 → PFU_cap = 665%
S_mrp > 3 200 000             → PFU_cap = 865%
```

> Для сумм ниже 800 000 МРП PFU_cap не меняется и равен 365%. При
> `Revenue_cap = 100%` максимум `PFU_raw` там 100+65+100 = 265%, поэтому
> итоговый кап в этом диапазоне фактически никогда не срабатывает.
>
> ⚠️ Всё это относится к вкладке «Калькулятор». На вкладке MDE `PFU_cap`
> **не применяется вообще**: `PFU_final = PFU_raw` (см. раздел 7.4).

---

### 7.4 Вкладка «Калькулятор MDE» — пользовательские параметры

Формулы разделов 7.2 не меняются. Отличие только в том, откуда берутся числа:
обычный калькулятор берёт их из `config.py`, MDE — из полей, которые заполнил
пользователь. Реализовано одним расчётом: `calculate_pfu(..., params=CalcParams)`
(`app/core/calculator.py`). Второго алгоритма быть не должно.

**Что пользователь может задать (`CalcParams` / схема `MdeParams`):**

| Показатель | Параметр | Заменяет | По умолчанию |
|---|---|---|---|
| Доход | `revenue_cap` | `Revenue_cap` из диапазона `S_mrp` | пусто = авто по диапазону |
| Налоги | `taxes_threshold` | число 3 | `TAXES_THRESHOLD` |
| Налоги | `taxes_step` | число 0.1 | `TAXES_STEP` |
| Налоги | `taxes_factor` | число 0.5 | `TAXES_FACTOR` |
| Налоги | `taxes_cap` | предел 65% | `TAXES_CAP` |
| ФОТ | `payroll_threshold` | число 6.6 | `PAYROLL_THRESHOLD` |
| ФОТ | `payroll_step` | число 0.1 | `PAYROLL_STEP` |
| ФОТ | `payroll_factor` | число 0.1 | `PAYROLL_FACTOR` |
| ФОТ | `payroll_cap` | предел 100% | `PAYROLL_CAP` |

**Что пользователю НЕ отдаётся:** числа формулы дохода (50 / 0.1 / 0.05)
и знаменатели показателей — они всегда из `config.py`.

**Итоговый ПФУ на вкладке MDE не ограничивается.** `PFU_final = PFU_raw`,
то есть выводится посчитанная сумма трёх показателей как есть. Кап по
диапазону `S_mrp` (365 / 665 / 865) здесь не участвует, `pfu_cap_applied`
всегда `false`, а `pfu_cap` в ответе равен `null`. Это режим вкладки, а не
поле формы: за него отвечает `CalcParams.apply_pfu_cap`, и эндпоинт
`/calculate-mde` передаёт `False`. Индивидуальные капы показателей (доход,
налоги, ФОТ) при этом продолжают работать в обычном режиме.

**Правила:**
- `revenue_cap = null` (пустое поле) → кап определяется автоматически по
  диапазону `S_mrp`, как в обычном калькуляторе. Заданное число вытесняет
  диапазоны полностью.
- `taxes_step` и `payroll_step` строго `> 0`: они стоят в знаменателе.
  Ноль отсекается схемой (422) и `ParamsValidationError` в ядре.
- Остальные параметры принимают любое число; капы — неотрицательные.
- Незаполненное поле = значение по умолчанию из `config.py`.
- Результат расчёта дополнительно содержит фактически применённые капы
  (`revenue_cap`, `taxes_cap`, `payroll_cap`, `pfu_cap`) — вкладка показывает
  их пользователю, а Excel-выгрузка печатает параметры в шапке.

---

### 7.3 Правила округления

- Все промежуточные вычисления: **полная точность float** (не округлять в процессе)
- Отображение пользователю: **2 знака после запятой**
- Округление: **стандартное математическое (half-up)**
- В экспорте Excel: **числовой формат с 2 знаками**, не текстовый

---

## 8. API ЭНДПОИНТЫ

> **Авторизация.** Доступ — по cookie-сессии (а не по токену). Роли: `admin`
> и `user`. Пользовательские эндпоинты требуют входа (любая роль), admin-эндпоинты
> — роль `admin`. Вход/выход: `GET/POST /login`, `GET /logout`. Страницы:
> `/` (калькулятор, обе роли), `/mde` (калькулятор MDE, обе роли),
> `/admin` (только admin). Не вошедший пользователь получает 401 на API
> и редирект на `/login` на страницах.

### `GET /companies`
Список всех компаний из кеша (строится из БД). Требует входа.

**Response:**
```json
[
  {"bin": "123456789012", "name": "ТОО Компания А"},
  ...
]
```

### `POST /calculate`
Расчёт ПФУ. Результат сохраняется в `calculations`.

**Request:**
```json
{
  "amount": 10000000000,
  "company_bins": ["123456789012", "987654321098"],
  "years": [2023, 2024]
}
```

`years` — необязательное поле: отсутствует, `null` или `[]` → расчёт по всем
годам из `config.YEARS` (обратная совместимость). Порядок нормализуется по
`YEARS`, дубликаты убираются, год вне `YEARS` → 422.

**Response:**
```json
{
  "calculation_id": 42,
  "years": [2023, 2024],
  "results": [
    {
      "bin": "123456789012",
      "name": "ТОО Компания А",
      "years_used": [2023, 2024],
      "warnings": [],
      "revenue_percent": 125.50,
      "revenue_indicator": 377.50,
      "revenue_cap_applied": false,
      "taxes_percent": 8.30,
      "taxes_indicator": 26.50,
      "taxes_cap_applied": false,
      "payroll_percent": 12.10,
      "payroll_indicator": 54.00,
      "payroll_cap_applied": false,
      "pfu_raw": 458.00,
      "pfu_final": 365.00,
      "pfu_cap_applied": true,
      "revenue_cap": 200.00,
      "taxes_cap": 65.00,
      "payroll_cap": 100.00,
      "pfu_cap": 365.00
    }
  ]
}
```

### `POST /calculate-mde`
Расчёт вкладки «Калькулятор MDE». Тело — как у `/calculate`, плюс объект
`params` с пользовательскими числами формул (раздел 7.4). Любое поле `params`
можно опустить — подставится значение из `config.py`; `revenue_cap: null`
означает «кап по диапазону суммы».

**Request:**
```json
{
  "amount": 10000000000,
  "company_bins": ["123456789012"],
  "years": [2023, 2024],
  "params": {
    "revenue_cap": 150,
    "taxes_threshold": 4, "taxes_step": 0.2, "taxes_factor": 0.25, "taxes_cap": 50,
    "payroll_threshold": 10, "payroll_step": 0.5, "payroll_factor": 0.2, "payroll_cap": 80
  }
}
```

**Response:** как у `/calculate`, плюс поле `params` с применёнными значениями.
Отличие в итоговом ПФУ: кап не применяется, поэтому `pfu_final` = `pfu_raw`,
`pfu_cap_applied` = `false`, `pfu_cap` = `null` (раздел 7.4).
`taxes_step` или `payroll_step` равные нулю → 422 (стоят в знаменателе).

### `GET /history`
Последние 20 расчётов из таблицы `calculations` (JSON), включая `years` —
годы расчёта, `kind` (`"pfu"` / `"mde"`) и `params` (только у MDE).
Query-параметр `kind` фильтрует историю по вкладке: страница калькулятора
запрашивает `/history?kind=pfu`, страница MDE — `/history?kind=mde`.
Недопустимое значение `kind` → 400. Требует входа.
Примечание: путь `/history` занят этим JSON-эндпоинтом, поэтому история
отображается секцией на странице калькулятора, а не отдельной страницей.

### `GET /export/{calculation_id}`
Excel-файл с результатами расчёта по `calculation_id`. Требует входа.

### `POST /admin/import-excel-upload` (admin)
**Основной способ импорта.** Принимает загруженный через браузер Excel-файл
(multipart, поле `file`), валидирует, **upsert по БИН** (добавляет новые,
обновляет существующие, не удаляет старые), пересобирает кеш.

### `POST /admin/import-excel` (admin)
Импорт из файла на диске сервера (`data/import/companies.xlsx`). Используется
для локального авто-импорта при старте; на деплое данных на диске нет.

**Response (оба импорта):**
```json
{
  "imported": 46,
  "added": 3,
  "updated": 43,
  "warnings": ["Строка 12: отсутствует ФОТ 2022"],
  "errors": []
}
```

### `GET /admin/companies` (admin)
Полный список компаний со всеми показателями (для таблицы администрирования).

### `POST /admin/companies` (admin)
Добавить одну компанию вручную через форму (без Excel).

### `PUT /admin/companies/{bin}` (admin)
Обновить данные одной компании (БИН не меняется).

---

## 9. ПОРЯДОК ЗАПУСКА ПРОЕКТА

### Первый запуск (с нуля)
```bash
# 1. Установить зависимости
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Настроить окружение
cp .env.example .env
# отредактировать .env (SECRET_KEY, учётные записи)

# 3. Запустить сервер (БД и таблицы создаются автоматически при старте)
uvicorn app.main:app --reload --port 8000

# 4. Открыть http://localhost:8000 → вход под админом
#    Данные: «Администрирование» → «Импорт из Excel» → выбрать .xlsx → загрузить.
#    Локально: если файл лежит в data/import/companies.xlsx, он подхватится
#    автоматически при старте на пустой базе (авто-импорт).
```

### При обновлении данных (новый Excel)
Войти как админ → «Администрирование» → блок «Импорт из Excel» → загрузить новый
файл. Это upsert по БИН: обновит существующие и добавит новые компании,
ничего не удаляя. Старый способ (файл на диске + `POST /admin/import-excel`)
остаётся для локальной разработки.

---

## 10. ОБРАБОТКА ОШИБОК

| Ситуация | Поведение |
|---|---|
| `S <= 0` | Валидация на фронте + 422 от API |
| `S_mrp < 800 000` | Расчёт выполняется (порог снят); `Revenue_cap = 100%` |
| Компания не найдена по БИН | 400 с перечнем не найденных БИН |
| `Revenue_sum = 0` | Taxes_indicator = 0 и Payroll_indicator = 0, предупреждения в results |
| `PFU_raw > PFU_cap` на вкладке MDE | Кап не применяется: `PFU_final = PFU_raw` |
| Нет данных ни за один выбранный год | Компания исключается, error в её блоке results |
| Год вне `config.YEARS` | 422 с перечнем недопустимых годов |
| Не выбрано ни одного года на UI | Валидация на фронте; пустой список от API = все годы |
| БД недоступна | 500 + «Обратитесь к администратору» |
| Excel не найден / неверный формат при импорте | 400 + описание ошибки (admin) |
| Не авторизован | 401 на API, редирект на `/login` на страницах |
| Недостаточно прав (не admin) | 403 на API, редирект на `/` на странице `/admin` |
| Любая неожиданная ошибка | 500 + «Произошла ошибка. Обратитесь к администратору» (полный traceback только в лог) |

---

## 11. FRONTEND

### Страница входа (`/login`)
- Логин/пароль, две роли (admin/user). После входа — редирект на `/` (user)
  или `/admin` (admin). В шапке — имя пользователя, роль и «Выйти».

### Страница калькулятора (`/`, обе роли)
- Поле ввода суммы в тенге (числовое, только положительные)
- Tom Select мультиселект с поиском по названию и БИН
- **Годы расчёта** — чипы-переключатели (`.chip-year`), по одному на год из
  `config.YEARS`; по умолчанию выбраны все. Можно выбрать один или несколько,
  кнопка «Выбрать все» возвращает полный набор. Список приходит в шаблон из
  `config.YEARS` — в HTML годы не хардкодятся.
- Кнопка «Рассчитать ПФУ»
- Блок результатов: карточка на каждую компанию:
  - Название и БИН
  - Годы, по которым фактически посчитано (`years_used`)
  - Предупреждения (если есть) — жёлтый блок
  - Промежуточные показатели: Revenue / Taxes / Payroll (процент и индикатор)
  - Пометка «применено ограничение» если `*_cap_applied = true`
  - Итоговый ПФУ — крупно, выделить цветом
- Кнопка «Экспорт в Excel»
- Секция «История расчётов» (таблица: дата/время, сумма, годы, число компаний, экспорт)

### Страница «Калькулятор MDE» (`/mde`, обе роли)
- Те же поля, что на калькуляторе: сумма, мультиселект компаний, чипы годов
- Блок «Параметры расчёта» — три группы (Доход / Налоги / ФОТ) с полями
  порога, шага, коэффициента и ограничения. Поля предзаполнены значениями из
  `config.py` (передаются в шаблон, в HTML не хардкодятся). Кап дохода пустой
  по умолчанию — подсказка показывает, какой кап подставится автоматически
  для введённой суммы.
- Кнопка «Сбросить к значениям по умолчанию»
- Под каждой формулой — её текстовая запись, чтобы было видно, куда встаёт
  каждое число
- Результаты — как на калькуляторе, плюс блок «Применённые параметры» и
  показ фактического капа в каждой карточке показателя
- В плашке итогового ПФУ вместо «До ограничения» — пометка «Сумма показателей
  без ограничения»: кап итогового ПФУ на этой вкладке не применяется
- Секция «История расчётов MDE» с кнопкой «Подставить» — возвращает параметры
  прошлого расчёта в форму

### Страница администрирования (`/admin`, только admin)
- Импорт из Excel: **загрузка файла через браузер** (multipart)
- Добавление компании вручную (форма)
- Таблица компаний с поиском и кнопкой «Изменить» (редактирование)

### Стиль — BI Group
- Основной цвет: `#0060FE`
- Фон: белый `#FFFFFF`
- Шрифт: Inter (Google Fonts) → fallback system sans-serif
- Кнопки: `#0060FE`, белый текст, border-radius 8px
- Карточки: белый фон, border 1px #E0E0E0, box-shadow лёгкая
- Предупреждения: фон `#FFF8E1`, граница `#FFC107`
- Ошибки: фон `#FFEBEE`, граница `#F44336`
- Успех/ПФУ: `#0060FE` крупный текст

---

## 12. ТЕСТЫ (ОБЯЗАТЕЛЬНЫ ДО НАПИСАНИЯ UI)

### `tests/test_calculator.py`
```
test_basic_calculation()           # эталонный расчёт с известным результатом
test_revenue_cap_200()             # S в диапазоне [800k;1.6m] МРП → кап 200%
test_revenue_cap_500()             # S в диапазоне (1.6m;3.2m] МРП → кап 500%
test_revenue_cap_700()             # S > 3.2m МРП → кап 700%
test_revenue_cap_not_applied()     # Revenue_indicator < cap → фактическое
test_taxes_cap_65()                # Taxes_indicator ограничен 65%
test_payroll_cap_100()             # Payroll_indicator ограничен 100%
test_pfu_cap_365()                 # PFU_final ограничен 365%
test_pfu_cap_665()                 # PFU_final ограничен 665%
test_pfu_cap_865()                 # PFU_final ограничен 865%
test_negative_indicators()         # отрицательные значения не обнуляются
test_revenue_sum_zero()            # Revenue_sum = 0 → Taxes_indicator = 0
test_missing_one_year()            # один год NULL → warning, считает по двум
test_all_years_missing()           # все годы NULL → ошибка по компании
test_amount_must_be_positive()     # S <= 0 → ошибка валидации
test_s_below_800k_mrp_allowed()    # S_mrp < 800 000 → расчёт выполняется
test_revenue_cap_below_800k_is_100()    # ниже 800 000 МРП → Revenue_cap 100%
test_boundary_1_600_000()          # ровно 1 600 000 МРП → кап 200%, не 500%
test_boundary_3_200_000()          # ровно 3 200 000 МРП → кап 500%, не 700%

# Показатель ФОТ считается от Revenue_sum
test_payroll_percent_uses_revenue_sum()        # ФОТ % = ФОТ / Доходы * 100
test_payroll_percent_independent_of_amount()   # сумма S на процент ФОТ не влияет
test_payroll_zero_when_revenue_sum_zero()      # Revenue_sum = 0 → индикатор 0 + warning

# Пользовательские параметры формул (вкладка MDE)
test_params_default_to_config()          # без params = CalcParams() по умолчанию
test_custom_revenue_cap_overrides_tier() # ручной кап дохода вытесняет диапазон
test_custom_revenue_cap_can_exceed_tier()# кап может быть выше автоматического
test_custom_taxes_params()               # порог/шаг/коэффициент/кап налогов
test_custom_taxes_cap_applies()          # пользовательский кап налогов ограничивает
test_custom_payroll_params()             # порог/шаг/коэффициент/кап ФОТ
test_custom_payroll_cap_applies()        # пользовательский кап ФОТ ограничивает
test_zero_step_rejected()                # шаг = 0 → ParamsValidationError

# Кап итогового ПФУ отключается на вкладке MDE
test_pfu_cap_skipped_when_disabled()        # apply_pfu_cap=False → PFU_final = PFU_raw
test_pfu_cap_applied_when_enabled()         # те же данные с капом → 365%
test_indicator_caps_still_apply_without_pfu_cap()  # капы показателей работают
test_default_params_keep_pfu_cap()          # обычный калькулятор кап сохраняет

# Выбор годов расчёта
test_normalize_years_defaults_to_all()   # None / [] → все годы из YEARS
test_normalize_years_sorts_and_dedupes() # порядок по YEARS, без дубликатов
test_normalize_years_rejects_unknown()   # год вне YEARS → YearsValidationError
test_selected_years_limit_sums()         # суммы только по выбранным годам
test_single_year_selection()             # можно выбрать ровно один год
test_selected_year_without_data_warns()  # выбранный год без данных → warning
test_no_data_for_selected_years()        # нет данных по всем Y → error по компании
test_unknown_year_rejected_in_calculate()# недопустимый год отсекается в calculate_pfu
```

### `tests/test_api.py` (по выбору годов)
```
test_calculate_with_selected_years()   # years в запросе → в ответе и в истории
test_calculate_rejects_unknown_year()  # год вне YEARS → 422
test_calculate_empty_years_means_all() # [] → расчёт по всем годам
test_calculate_below_800k_mrp_succeeds() # сумма ниже 800 000 МРП → 200, не 400

# Вкладка «Калькулятор MDE»
test_calculate_mde_applies_params()             # введённые числа встают в формулы
test_calculate_mde_without_params_matches_plain()# без params = обычный расчёт
test_calculate_mde_empty_revenue_cap_is_auto()  # revenue_cap null → авто по диапазону
test_calculate_mde_rejects_zero_step()          # шаг = 0 → 422
test_history_separates_tabs()                   # /history?kind= разделяет вкладки
test_history_rejects_unknown_kind()             # неизвестный kind → 400
test_export_mde_includes_params()               # параметры печатаются в шапке xlsx
test_calculate_mde_does_not_cap_final_pfu()     # итоговый ПФУ без ограничения
test_export_mde_notes_uncapped_pfu()            # пометка об этом в шапке xlsx
```

---

## 13. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (`.env`)

```
# База данных (локально SQLite; на Render — PostgreSQL через DATABASE_URL)
DATABASE_URL=sqlite+aiosqlite:///./pfu.db
LOG_LEVEL=INFO
# PORT задаёт платформа (Render); локально по умолчанию 8000

# Авторизация
SECRET_KEY=change-me-to-a-long-random-string
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin
USER_USERNAME=user
USER_PASSWORD=user
```

> Python закреплён на 3.11 (`.python-version` = `3.11.0`, `runtime.txt` =
> `python-3.11.0`). `pydantic-core==2.27.2` ставится на 3.11 из готового wheel.

---

## 14. ЧТО НЕЛЬЗЯ МЕНЯТЬ БЕЗ ЯВНОГО СОГЛАСОВАНИЯ

1. Формулы расчёта показателей (раздел 7)
2. Пороговые значения и капы в `config.py`
3. Значение МРП (4325) без подтверждения актуальности
4. Структуру JSON-ответа `/calculate` (сломает экспорт). Добавлять
   необязательные поля можно — удалять и переименовывать существующие нельзя
5. Схему таблицы `companies` без миграции
6. Список параметров, которые вкладка MDE отдаёт пользователю (раздел 7.4):
   числа формулы дохода и знаменатели показателей пользователь задавать
   не должен
7. Режим `apply_pfu_cap`: обычный калькулятор всегда применяет кап итогового
   ПФУ, вкладка MDE — никогда

---

## 15. СОГЛАШЕНИЯ ПО КОДУ

- Язык кода: **английский** (переменные, функции, классы)
- Язык комментариев: **русский** (бизнес-логика) / английский (технические)
- Форматирование: **black** + **isort**
- Type hints: обязательны везде
- Логирование: стандартный `logging`, уровни INFO/WARNING/ERROR
- Никаких `print()` в production-коде

---

*Последнее обновление: 2026-09 (вкладка «Калькулятор MDE»: ручной ввод
параметров формул и итоговый ПФУ без ограничения; показатель ФОТ считается
от Revenue_sum, а не от суммы S — изменение затрагивает ОБЕ вкладки;
колонки kind/params в calculations).
Ранее: снят минимальный порог суммы 800 000 МРП и добавлен нижний уровень
Revenue_cap = 100%; 2025 год и выбор годов расчёта; авто-миграция колонок;
фикс prepared statements asyncpg через pgbouncer; авторизация с ролями,
загрузка Excel через браузер, поддержка PostgreSQL/asyncpg, деплой на Render.*  
*Владелец: Aidyn (администратор системы)*
