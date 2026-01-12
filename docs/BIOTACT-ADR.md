# BIOTACT Core — Архитектурные решения (ADR)

> Документ для Claude Code. Содержит согласованные решения по архитектуре системы.

---

## Контекст проекта

**Цель:** AI-трансформация компании BIOTACT. Внедрение AI-инструментов во все структуры.

**Пользователи:**
- ~70 сотрудников всего
- ~30 будут пользоваться
- ~15 активных пользователей
- 2 администратора
- 2 руководителя (максимальное внимание)

**Тип системы:** Внутренний корпоративный инструмент, внешних пользователей нет.

---

## Q1: AI-паттерны по модулям

### Решение

| Модуль | Паттерн | Описание |
|--------|---------|----------|
| **Dashboard** | Command (LLM → SQL) | LLM парсит намерение → Function Call → PostgreSQL |
| **КолЦентр** | RAG | Поиск по базе знаний → генерация ответа |
| **Маркетинг** | RAG | Поиск по продуктам/компании → генерация контента |
| **HR** | RAG | Поиск по HR-базе (8 источников + 2 TG-канала) |
| **Аналитика** | TBD | Заглушка |
| **Продажи** | TBD | Заглушка |
| **Логистика** | TBD | Заглушка |
| **Склад** | TBD | Заглушка |

### Dashboard: Multi-turn Command Flow

Dashboard поддерживает уточняющие вопросы если данных недостаточно:

```
User: "Внеси расход на покупку компьютеров"
AI: "Какая сумма?"

User: "500 тысяч"
AI: "Записать в 'Техника и оборудование' или 'Офис'?"

User: "Техника"
AI: → Function Call → DB
AI: "Готово. Расход 500 000 сум — Техника и оборудование"
```

### Типы запросов Dashboard

| Запрос | Обработка |
|--------|-----------|
| "Расход 15 млн на серверы" | Command → INSERT в PostgreSQL |
| "Покажи расходы за январь" | LLM понимает вопрос → SQL SELECT → форматированный ответ |

---

## Q2: Frontend

### Решение

| Параметр | Значение |
|----------|----------|
| Фреймворк | React 18 |
| Стилизация | Tailwind CSS |
| Архитектура | FSD (Feature-Sliced Design) — минимальный |
| Исходник | `biotact-dashboard-v3.jsx` (прототип) |
| Разработчик | Claude Code по документации |

### FSD структура (минимальная)

```
src/
├── app/                    # Инициализация, провайдеры
│   ├── providers/
│   │   └── ThemeProvider.jsx
│   └── App.jsx
├── pages/                  # Страницы-роуты
│   └── DashboardPage.jsx
├── widgets/                # Композитные блоки
│   ├── Sidebar/
│   ├── ChatPanel/
│   └── FinanceCharts/
├── features/               # Бизнес-фичи
│   ├── add-transaction/
│   ├── generate-report/
│   └── theme-toggle/
├── entities/               # Бизнес-сущности
│   ├── transaction/
│   └── category/
└── shared/                 # Переиспользуемое
    ├── ui/
    ├── api/
    └── lib/
```

---

## Q3: Persistence

### Решение

| Параметр | Значение |
|----------|----------|
| База данных | PostgreSQL |
| Тип данных | Реальные (production) |
| UX | Multi-turn диалог с уточнениями |

### Схема транзакций (базовая)

```sql
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type VARCHAR(20) NOT NULL,           -- 'expense' | 'income'
    amount BIGINT NOT NULL,              -- в сумах
    category VARCHAR(50) NOT NULL,       -- 'hosting', 'marketing', etc.
    period VARCHAR(20) DEFAULT 'monthly', -- 'monthly' | 'yearly' | 'quarterly'
    description TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE categories (
    id VARCHAR(50) PRIMARY KEY,          -- 'hosting', 'marketing', etc.
    name VARCHAR(100) NOT NULL,          -- 'Серверы', 'Маркетинг'
    icon VARCHAR(50),                    -- 'Server', 'Megaphone'
    color VARCHAR(7),                    -- '#2563eb'
    department VARCHAR(50)               -- для фильтрации
);
```

---

## Q4: Модули системы

### Решение

| Модуль | Паттерн | Приоритет | Статус |
|--------|---------|-----------|--------|
| Dashboard | Command | 🔴 P0 | В разработке |
| КолЦентр | RAG | ✅ | Работает (Telegram бот) |
| Маркетинг | RAG | 🟡 P1 | Следующий |
| HR | RAG | 🟡 P1 | Спецификация готова |
| Аналитика | TBD | ⚪ P2 | Заглушка в UI |
| Продажи | TBD | ⚪ P2 | Заглушка в UI |
| Логистика | TBD | ⚪ P2 | Заглушка в UI |
| Склад | TBD | ⚪ P2 | Заглушка в UI |

### Авторизация по отделам

```
Регистрация → Выбор отдела → Подтверждение админом → Доступ только к своему разделу

Роли:
- admin: Все разделы + загрузка документов + подтверждение регистраций
- user: Только свой раздел
```

---

## Q5: Qdrant (векторная БД)

### Решение

| Параметр | Значение |
|----------|----------|
| Структура | Единая коллекция |
| Фильтрация | По `department` в payload |

### Payload schema

```json
{
  "department": "hr",
  "category": "legislation",
  "source": "kadrovik.uz",
  "title": "Изменения в Трудовом кодексе 2026",
  "url": "https://kadrovik.uz/...",
  "published_date": "2026-01-07",
  "tags": ["трудовой кодекс", "изменения"],
  "language": "ru"
}
```

### Запрос с фильтрацией

```python
qdrant.search(
    collection_name="biotact_knowledge",
    query_vector=embedding,
    query_filter=Filter(
        must=[
            FieldCondition(key="department", match=MatchValue(value="hr"))
        ]
    ),
    limit=5
)
```

---

## Q6: Real-time

### Решение

| Параметр | Значение |
|----------|----------|
| MVP | REST API |
| WebSocket | В backlog, добавить по запросу |

### Обоснование

- 2-4 пользователя Dashboard — редко работают одновременно
- WebSocket добавляет +30% сложности
- MVP фокус на core-функционал

### Поведение

```
После команды в чате:
1. AI обрабатывает → Function Call → DB
2. Автоматический refresh данных у текущего пользователя
3. Другие пользователи: обновление страницы или кнопка "Обновить"

Backlog:
- Polling каждые 60 сек (если понадобится)
- WebSocket (если реально мешает)
```

---

## Сводка технологий

| Слой | Технология |
|------|------------|
| Frontend | React 18 + Tailwind + Recharts + Lucide |
| Backend | FastAPI (Python) или Node.js |
| AI/LLM | GPT-4o-mini + Function Calling |
| Vector DB | Qdrant |
| Database | PostgreSQL |
| Auth | JWT + роли (admin/user) + department |
| Real-time | REST (MVP), WebSocket (backlog) |

---

## Файлы проекта

| Файл | Описание |
|------|----------|
| `biotact-dashboard-v3.jsx` | React-прототип с темами |
| `BIOTACT-DASHBOARD.md` | Документация по Dashboard |
| `BIOTACT-ADR.md` | Этот файл — архитектурные решения |
| `BIOTACT_HR_Section_Architecture.docx` | Спецификация HR-раздела |

---

*Документ создан: 13 января 2026*
*BIOTACT Core | Architecture Decision Record*
