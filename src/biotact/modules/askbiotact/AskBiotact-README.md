# AskBiotact — AI-консультант по здоровому образу жизни

Модуль RAG-чатбота внутри платформы **biotact-core-v2**. Консультирует клиентов по продукции BIOTACT Deutschland через Telegram-бот и Public API.

## Философия

> "Мы не продаем продукты — мы предлагаем РЕШЕНИЯ для здорового образа жизни."

Бот анализирует ситуацию клиента целиком и предлагает комплексные решения:
- БАДы (синбиотики, витаминные комплексы) — 13 продуктов
- Техника для здорового питания — 7 продуктов
- Аксессуары для активной жизни — 9 продуктов

## Архитектура

```
biotact-core-v2/                        # Модульный монолит (FastAPI)
├── src/biotact/
│   ├── main.py                         # FastAPI app, lifespan
│   ├── modules/
│   │   ├── base.py                     # BaseModuleConfig, RAGModuleConfig, CommandModuleConfig
│   │   ├── registry.py                 # ModuleRegistry (singleton)
│   │   ├── askbiotact/                 # << ЭТОТ МОДУЛЬ
│   │   │   ├── config.py              # RAGModuleConfig(department_id="askbiotact", rag_limit=10, score_threshold=0.30)
│   │   │   ├── service.py             # AskBiotactService — RAG pipeline + Phase 0.6 safety_filter integration
│   │   │   ├── safety_filter.py       # Phase 0.6 — code-level guard: detect_safety_trigger + apply_safety_filter
│   │   │   ├── constants.py           # PRODUCT_NAMES, PRODUCT_PRICES, ORDER_KEYWORDS, enrich_query
│   │   │   ├── schemas.py             # AskRequest/AskResponse/ParsedOrder pydantic
│   │   │   └── __init__.py
│   │   ├── crm/                        # CRM для Telegram-клиентов
│   │   │   ├── models.py              # TelegramCustomer (проблемы, семья, покупки, AI-заметки)
│   │   │   ├── service.py             # get_or_create, add_purchase, format_context_for_prompt
│   │   │   ├── schemas.py
│   │   │   └── router.py
│   │   ├── callcenter/                 # Другие департаменты (RAG)
│   │   ├── marketing/
│   │   ├── hr/
│   │   ├── dashboard/                  # Command-модуль (Function Calling -> SQL)
│   │   └── sales/
│   ├── api/v1/
│   │   ├── public.py                   # POST /api/v1/public/ask — основной endpoint AskBiotact
│   │   └── webhooks.py                 # POST /api/v1/webhooks/telegram — Telegram webhook (inline-кнопки)
│   ├── services/
│   │   ├── chat_service.py             # Оркестрация RAG-пайплайна (для внутренних модулей)
│   │   ├── extraction_agent.py         # ExtractionAgent (GPT-4o-mini, async) — извлечение insights
│   │   ├── rag/
│   │   │   ├── llm.py                 # LLMService (OpenAI / Anthropic)
│   │   │   └── qdrant.py             # QdrantService (vector search + department filter)
│   │   └── auth_service.py
│   ├── integrations/
│   │   ├── openai/                     # Embeddings
│   │   ├── telegram/
│   │   └── amocrm/
│   └── telegram_bot.py                # Standalone Telegram-бот (aiogram + LlamaIndex, legacy)
├── prompts/
│   └── askbiotact.txt                  # Системный промпт (40 строк, ~4.5KB)
├── data/knowledge/evolution/           # RAG-документы (НЕ смонтированы в Docker!)
│   ├── biotact_rag_cards_qdrant.txt   # 13 карточек БАДов
│   ├── biotact_rag_cards_tech_qdrant.txt  # 16 карточек (техника + active life)
│   ├── prices.txt                      # Единый прайс-лист (RU/UZ)
│   ├── rag_config.yaml                # Конфиг индексера (для контейнера)
│   └── rag_config_host.yaml           # Конфиг индексера (для хоста)
├── scripts/
│   └── rag_indexer.py                 # Универсальный индексер (YAML, секции, dry-run, stats, search)
└── docker-compose.prod.yml
```

## Стек

| Компонент | Технология |
|---|---|
| API | FastAPI (Python 3.11, uvicorn) |
| LLM (основной) | OpenAI GPT-5 mini |
| LLM (HR Digest) | OpenAI gpt-4o-mini (прямой клиент) |
| LLM (Extraction Agent) | OpenAI gpt-4o-mini (async insights) |
| LLM (Order Parsing) | OpenAI gpt-4o-mini (parse_order_with_llm) |
| LLM (Function Calling) | OpenAI gpt-4o (command_executor) |
| Embeddings | OpenAI text-embedding-3-large (3072d) |
| Vector DB | Qdrant v1.16.2 (коллекция `knowledge-evolution`, cosine) |
| История чата | Redis 7 (TTL 24h, макс 10 пар сообщений) |
| CRM | PostgreSQL 16 (таблица `telegram_customers`) |
| Telegram-бот | Внешний (вызывает Public API через HTTP) |

## Пайплайн обработки запроса

```
POST /api/v1/public/ask (X-API-Key)
    │
    ├── 1. Auth: проверка API-ключа
    ├── 2. Redis: загрузка истории чата (public:{user_id}:history)
    ├── 3. CRM: get_or_create клиента в PostgreSQL
    ├── 4. Order Detection: поиск телефона + ключевых слов заказа
    │      ├── parse_order_with_llm() → GPT-4o-mini извлекает имя/телефон/адрес/продукты
    │      ├── format_order_for_sales() → структурированная заявка с ценами и итогом
    │      └── fallback на сырой текст если LLM-парсинг не удался
    ├── 5. Query Enrichment:
    │      ├── DB insights (ExtractionAgent) → приоритет
    │      ├── Короткие запросы (<30 символов) → добавляем контекст из истории
    │      └── Запросы о ценах → добавляем семантическое ядро для prices.txt
    ├── 6. Embedding: OpenAI text-embedding-3-large
    ├── 7. Qdrant: vector search (department_id=askbiotact, limit=5, threshold=0.30)
    ├── 8. LLM: GPT-5 mini генерирует ответ
    │      ├── system_prompt: prompts/askbiotact.txt (+ CRM-контекст клиента)
    │      └── user_message: RAG-контекст + оригинальный вопрос
    ├── 8.5. Safety filter (Phase 0.6, post-process):
    │      ├── detect_safety_trigger(message) → pregnancy/child<3/cardiac/chronic/None
    │      └── if trigger → strip BIOTACT product names + ensure doctor redirect
    ├── 9. Redis: сохранение истории
    ├── 10. ExtractionAgent (async, не блокирует ответ):
    │      └── GPT-4o-mini → products, symptoms, family, intent, summary → conversation_insights
    └── 11. Response: {answer, user_id, order_sent}
```

## RAG-данные (37 документов в Qdrant)

- **29 карточек продуктов** — plain text, без markdown/emoji, самодостаточные
  - Каждая содержит: описание, состав, показания, дозировки, "Когда рекомендуется" (на языке клиента для vector search)
  - Цены вынесены из карточек в отдельный файл
- **8 секций prices.txt** — единый источник цен (RU + UZ), FAQ по доставке
- Секционный формат: `===СЕКЦИЯ===` / `===/СЕКЦИЯ===`
- Индексатор: `scripts/rag_indexer.py` (запускать только с хоста, не из контейнера!)

```bash
# Переиндексация (с хоста сервера)
cd /opt/biotact-core-v2
source .env && export OPENAI_API_KEY
python3 scripts/rag_indexer.py -c data/knowledge/evolution/rag_config_host.yaml --verbose index --force

# Поиск
python3 scripts/rag_indexer.py -c data/knowledge/evolution/rag_config_host.yaml search "выпадение волос"

# Статистика
python3 scripts/rag_indexer.py -c data/knowledge/evolution/rag_config_host.yaml stats
```

## LLM-провайдеры

Сервис `LLMService` поддерживает два провайдера через единый интерфейс:

| Провайдер | .env | Модель |
|---|---|---|
| **OpenAI** (текущий) | `LLM_PROVIDER=openai` | `LLM_MODEL=gpt-5-mini` |
| Anthropic | `LLM_PROVIDER=anthropic` | `LLM_MODEL=claude-haiku-4-5-20251001` |

Переключение — изменить `LLM_PROVIDER` и `LLM_MODEL` в `.env` + перезапустить контейнер.

> OpenAI API-ключ нужен всегда — для embeddings, function calling (dashboard), и HR digest summarizer.

## Модульная система

Платформа — **модульный монолит**. Каждый департамент — отдельный модуль с конфигом:

- **RAG-модули** (`RAGModuleConfig`): askbiotact, callcenter, marketing, hr — vector search + LLM
- **Command-модули** (`CommandModuleConfig`): dashboard — Function Calling → SQL

Все модули фильтруют Qdrant по `department_id` (payload-based multitenancy, одна коллекция).

## Extraction Agent (async insights)

После каждого ответа бота асинхронно запускается `ExtractionAgent`:

| Параметр | Значение |
|---|---|
| Модель | GPT-4o-mini (temperature=0) |
| Режим | async — не блокирует ответ клиенту |
| Таблица | `conversation_insights` (PostgreSQL) |

Извлекает из диалога:
- **products** — упомянутые продукты
- **symptoms** — жалобы/симптомы клиента
- **family** — информация о семье (возраст детей и т.д.)
- **intent** — намерение (консультация, покупка, жалоба)
- **summary** — краткое резюме разговора

Данные накапливаются в течение сессии и используются для:
1. **Query Enrichment** — products из insights обогащают короткие запросы (приоритет над regex)
2. **CRM** — будущая автосинхронизация (Phase 3)

При `/ask/reset` вызывается `archive_insight()` — данные архивируются перед очисткой.

## Structured Order Flow

Оба канала (Public API и Telegram webhook) используют одинаковый flow:

```
Телефон обнаружен → parse_order_with_llm() → format_order_for_sales() → Telegram-группа продаж
```

- **parse_order_with_llm()** — GPT-4o-mini извлекает имя, телефон, адрес, продукты с количеством
- **format_order_for_sales()** — структурированная заявка с ценами из `PRODUCT_PRICES` и итогом
- **PRODUCT_PRICES** — 18 продуктов (БАДы + техника), цены в UZS
- **Fallback** — если LLM-парсинг не удался, отправляется сырой текст

Разница между каналами:
- **webhooks.py** (Telegram) — inline-кнопки "Подтвердить / Отмена", pending order в Redis
- **public.py** (API) — заказ отправляется сразу, подтверждение через LLM-ответ бота

## CRM-интеграция

При каждом запросе AskBiotact:
1. Создает/находит клиента по `telegram_id`
2. Загружает профиль (проблемы, семья, покупки)
3. Добавляет профиль в системный промпт для персонализации
4. При заказе — обновляет историю покупок

## Docker

```bash
# Контейнеры
docker compose -f docker-compose.prod.yml up -d    # запуск
docker compose -f docker-compose.prod.yml logs -f api  # логи

# Volumes: src/, prompts/, scripts/ смонтированы — изменения применяются после рестарта
# data/ НЕ смонтирована — индексатор запускать с хоста
```

| Контейнер | Образ | Порт |
|---|---|---|
| biotact-api | biotact-core-v2-api:latest | 8000 |
| biotact-postgres | postgres:16-alpine | 5432 (internal) |
| biotact-qdrant | qdrant/qdrant:v1.16.2 | 6333 (internal) |
| biotact-redis | redis:7-alpine | 6379 (internal) |

## API

```bash
# Отправить вопрос
curl -X POST http://localhost:8000/api/v1/public/ask \
  -H "X-API-Key: $ASKBIOTACT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123456", "message": "Что помогает при выпадении волос?", "first_name": "Анна"}'

# Сбросить историю
curl -X POST "http://localhost:8000/api/v1/public/ask/reset?user_id=123456" \
  -H "X-API-Key: $ASKBIOTACT_API_KEY"

# Health check
curl http://localhost:8000/api/v1/health
```

## Ключевые правила промпта

- Всегда выяснить возраст до рекомендации
- При серьезных симптомах → направить к врачу
- Цены только из базы знаний, не выдумывать
- БАДы не лечат, а поддерживают организм
- Ответ: plain text, 200-400 символов, макс 1-2 эмодзи
- Язык ответа = язык вопроса (RU/UZ)
