# AskBiotact: Enrichment Agent — План реализации

## Статус: В РАБОТЕ
- Дата старта: 2026-02-08
- Модель бота: GPT-4o (переключена с Qwen3-235B)
- Prompt fix "BIFOLAK MAGNIY": DONE

---

## Проблема

При follow-up запросах ("да", "подробнее", "сколько стоит") бот галлюцинирует.

**Корневая причина:** enrichment подклеивает только user-сообщения, а название продукта находится в ответе бота (role=assistant). RAG получает слабый запрос → слабый контекст → LLM додумывает несуществующие детали.

**Пример:**
```
Бот ответил: "...подойдёт BIFOLAK NEO..."
Юзер: "да, сколько стоит"

Enrichment сейчас:  "У моего сына животик дуется Ему 2 года да, сколько стоит"
Нужно:              "BIFOLAK NEO да, сколько стоит цены..."
```

---

## Архитектура решения

```
Юзер → ФАЗА 1 (regex, sync) → ФАЗА 2 (DB read, sync) → RAG + LLM → Ответ
                                                                        │
                                                            ФАЗА 4 (async)
                                                            Агент-экстрактор
                                                            GPT-4o-mini
                                                                        │
                                                            UPSERT conversation_insights
                                                            UPDATE telegram_customers
```

**Ключевой принцип:** Агент работает ПОСЛЕ ответа юзеру (async). Enrichment читает из БД (sync, ~5ms). Задержки для юзера — ноль.

**Fallback-цепочка enrichment:**
1. `conversation_insights.products` (из БД, обновлено агентом)
2. `extract_products_from_history()` (regex, из Redis-истории)
3. `telegram_customers` профиль (для возвращающихся юзеров)
4. Подклейка user-сообщений (текущее поведение, крайний случай)

---

## ФАЗА 1: Быстрый фикс enrichment

**Время:** 30 минут
**Файл:** `src/biotact/api/v1/public.py`
**Риск:** Минимальный — только изменение логики enrichment

### Задача

Подключить `extract_products_from_history()` (строка ~180) — функция УЖЕ написана, ищет продукты из ОБОИХ ролей, но НЕ вызывается.

### Изменения в `enrich_query_with_context()`

```python
def enrich_query_with_context(message: str, history: list[dict[str, str]]) -> str:
    message_lower = message.lower()
    enriched = message

    # STEP 1: Для коротких запросов — обогащение контекстом
    if is_short_query(message) and history:
        # Сначала пробуем найти продукты в истории (ОБЕ роли)
        products = extract_products_from_history(history)
        if products:
            product_prefix = " ".join(products)
            enriched = f"{product_prefix} {message}"
            logger.info(f"Product-enriched query: {enriched[:80]}...")
        else:
            # Fallback: подклейка последних user-сообщений
            recent_user_msgs = [
                m["content"] for m in history[-6:]
                if m.get("role") == "user"
            ][-2:]
            if recent_user_msgs:
                context_prefix = " ".join(recent_user_msgs)
                enriched = f"{context_prefix} {message}"
                logger.info(f"History-enriched query: {enriched[:80]}...")

    # STEP 2: Ценовой триггер — без изменений
    is_price_query = any(trigger in message_lower for trigger in PRICE_TRIGGERS)
    if is_price_query:
        enriched = f"{enriched} {PRICE_ENRICHMENT}"
        logger.info(f"Price query enriched: {message[:50]}...")

    return enriched
```

### Тест после Фазы 1

5 вопросов через API → сравнение с текущими результатами.

---

## ФАЗА 2: Агент-экстрактор + БД

**Время:** 1-2 дня
**Новые файлы:** миграция, extraction_agent.py
**Изменяемые файлы:** public.py, config.py

### 2.1 Миграция: conversation_insights

```sql
CREATE TABLE conversation_insights (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT NOT NULL,

    -- Извлечённые сущности
    products        TEXT[] DEFAULT '{}',
    symptoms        TEXT[] DEFAULT '{}',
    family_members  JSONB DEFAULT '[]',
    client_age      INT,
    intent          VARCHAR(30),
    phone           VARCHAR(20),
    semantic_summary TEXT,

    -- Мета
    message_count   INT DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Partial index: быстрый поиск активного диалога
CREATE INDEX idx_ci_active ON conversation_insights(telegram_id, is_active)
    WHERE is_active = TRUE;
```

**Жизненный цикл:**
- Новое сообщение от нового юзера → INSERT (is_active=TRUE)
- Каждый обмен → UPDATE существующего активного ряда
- POST /ask/reset → UPDATE is_active=FALSE (архив)
- Повторное обращение после reset → новый INSERT

### 2.2 ExtractionAgent сервис

**Файл:** `src/biotact/services/extraction_agent.py`

| Параметр | Значение |
|---|---|
| Модель | GPT-4o-mini |
| Temperature | 0 |
| Max tokens | 300 |
| Вызов | asyncio.create_task() после ответа |
| Input | ~300 токенов (summary + пара сообщений) |
| Output | ~100 токенов (JSON) |
| Стоимость | ~$0.0001/обмен ≈ $3/мес при 1000 диалогов/день |

**Промпт агента:**
```
Ты аналитик диалогов BIOTACT. Извлеки сущности из нового обмена.

Текущий контекст: {semantic_summary или "Новый диалог"}

Новый обмен:
Клиент: {user_message}
Консультант: {assistant_message}

Верни ТОЛЬКО валидный JSON:
{
  "products": [],
  "symptoms": [],
  "family": [{"relation": "", "age": null}],
  "client_age": null,
  "intent": "consultation|order|price_check|info|complaint",
  "phone": null,
  "summary": "1-2 предложения, ключевые факты"
}

ПРОДУКТЫ строго из списка:
BIFOLAK ACTIVE, BIFOLAK NEO, BIFOLAK ZINCUM, BIFOLAK ZINCUM+C+D3,
BIFOLAK MAGNIY (капсулы), BIFOLAK MAGNIY (стик),
IMMUNOCOMPLEX, IMMUNOCOMPLEX KIDS,
NEUROCOMPLEX, NEUROCOMPLEX KIDS,
DERMACOMPLEX, OPHTALMOCOMPLEX, CALCIY TRIACTIVE,
Аэрогриль BIOTACT, Блендер BIOTACT, Соковыжималка BIOTACT,
Пароварка BIOTACT, Тостер BIOTACT, Чайник BIOTACT, Мясорубка BIOTACT

Правила:
- Продукты ТОЛЬКО из списка выше. Если бот назвал продукт не из списка — игнорируй.
- Если для поля нет данных — не включай поле в JSON.
- summary: обновлённая версия с учётом нового обмена.
- phone: только если клиент явно оставил номер телефона.
```

### 2.3 Интеграция в пайплайн

**Файл:** `src/biotact/api/v1/public.py`

В `process_rag_query()` — добавить чтение из БД перед enrichment.
В `ask()` — добавить `asyncio.create_task(extraction_agent.process(...))` после ответа.
В `reset_history()` — добавить архивацию: `UPDATE is_active=FALSE`.

### 2.4 Обработка ошибок

| Ситуация | Поведение |
|---|---|
| Агент вернул невалидный JSON | Логируем, пропускаем. Regex-enrichment работает |
| API timeout (GPT-4o-mini) | Логируем, пропускаем. Данные обновятся при следующем обмене |
| Агент вернул продукт не из списка | Фильтруем на уровне сервиса перед записью в БД |
| conversation_insights пуст (новый юзер) | Fallback на regex → telegram_customers → user messages |

---

## ФАЗА 3: CRM-синхронизация

**Время:** 0.5 дня (после Фазы 2)

При архивации диалога (is_active → FALSE):
```python
# Автоматический sync
symptoms → crm_service.add_problems(telegram_id, mapped_symptoms)
family   → crm_service.add_family_member(telegram_id, member)
phone    → crm_service.update(telegram_id, CustomerUpdate(phone=phone))
products → crm_service.ai_notes (дописать "Интересовались: ...")
```

Маппинг симптомов → CRM-тегов:
```python
SYMPTOM_TO_PROBLEM = {
    "вздутие": "gut", "газы": "gut", "диарея": "gut", "запор": "gut",
    "стресс": "stress", "бессонница": "stress", "усталость": "stress",
    "выпадение волос": "skin", "акне": "skin", "сухая кожа": "skin",
    "простуда": "immunity", "иммунитет": "immunity", "болеет": "immunity",
}
```

---

## Файлы: что меняется

| Фаза | Файл | Действие |
|---|---|---|
| 1 | `src/biotact/api/v1/public.py` | Изменить `enrich_query_with_context()` |
| 1 | `prompts/askbiotact.txt` | ✅ DONE — "BIFOLAK MAGNIY" |
| 2 | `migrations/versions/xxx_add_conversation_insights.py` | Новый файл |
| 2 | `src/biotact/services/extraction_agent.py` | Новый файл |
| 2 | `src/biotact/api/v1/public.py` | DB read + async agent call |
| 2 | `src/biotact/core/config.py` | EXTRACTION_MODEL setting |
| 2 | `.env` | EXTRACTION_MODEL=gpt-4o-mini |
| 3 | `src/biotact/api/v1/public.py` | CRM sync при reset |

---

## Тесты

После КАЖДОЙ фазы — прогон через API:

**Сценарий 1: Follow-up (основная проблема)**
1. "У моего сына животик дуется и газы"
2. "Ему 2 года"
3. "да" ← должен ответить про BIFOLAK NEO из RAG, не выдумывать
4. "сколько стоит" ← должен дать точную цену из prices.txt

**Сценарий 2: Прямой вопрос**
5. "Сколько стоит BIFOLAK ACTIVE?" ← контроль, должен работать как раньше

**Сценарий 3: Узбекский**
6. "Sochim tushyapti, nima qilsam boladi?"

**Критерии успеха:**
- Нет галлюцинированных названий продуктов
- Цены только из базы
- Составы и дозировки только из RAG-карточек
- Follow-up запросы получают релевантный RAG-контекст
