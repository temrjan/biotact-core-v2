# HR Gifts & Events — Phase 2 Roadmap

> **Дата анализа:** 2026-06-10
> **Источник требований:** `doc_content.txt` (реестр подарков BIOTACT DEUTSCHLAND)
> **База:** `biotact-core-v2/main` на коммите `e088c15` (PR-2a Gifts+Events API)

---

## 1. Что уже реализовано (09.06.2026)

### 1.1 Модели БД (миграция `k9l0m1n2o345`)

| Таблица | Назначение | Статус |
|---|---|---|
| `hr_events` | Календарь событий (date, employee_name, department, occasion_type, notes) | ✅ |
| `hr_gift_requests` | Заявки на подарки — все поля из doc_content.txt | ✅ |
| `hr_gift_status_history` | Аудит переходов статусов (append-only) | ✅ |
| `hr_gift_budget_plans` | План бюджета по месяцам (month, year, planned_amount) | ✅ **Schema only** |

### 1.2 API Endpoints

**Gifts (`/api/v1/hr/gifts`):**
- `GET /` — список с фильтрами (status, month/year, responsible) + пагинация
- `POST /` — создание заявки
- `GET /{id}` — детали
- `PATCH /{id}` — частичное обновление
- `PATCH /{id}/status` — смена статуса с `SELECT FOR UPDATE` + аудит
- `DELETE /{id}` — удаление
- `GET /{id}/history` — история статусов

**Events (`/api/v1/hr/events`):**
- `GET /` — список с фильтрами (month/year, department) + пагинация
- `POST /` — создание события
- `GET /{id}` — детали
- `DELETE /{id}` — удаление (SET NULL на связанные gifts)

### 1.3 Статусная модель (соответствие doc_content.txt)

| Код в БД | Название из документа |
|---|---|
| `new` | Новая заявка |
| `approval` | На согласовании |
| `purchase` | Закупка |
| `packaging` | Упаковка |
| `ready` | Готово к вручению |
| `done` | Вручено |
| `cancelled` | Отменено |

### 1.4 Тесты

- `tests/unit/hr/test_gifts_api.py` — 13 тестов (CRUD, статусы, фильтры, история, связь с event)
- `tests/unit/hr/test_events_api.py` — 8 тестов (CRUD, фильтры, SET NULL на удалении)
- `tests/unit/hr/test_gifts_models.py` — модельные тесты
- `tests/unit/hr/test_migration_gifts.py` — тест миграции
- **Skip на SQLite** — требуется PostgreSQL (ENUM типы)

### 1.5 Auth

- Все endpoint'ы под `RequireHREmailDep` (RBAC через `HR_ALLOWED_EMAILS`)

---

## 2. Что НЕ реализовано (GAP analysis)

### 2.1 🔴 Budget Plan API — полностью отсутствует

Модель `GiftBudgetPlan` создана в миграции, но нет:
- Схем (Pydantic)
- Сервиса (CRUD)
- Роутера (endpoint'ов)
- Тестов

**Блокирует:** отчётность (нельзя сравнить план vs факт).

### 2.2 🔴 Отчётность (Report endpoint) — полностью отсутствует

Нужен эндпоинт `/api/v1/hr/gifts/report` с агрегацией.

**Must-fix спецификация:**
- **Якорь:** `created_at` (не `presentation_date` — она nullable, in-flight заявки потеряются)
- **Исключить `cancelled`:** из SUM/COUNT/AVG
- **"Кол-во мероприятий"** = заявки (`hr_gift_requests`), не `hr_events`

| Поле | Источник |
|---|---|
| Месяц | `month/year` параметры (по `created_at`) |
| Кол-во мероприятий | `COUNT(*) FROM hr_gift_requests WHERE status != 'cancelled'` |
| План бюджета | `hr_gift_budget_plans.planned_amount` |
| Факт бюджета | `SUM(budget) FROM hr_gift_requests WHERE status != 'cancelled'` |
| Экономия/Перерасход | `planned - SUM(budget)` |
| Средний чек | `SUM(budget) / COUNT(*)` (только не-cancelled) |

### 2.3 🔴 KPI — полностью отсутствует

Из doc_content.txt (Table 2):

| Показатель | План | Факт | % выполнения |
|---|---|---|---|
| Поздравления сотрудников в срок | — | — | — |
| Поздравления партнеров в срок | — | — | — |
| Соблюдение бюджета | — | — | — |
| Удовлетворенность сотрудников | — | — | — |
| Своевременное закрытие заявок | — | — | — |

**Must-fix спецификация:**
- KPI-модель: **planned + actual на показатель** (не одно число) — иначе не ложится на Table 2
- Ручной ввод HR (не авторасчёт — `satisfaction_score` требует опроса, "в срок" требует ручной проверки)
- Модель:
  ```python
  class GiftKPI(Base):
      month: int
      year: int
      employee_congrats_planned: int
      employee_congrats_actual: int
      partner_congrats_planned: int
      partner_congrats_actual: int
      budget_compliance_planned: int   # обычно 100%
      budget_compliance_actual: int
      satisfaction_planned: int
      satisfaction_actual: int
      timely_closure_planned: int
      timely_closure_actual: int
      notes: str | None
      created_by: int
  ```
- `% выполнения` = `actual / planned * 100` (computed в response)

### 2.4 🟡 Events — нет UPDATE

Можно создать и удалить событие, но нельзя отредактировать (`PATCH /hr/events/{id}`).

### 2.5 🟡 AI-интеграция — не подключена

HR Chat (`chat/service.py`) не имеет tools для работы с gifts/events:
- Нет `create_gift_request`
- Нет `list_upcoming_events`
- Нет `get_gift_status`

**Note:** доспецифицировать `user_id` — AI-tools должны передавать `created_by=current_user.id`.

### 2.6 🟡 Фронтенд — out-of-scope

Kanban-доска по статусам, календарь событий, форма KPI — требуют frontend. В плане backend — только API.

---

## 3. План реализации (Phase 2)

### PR-1 · Budget Plan CRUD (`hr/p2-gifts-budget`) — ✅ ЧИСТ, МОЖНО СТАРТОВАТЬ

**Scope:**
1. `gifts/schemas.py` — добавить `BudgetPlanCreate/Update/Response`
2. `gifts/service.py` — `create_budget_plan`, `get_budget_plan`, `update_budget_plan`, `delete_budget_plan`
3. `gifts/router.py` — `POST/GET/PATCH/DELETE /hr/gifts/budgets`
4. Unique constraint `month+year` — уже в миграции
5. Тесты: CRUD + попытка создать дубль month/year → 409

**Acceptance:**
- `POST /hr/gifts/budgets` — создаёт план
- `GET /hr/gifts/budgets?month=6&year=2026` — возвращает план
- `PATCH /hr/gifts/budgets/{id}` — обновляет planned_amount
- Дубль month/year → 409 Conflict

---

### PR-2 · Report endpoint (`hr/p2-gifts-report`)

**Scope:**
1. Новый `gifts/report.py` (или в `service.py`) — SQL-агрегация:
   ```sql
   SELECT
     COUNT(*) as total_requests,
     COALESCE(SUM(budget), 0) as actual_budget,
     COALESCE(AVG(budget), 0) as avg_check
   FROM hr_gift_requests
   WHERE created_at >= :month_start
     AND created_at < :month_end
     AND status != 'cancelled'
   ```
2. LEFT JOIN с `hr_gift_budget_plans` для `planned_amount`
3. `GET /hr/gifts/report?month=6&year=2026`
4. Response schema: `GiftReportResponse`

**Acceptance:**
- Сводка за месяц: кол-во (без cancelled), план, факт, дельта, средний чек
- Если плана нет → `planned_amount = 0`, `delta = -actual`
- Пустой месяц → `total=0, actual=0, avg=0`
- `cancelled` заявки не попадают в агрегацию

---

### PR-3 · Events PATCH (`hr/p2-gifts-events-patch`) — МЕЛКИЙ

**Scope:**
1. `events/schemas.py` — `EventUpdateRequest` (все поля optional)
2. `events/service.py` — `update_event`
3. `events/router.py` — `PATCH /hr/events/{id}`
4. Тест: обновление полей + 404

**Acceptance:**
- Events можно редактировать частично

---

### PR-4 · KPI CRUD (`hr/p2-gifts-kpi`)

**Scope:**
1. **Миграция:** новая таблица `hr_gift_kpi`
   ```sql
   CREATE TABLE hr_gift_kpi (
     id SERIAL PRIMARY KEY,
     month INT NOT NULL,
     year INT NOT NULL,
     employee_congrats_planned INT DEFAULT 0,
     employee_congrats_actual INT DEFAULT 0,
     partner_congrats_planned INT DEFAULT 0,
     partner_congrats_actual INT DEFAULT 0,
     budget_compliance_planned INT DEFAULT 100,
     budget_compliance_actual INT DEFAULT 0,
     satisfaction_planned INT DEFAULT 0,
     satisfaction_actual INT DEFAULT 0,
     timely_closure_planned INT DEFAULT 0,
     timely_closure_actual INT DEFAULT 0,
     notes TEXT,
     created_by INT REFERENCES users(id) ON DELETE CASCADE,
     created_at TIMESTAMPTZ DEFAULT now(),
     updated_at TIMESTAMPTZ DEFAULT now(),
     UNIQUE(month, year)
   );
   ```
2. **Schemas:** `KPICreate/Update/Response` с `computed_completion_pct`:
   ```python
   @computed_field
   @property
   def employee_congrats_pct(self) -> int:
       if self.employee_congrats_planned == 0:
           return 0
       return int(self.employee_congrats_actual / self.employee_congrats_planned * 100)
   ```
3. **Service + Router:** CRUD `POST/GET/PATCH /hr/gifts/kpi`
4. **Тесты:** CRUD + unique month/year + computed fields

**Acceptance:**
- `GET /hr/gifts/kpi?month=6&year=2026` → возвращает KPI с `% выполнения`
- `PATCH` обновляет planned/actual для любого показателя
- Дубль month/year → 409

---

### PR-5 · AI Tools integration (`hr/p2-gifts-ai-tools`)

**Scope:**
Добавить в `chat/prompts.py` OpenAI tools:
1. `create_gift_request` — AI создаёт заявку из диалога (передаёт `created_by=current_user.id`)
2. `list_upcoming_events` — AI показывает ближайшие события
3. `get_gift_status` — AI проверяет статус заявки

**Acceptance:**
- В чате: "Оксана выходит замуж 15 июня" → AI создаёт gift request + event
- "Какие подарки в работе?" → AI вызывает `list_gifts` → отвечает

---

### PR-6 · Полировка (`hr/p2-gifts-polish`)

**Scope:**
1. Интеграционные тесты на Report + Budget Plan + KPI
2. Убрать избыточный индекс (если есть — проверить `EXPLAIN` на report query)
3. Проверка `budget >= 0` в schema (уже есть `ge=0`)
4. Пагинация на историю статусов (уже есть page/size)

---

## 4. Открытые вопросы (все закрыты)

| # | Вопрос | Решение |
|---|---|---|
| 1 | **KPI — ручной ввод или авторасчёт?** | Ручной ввод planned+actual. `% выполнения` computed. |
| 2 | **Кто создаёт budget plan?** | Любой HR из `HR_ALLOWED_EMAILS` (текущий `RequireHREmailDep`). |
| 3 | **Report — по presentation_date или created_at?** | `created_at` (presentation_date nullable). |
| 4 | **AI-tools — нужны сейчас или later?** | PR-5, можно отложить. |
| 5 | **Frontend — кто делает и когда?** | Отдельно, backend готовит API. |

---

## 5. Сводка

| Компонент | Статус | Осталось |
|---|---|---|
| БД Schema | ✅ Готово | + миграция KPI в PR-4 |
| Gifts CRUD + статусы | ✅ Готово | — |
| Events CRUD | ✅ 90% | PR-3: PATCH |
| Budget Plan CRUD | ❌ Нет | PR-1 (чист, можно стартовать) |
| Report (план/факт) | ❌ Нет | PR-2 |
| KPI (planned+actual) | ❌ Нет | PR-4 |
| AI-интеграция | ❌ Нет | PR-5 (опционально) |
| Тесты | ✅ Unit | + Integration на новые фичи |

**Рекомендуемый порядок:** PR-1 → PR-2 → PR-3 → PR-4 → PR-6 → PR-5 (AI опционально)
