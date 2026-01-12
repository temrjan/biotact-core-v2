# BIOTACT RAG System — Техническое задание v1.0

**Дата:** 2026-01-21
**Сервер:** biotact-core-v2 (38.242.138.184, Contabo)
**ОС:** Ubuntu 24.04.3 LTS

---

## 1. ТЕКУЩАЯ АРХИТЕКТУРА

### 1.1 Компоненты системы

```
┌─────────────────────────────────────────────────────────────┐
│                    DOCKER COMPOSE                            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  PostgreSQL │  │    Redis    │  │   Qdrant    │          │
│  │   :5432     │  │    :6379    │  │ :6333/:6334 │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│         │                │                │                  │
│         └────────────────┼────────────────┘                  │
│                          │                                   │
│                 ┌────────┴────────┐                          │
│                 │   biotact-api   │                          │
│                 │  FastAPI :8000  │                          │
│                 │                 │                          │
│                 │  [ВРУЧНУЮ]      │                          │
│                 │  telegram_bot.py│ ← ПРОБЛЕМА!              │
│                 └─────────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
            ┌─────────────────────────┐
            │     EXTERNAL APIs       │
            ├─────────────────────────┤
            │ • OpenAI (embeddings)   │
            │ • Together AI (Qwen LLM)│
            │ • Telegram Bot API      │
            └─────────────────────────┘
```

### 1.2 Технологический стек

| Слой | Технология | Версия | Назначение |
|------|------------|--------|------------|
| **Runtime** | Python | 3.11 | Основной язык |
| **Web Framework** | FastAPI | 0.115+ | REST API |
| **ASGI Server** | Uvicorn | 0.32+ | HTTP сервер |
| **Database** | PostgreSQL | 16-alpine | Пользователи, сессии чата |
| **Vector DB** | Qdrant | 1.13.0 (факт) / 1.16.2 (compose) | Хранение embeddings |
| **Cache** | Redis | 7-alpine | Кэширование (не используется ботом) |
| **RAG Framework** | LlamaIndex | 0.14+ | Retrieval pipeline |
| **Embeddings** | OpenAI text-embedding-3-large | - | 3072-мерные векторы |
| **Chat LLM** | Qwen/Qwen3-235B-A22B-Instruct | Together AI | Генерация ответов |
| **Telegram** | aiogram | 3.24 | Telegram Bot Framework |
| **Container** | Docker Compose | - | Оркестрация |

### 1.3 Ключевые файлы

```
/opt/biotact-core-v2/
├── src/biotact/
│   ├── telegram_bot.py          # Telegram бот (RAG + aiogram)
│   ├── main.py                  # FastAPI app
│   ├── config/departments.py    # Конфигурация департаментов (top_k и т.д.)
│   └── services/rag/
│       ├── qdrant.py            # Qdrant client
│       ├── embedding.py         # OpenAI embeddings
│       └── llm.py               # LLM service
├── prompts/
│   └── askbiotact.txt           # Системный промпт (~23KB)
├── data/knowledge/evolution/    # RAG документы (7 файлов, 160 chunks)
├── docker-compose.prod.yml
├── Dockerfile
└── .env                         # Секреты
```

---

## 2. ВЫЯВЛЕННЫЕ ПРОБЛЕМЫ

### 2.1 КРИТИЧЕСКИЕ

#### P1: Telegram Bot не управляется Docker
```
Статус: КРИТИЧНО
Описание: Бот запускается вручную через `docker exec -d ... nohup python3 ...`
Симптомы:
  - При рестарте контейнера бот не запускается автоматически
  - Конфликты при попытке перезапуска (TelegramConflictError)
  - pkill не работает корректно в Alpine-контейнере
  - Логи теряются при рестарте (/tmp/bot.log)

Причина: Dockerfile CMD запускает только Uvicorn, бот требует отдельного процесса
```

#### P2: Версия Qdrant — несовместимость
```
Статус: WARNING (работает, но рискованно)
docker-compose.prod.yml: qdrant/qdrant:v1.16.2
Реально на сервере: v1.13.0
Python qdrant-client: 1.16.2

Warning в логах:
"Qdrant client version 1.16.2 is incompatible with server version 1.13.0"
```

### 2.2 АРХИТЕКТУРНЫЕ

#### P3: Один контейнер — несколько процессов
```
Антипаттерн Docker: "One container = One process"
Сейчас: API + Bot должны жить в одном контейнере
Проблема: Нет изоляции, сложное управление жизненным циклом
```

#### P4: Отсутствие процесс-менеджера
```
В Alpine-контейнере нет:
- systemd
- supervisord
- полноценного init

Результат: Нельзя корректно управлять фоновыми процессами
```

### 2.3 КОНФИГУРАЦИОННЫЕ

#### P5: Together AI не в docker-compose
```
.env содержит:
  TOGETHER_API_KEY=...
  USE_TOGETHER=true
  TOGETHER_MODEL=Qwen/Qwen3-235B-A22B-Instruct-2507-tput

docker-compose.prod.yml: НЕ содержит этих переменных
Работает случайно через volume: ./.env:/app/.env:ro
```

#### P6: Healthcheck только для API
```
Healthcheck проверяет: http://localhost:8000/api/v1/health
Бот: Не мониторится, может упасть незаметно
```

---

## 3. АНАЛИЗ: DOCKER vs БЕЗ DOCKER

### 3.1 Что даёт Docker сейчас

| Преимущество | Реальная польза для проекта |
|--------------|----------------------------|
| Изоляция окружения | ✅ Python deps не конфликтуют с системой |
| Воспроизводимость | ✅ Можно развернуть на другом сервере |
| Версионирование | ⚠️ Частично (Qdrant версия разошлась) |
| Простота деплоя | ❌ Усложняет из-за бота |
| Масштабирование | ❌ Не используется (1 сервер) |
| Оркестрация | ⚠️ Docker Compose, но бот вне управления |

### 3.2 Сложности от Docker

| Проблема | Влияние |
|----------|---------|
| Бот вне lifecycle | Ручной запуск, конфликты, потеря логов |
| Отладка | Сложнее — нужен docker exec |
| Логи | Разбросаны: docker logs vs /tmp/bot.log |
| Обновление кода | Требует rebuild image или docker cp |
| Ресурсы | Overhead от контейнеризации (~200MB RAM) |

### 3.3 Вариант: Отказ от Docker

#### Что потребуется:
```bash
# 1. Системные зависимости
sudo apt install python3.11 python3.11-venv postgresql redis-server

# 2. Qdrant — binary или Docker (он легковесный)
# Можно оставить в Docker отдельно

# 3. Python virtual environment
python3.11 -m venv /opt/biotact/venv
source /opt/biotact/venv/bin/activate
pip install -e .

# 4. Systemd services
/etc/systemd/system/biotact-api.service
/etc/systemd/system/biotact-bot.service
```

#### Преимущества без Docker:
```
✅ Простое управление процессами через systemd
✅ Автозапуск при рестарте сервера
✅ Нативные логи через journalctl
✅ Простая отладка
✅ Меньше overhead
✅ Проще обновлять код (git pull && systemctl restart)
```

#### Недостатки без Docker:
```
❌ Зависимость от системных пакетов
❌ Сложнее перенести на другой сервер
❌ Нужно вручную управлять версиями Python
❌ PostgreSQL/Redis нужно настраивать отдельно
```

---

## 4. ВАРИАНТЫ РЕШЕНИЯ

### Вариант A: Отдельный контейнер для бота (рекомендуется для Docker)

```yaml
# docker-compose.prod.yml - добавить:
services:
  bot:
    image: biotact-core-v2-api:latest
    container_name: biotact-bot
    restart: unless-stopped
    command: ["python3", "-u", "/app/src/biotact/telegram_bot.py"]
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
      TOGETHER_API_KEY: ${TOGETHER_API_KEY}
      TOGETHER_MODEL: ${TOGETHER_MODEL}
      USE_TOGETHER: "true"
      QDRANT_HOST: qdrant
      QDRANT_PORT: 6333
      QDRANT_COLLECTION: knowledge-evolution
      # ... остальные переменные
    volumes:
      - ./prompts:/app/prompts:ro
      - ./data:/app/data:ro
      - bot_logs:/var/log/biotact
    depends_on:
      qdrant:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python3", "-c", "import requests; requests.get('https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe')"]
      interval: 60s
      timeout: 10s
      retries: 3
    networks:
      - biotact-network

volumes:
  bot_logs:
    name: biotact_bot_logs
```

**Оценка:**
- Сложность: Средняя
- Время: 2-3 часа
- Надёжность: Высокая

### Вариант B: Systemd без Docker (рекомендуется для простоты)

```ini
# /etc/systemd/system/biotact-bot.service
[Unit]
Description=Biotact Telegram Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=biotact
Group=biotact
WorkingDirectory=/opt/biotact-core-v2
Environment="PATH=/opt/biotact-core-v2/.venv/bin"
EnvironmentFile=/opt/biotact-core-v2/.env
ExecStart=/opt/biotact-core-v2/.venv/bin/python3 src/biotact/telegram_bot.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Оценка:**
- Сложность: Низкая
- Время: 1-2 часа
- Надёжность: Очень высокая

### Вариант C: Гибридный (Docker для БД, systemd для приложений)

```
Docker:
  - PostgreSQL
  - Redis
  - Qdrant

Systemd:
  - biotact-api.service
  - biotact-bot.service
```

**Оценка:**
- Сложность: Средняя
- Время: 3-4 часа
- Надёжность: Высокая
- Гибкость: Максимальная

---

## 5. ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ

### 5.1 Мониторинг и логирование
```
Текущее состояние: Логи в stdout/файлы, нет алертов
Рекомендация:
  - Loki + Grafana для логов
  - Или простой logrotate + tail по SSH
  - Telegram алерты при падении бота
```

### 5.2 RAG Pipeline оптимизация
```
Текущее:
  - top_k=5 (было 15)
  - Системный промпт ~23KB токенов

Рекомендации:
  - Сократить системный промпт до ~5-7KB
  - Добавить reranker после retrieval
  - Кэшировать частые запросы в Redis
```

### 5.3 Версии и зависимости
```
Исправить:
  - Qdrant: обновить сервер до 1.16.2 ИЛИ понизить client
  - Добавить requirements.lock для reproducibility
```

### 5.4 Безопасность
```
Текущее:
  - API ключи в .env (OK)
  - Бот работает от root в контейнере

Улучшить:
  - Использовать Docker secrets или Vault
  - Non-root user для бота
```

---

## 6. ПЛАН ДЕЙСТВИЙ (для следующей сессии)

### Фаза 1: Стабилизация бота (приоритет HIGH)
```
□ Выбрать вариант: A (Docker) или B (systemd)
□ Реализовать автозапуск бота
□ Настроить healthcheck/мониторинг
□ Исправить логирование
```

### Фаза 2: Исправление конфигурации
```
□ Синхронизировать версию Qdrant
□ Добавить Together AI в docker-compose (если остаёмся на Docker)
□ Убрать markdown из ответов бота (проверить после рестарта)
```

### Фаза 3: Оптимизация (приоритет MEDIUM)
```
□ Сократить системный промпт
□ Настроить Redis кэширование
□ Добавить rate limiting для бота
```

---

## 7. КОМАНДЫ ДЛЯ БЫСТРОГО ДОСТУПА

```bash
# SSH подключение
ssh biotact-core-v2

# Проверить статус контейнеров
docker ps -a

# Логи API
docker logs biotact-api --tail 100

# Логи бота (если запущен)
docker exec biotact-api cat /tmp/bot.log

# Запустить бота вручную (текущий способ)
docker exec biotact-api sh -c 'nohup python3 /app/src/biotact/telegram_bot.py > /tmp/bot.log 2>&1 &'

# Проверить процессы бота
docker exec biotact-api sh -c 'cat /proc/*/cmdline 2>/dev/null | tr "\0" " " | grep telegram'

# Рестарт контейнера (убивает все процессы)
docker restart biotact-api

# Проверить Qdrant
docker exec biotact-api curl -s http://biotact-qdrant:6333/collections

# Путь к файлам на сервере
/opt/biotact-core-v2/
```

---

## 8. КОНТАКТЫ И РЕСУРСЫ

- **Сервер:** 38.242.138.184 (Contabo)
- **SSH:** biotact-core-v2 (настроен в ~/.ssh/config)
- **Telegram Bot:** @AskBiotact_bot
- **Together AI Model:** Qwen/Qwen3-235B-A22B-Instruct-2507-tput
- **Qdrant Collection:** knowledge-evolution (160 vectors)

---

## 9. ОТКРЫТЫЕ ВОПРОСЫ ДЛЯ ОБСУЖДЕНИЯ

1. **Docker или systemd?** — Какой подход предпочтительнее для этого проекта?
2. **Масштабирование** — Планируется ли несколько серверов в будущем?
3. **Бэкапы** — Как сейчас бэкапится PostgreSQL и Qdrant?
4. **CI/CD** — Есть ли автоматический деплой?
5. **Мониторинг** — Нужны ли алерты при падении сервисов?

---

*Документ создан: 2026-01-21*
*Автор: Claude Code (Opus 4.5)*
