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
    taxes_2022      REAL,
    taxes_2023      REAL,
    taxes_2024      REAL,
    payroll_2022    REAL,
    payroll_2023    REAL,
    payroll_2024    REAL,
    imported_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

- NULL в колонках года = данные отсутствуют (не 0)
- При импорте из Excel: **upsert по БИН** (INSERT OR REPLACE). Новые компании добавляются, существующие обновляются, удалённых из Excel компаний в БД не трогаем.

### Таблица `calculations`

```sql
CREATE TABLE calculations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    amount          REAL NOT NULL,
    amount_mrp      REAL NOT NULL,
    company_bins    TEXT NOT NULL,  -- JSON array
    results         TEXT NOT NULL,  -- JSON array результатов
    companies_count INTEGER NOT NULL
);
```

- Хранить последние 1000 записей (при превышении — удалять старые)

---

## 6. КОНФИГУРАЦИЯ (`app/config.py`)

**Все константы — только здесь. Никогда не хардкодить в формулах.**

```python
# Константы МРП
MRP = 4_325  # тенге, актуальное значение на 2024 год

# Диапазоны суммы в МРП и соответствующие капы для Revenue_indicator
REVENUE_CAPS = [
    (800_000,   1_600_000, 200.0),
    (1_600_000, 3_200_000, 500.0),
]
REVENUE_CAP_ABOVE_MAX = 700.0

# Капы для индивидуальных показателей
TAXES_CAP   = 65.0   # %
PAYROLL_CAP = 100.0  # %

# Диапазоны и капы для итогового ПФУ
PFU_CAPS = [
    (800_000,   1_600_000, 365.0),
    (1_600_000, 3_200_000, 665.0),
]
PFU_CAP_ABOVE_MAX = 865.0

# Минимальная сумма S в МРП
S_MRP_MIN = 800_000

# Пороговые значения формул
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
    "revenue": ["Доходы 2022", "Доходы 2023", "Доходы 2024"],
    "taxes":   ["Уплаченные налоги 2022", "Уплаченные налоги 2023", "Уплаченные налоги 2024"],
    "payroll": ["ФОТ 2022", "ФОТ 2023", "ФОТ 2024"],
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
| `Revenue_sum` | Сумма доходов за 2022–2024 |
| `Taxes_sum` | Сумма уплаченных налогов за 2022–2024 |
| `Payroll_sum` | Сумма ФОТ за 2022–2024 |
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
Если S_mrp < 800000 → ошибка: "Сумма ниже минимального порога (800 000 МРП)"
```

#### Шаг 1 — Перевод суммы в МРП
```
S_mrp = S / 4325
```

#### Шаг 2 — Суммирование по годам
```
Revenue_sum = Revenue_2022 + Revenue_2023 + Revenue_2024
Taxes_sum   = Taxes_2022   + Taxes_2023   + Taxes_2024
Payroll_sum = Payroll_2022 + Payroll_2023 + Payroll_2024
```

**Правило для отсутствующих данных (NULL в БД):**
- NULL за год → считать как 0, суммировать по имеющимся
- Добавить в `warnings`: `"Отсутствуют данные за [год(ы)]. Расчёт выполнен по: [список лет]."`
- Если все 3 года NULL → исключить компанию, вернуть ошибку по ней

#### Шаг 3 — Показатель дохода
```
Revenue_percent   = (Revenue_sum / S) * 100
Revenue_indicator = ((Revenue_percent - 50) / 0.1) * 0.05
Revenue_indicator = min(Revenue_indicator, Revenue_cap)
```

Определение `Revenue_cap` по `S_mrp`:
```
800 000 ≤ S_mrp ≤ 1 600 000  → Revenue_cap = 200%
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
Payroll_percent   = (Payroll_sum / S) * 100
Payroll_indicator = ((Payroll_percent - 6.6) / 0.1) * 0.1
Payroll_indicator = min(Payroll_indicator, 100%)
```

> Отрицательный `Payroll_indicator` допустим — не обнулять.

#### Шаг 6 — Итоговый ПФУ
```
PFU_raw   = Revenue_indicator + Taxes_indicator + Payroll_indicator
PFU_final = min(PFU_raw, PFU_cap)
```

Определение `PFU_cap` по `S_mrp`:
```
800 000 ≤ S_mrp ≤ 1 600 000  → PFU_cap = 365%
1 600 000 < S_mrp ≤ 3 200 000 → PFU_cap = 665%
S_mrp > 3 200 000             → PFU_cap = 865%
```

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
> `/` (калькулятор, обе роли), `/admin` (только admin). Не вошедший пользователь
> получает 401 на API и редирект на `/login` на страницах.

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
  "company_bins": ["123456789012", "987654321098"]
}
```

**Response:**
```json
{
  "calculation_id": 42,
  "results": [
    {
      "bin": "123456789012",
      "name": "ТОО Компания А",
      "years_used": [2022, 2023, 2024],
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
      "pfu_cap_applied": true
    }
  ]
}
```

### `GET /history`
Последние 20 расчётов из таблицы `calculations` (JSON). Требует входа.
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
| `S_mrp < 800 000` | 400 с сообщением пользователю |
| Компания не найдена по БИН | 400 с перечнем не найденных БИН |
| `Revenue_sum = 0` | Taxes_indicator = 0, предупреждение в results |
| Все 3 года NULL у компании | Компания исключается, error в её блоке results |
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
- Кнопка «Рассчитать ПФУ»
- Блок результатов: карточка на каждую компанию:
  - Название и БИН
  - Предупреждения (если есть) — жёлтый блок
  - Промежуточные показатели: Revenue / Taxes / Payroll (процент и индикатор)
  - Пометка «применено ограничение» если `*_cap_applied = true`
  - Итоговый ПФУ — крупно, выделить цветом
- Кнопка «Экспорт в Excel»
- Секция «История расчётов» (таблица: дата/время, сумма, число компаний, экспорт)

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
test_s_below_minimum()             # S_mrp < 800 000 → ошибка валидации
test_boundary_1_600_000()          # ровно 1 600 000 МРП → кап 200%, не 500%
test_boundary_3_200_000()          # ровно 3 200 000 МРП → кап 500%, не 700%
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
4. Структуру JSON-ответа `/calculate` (сломает экспорт)
5. Схему таблицы `companies` без миграции

---

## 15. СОГЛАШЕНИЯ ПО КОДУ

- Язык кода: **английский** (переменные, функции, классы)
- Язык комментариев: **русский** (бизнес-логика) / английский (технические)
- Форматирование: **black** + **isort**
- Type hints: обязательны везде
- Логирование: стандартный `logging`, уровни INFO/WARNING/ERROR
- Никаких `print()` в production-коде

---

*Последнее обновление: 2026-06 (добавлены авторизация с ролями, загрузка Excel
через браузер, поддержка PostgreSQL/asyncpg, деплой на Render, фикс названий
столбцов Excel)*  
*Владелец: Aidyn (администратор системы)*
