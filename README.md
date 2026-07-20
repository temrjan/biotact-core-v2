# Biotact Platform v2

AI-powered RAG (Retrieval-Augmented Generation) system for Biotact pharmaceutical company.

## Quick Start

```bash
# Clone repository
git clone https://github.com/temrjan/biotact-core-v2.git
cd biotact-core-v2

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e ".[dev]"

# Start services
docker compose up -d

# Run development server
make run
```

## Development

```bash
make test        # Run tests
make lint        # Run linter
make typecheck   # Run type checker
make format      # Format code
```

Integration tests need PostgreSQL (models use `JSONB`, which SQLite can't
compile); the OpenAI client is mocked, so no real key is needed:

```bash
podman run -d --rm --name pg-test \
  -e POSTGRES_PASSWORD=test -e POSTGRES_DB=biotact_test \
  -p 5433:5432 postgres:16-alpine
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/biotact_test \
OPENAI_API_KEY=sk-dummy \
  pytest -m integration
```


## AskBiotact Telegram Bot

Telegram-бот (`@AskBiotactBot`) — AI-консультант по продукции Biotact.

### Возможности

- **RAG-консультации** — отвечает на вопросы о продуктах на основе базы знаний (Qdrant + OpenAI)
- **Структурированные заявки** — парсит произвольный текст заказа через GPT-4o-mini, показывает пользователю красивую заявку с названиями продуктов, ценами и итогом
- **Подтверждение заказа** — inline-кнопки «Подтвердить / Отмена»
- **Уведомление менеджеров** — после подтверждения отправляет структурированную заявку в группу продаж

### Флоу заказа

1. Пользователь пишет заказ в свободной форме (например: *"биолак актив 2шт иван +998901234567 ташкент"*)
2. Бот распознаёт телефон, парсит текст через LLM → извлекает продукты, количество, имя, адрес
3. Показывает структурированную заявку с ценами и кнопками подтверждения
4. После подтверждения — отправляет заявку в группу продаж

### Ключевые файлы

| Файл | Описание |
|------|----------|
| `src/biotact/api/v1/webhooks.py` | Webhook-хэндлер: RAG, заказы, Telegram API |
| `src/biotact/api/v1/public.py` | Публичный API (сайт biotact.uz) |
| `src/biotact/services/extraction_agent.py` | Extraction agent для аналитики |
| `src/biotact/services/rag/` | RAG-сервисы: embedding, LLM, Qdrant |
| `prompts/askbiotact.txt` | Системный промпт бота |

## RAG Knowledge Base

База знаний AskBiotact — двуязычная (RU + UZ), хранится в Qdrant.

### Архитектура

- **Embeddings:** OpenAI text-embedding-3-large (3072 dims)
- **Vector DB:** Qdrant, коллекция `knowledge-evolution`
- **LLM:** gpt-4.1-mini (OpenAI)
- **Score threshold:** 0.30
- **Индексер:** `scripts/rag_indexer.py` (запуск с хоста, не из контейнера)

### Документы

Расположение: `data/knowledge/evolution/`

| Тип | Файлы | Секции | Описание |
|-----|--------|--------|----------|
| Продукты RU | 11 `*_RU.txt` | 91 | Карточки продуктов на русском |
| Продукты UZ | 11 `*_UZ.txt` | 91 | Карточки продуктов на узбекском |
| Техкарточки | `biotact_rag_cards_tech_qdrant.txt` | 16 | Бытовая техника Biotact |
| Прайс-лист | `prices.txt` | 8 | Цены на все продукты |
| **Итого** | **24 файла** | **206 точек** | |

### 11 продуктов

BIFOLAK_ZINCUM, BIFOLAK_ZINCUM_C_D3, BIFOLAK_ACTIVE, BIFOLAK_MAGNIY, BIFOLAK_NEO, IMMUNOCOMPLEX, IMMUNOCOMPLEX_KIDS, CALCIY_TRIACTIVE_D3, NEUROCOMPLEX_KIDS, OPHTALMOCOMPLEX, DERMACOMPLEX

### Формат секций

Каждый файл содержит 8-9 секций в формате:

```
===СЕКЦИЯ===
product_id: PRODUCT_NAME
doc_type: product_card | symptoms_search | combinations | contraindications | dosage_norms
category: probiotiki-vitaminy-mineraly

[Заголовок секции]
Содержимое (чистый текст, без markdown-маркеров)
===/СЕКЦИЯ===
```

Типы секций на продукт:
- `product_card` (1) — обзор, состав, дозировка, механизм действия
- `symptoms_search` (3-5) — группы симптомов для поиска (ЖКТ, иммунитет, кожа и т.д.)
- `combinations` (1) — рекомендуемые комбинации с другими продуктами
- `contraindications` (1) — противопоказания, взаимодействие с лекарствами
- `dosage_norms` (1) — нормы, подробные дозировки, особые группы

### Переиндексация

```bash
# Удалить state и коллекцию
cd /opt/biotact-core-v2
rm -f data/knowledge/evolution/.rag_state.json
curl -X DELETE http://172.18.0.5:6333/collections/knowledge-evolution

# Запустить индексер (с хоста, НЕ из контейнера)
OPENAI_API_KEY='...' python3 scripts/rag_indexer.py \
  --config data/knowledge/evolution/rag_config_host.yaml index

# Тест поиска
OPENAI_API_KEY='...' python3 scripts/rag_indexer.py \
  --config data/knowledge/evolution/rag_config_host.yaml search "запрос" --limit 5
```

### Правила документов

- Чистый текст: без `*`, `#`, `_` как маркеров форматирования
- Максимум 8000 символов на секцию
- `product_id` в UPPERCASE
- UZ — узбекский латиницей (o', qo', bo' и т.д.)
- `bilingual.enabled: false` в конфиге (отдельные файлы RU и UZ)

## Documentation

- [RFC 001: Architecture](docs/RFC_001_architecture.md)
- [API Specification](docs/api/openapi.yaml)
- [ADR: Modular Monolith](docs/ADR/001_modular_monolith.md)
