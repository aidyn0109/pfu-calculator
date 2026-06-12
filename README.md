# Калькулятор ПФУ (Показатель финансовой устойчивости)

Веб-калькулятор для расчёта Показателя финансовой устойчивости компаний.
Источник истины по бизнес-логике — [CLAUDE.md](CLAUDE.md).

## Стек
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + aiosqlite, pandas/openpyxl
- Frontend: Jinja2 + Alpine.js + Tom Select (CDN, без сборки)
- Деплой: Docker + docker-compose + Nginx

## Структура
```
app/
  config.py          # все константы (МРП, капы, пороги)
  main.py            # точка входа FastAPI
  dependencies.py    # сессия БД, кеш, admin-токен
  api/               # routes.py, schemas.py
  core/calculator.py # бизнес-логика расчёта ПФУ (чистые функции)
  db/                # database, models (ORM), companies, calculations
  data/              # importer (Excel→БД), cache (in-memory), exporter (→Excel)
  models/company.py  # доменная модель CompanyData
  templates/         # base.html, index.html
tests/               # test_calculator.py — все формулы покрыты
```

## Локальный запуск
```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env         # задать SECRET_KEY и учётные записи

uvicorn app.main:app --reload --port 8000
```

Открыть http://localhost:8000 → вход → раздел «Администрирование» → **Импорт из Excel**
→ выбрать файл `.xlsx` → **Загрузить и импортировать**.

> Для локальной разработки: если положить файл в `data/import/companies.xlsx`,
> он подхватится автоматически при первом старте на пустой базе (авто-импорт).
> На деплое данные загружаются только через страницу администрирования.

## Тесты
```bash
pytest
```

## Авторизация и роли
Вход по логину/паролю (cookie-сессия). Две роли, учётки задаются в `.env`:
- **admin** — полный доступ, включая раздел «Администрирование».
- **user** — только калькулятор.

Переменные: `ADMIN_USERNAME`/`ADMIN_PASSWORD`, `USER_USERNAME`/`USER_PASSWORD`,
`SECRET_KEY` (ключ подписи сессии). Значения по умолчанию — в `.env.example`.

## Страницы
- `/login` — вход.
- `/` — калькулятор (обе роли).
- `/admin` — администрирование (только admin): **загрузка Excel через браузер**,
  добавление и редактирование компаний. Токены не нужны — доступ по роли.

## Эндпоинты
| Метод | Путь | Назначение |
|---|---|---|
| GET  | `/companies` | список компаний из кеша |
| POST | `/calculate` | расчёт ПФУ, сохранение в историю |
| GET  | `/history` | последние 20 расчётов (JSON) |
| GET  | `/export/{id}` | Excel с результатами расчёта |
| POST | `/admin/import-excel-upload` | импорт загруженного Excel-файла (admin) |
| POST | `/admin/import-excel` | импорт Excel с диска сервера (admin, для локалки) |
| GET  | `/admin/companies` | полный список компаний (admin) |
| POST | `/admin/companies` | добавить компанию вручную (admin) |
| PUT  | `/admin/companies/{bin}` | обновить компанию (admin) |
| GET  | `/` | страница калькулятора |
| GET  | `/admin` | страница администрирования |

## Формат Excel импорта
Колонки (сверены с фактическим файлом):
`БИН ТОО`, `Наименование ТОО`, `Доходы 2022/2023/2024`,
`Уплаченные налоги 2022/2023/2024`, `ФОТ 2022/2023/2024`.
БИН нормализуется до 12 цифр (ведущие нули восстанавливаются).
