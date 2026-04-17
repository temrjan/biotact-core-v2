# Модуль «Медиа» — STT + TTS + Unified RAG Chat

> Раздел для работы с аудио (транскрибация, синтез) и единый LLM-поиск по всем коллекциям знаний компании.
> Дата: 2026-04-17 | Ветка: main | CI: Tests + Deploy green (Lint — чужие ошибки в hr-модуле)

---

## Что сделано

Доставлено тремя этапами (+ 2 хот-фикса):

| Этап  | Коммит        | Содержание                                              |
|-------|---------------|---------------------------------------------------------|
| 1     | `dbbd67a`     | `POST /audio/transcribe`, `POST /audio/synthesize` (Whisper + TTS-1, 25 MB лимит) |
| 2     | `e571de5`     | ffmpeg split для файлов >20 MB, поддержка до 300 MB / ~4 часов |
| 3     | `89ba01c`     | Qdrant-индексация, unified chat по 5 коллекциям, clickable sources |
| 3.1   | `99d005a`     | Alembic owns schema, `|| echo` убран из CD              |
| 3-fix | `731492c`     | Явный commit перед background task (race fix)           |

### Backend (13 файлов)

```
src/biotact/modules/media/
├── __init__.py              — описание модуля
├── models.py                — MediaTranscription (SQLAlchemy 2.0)
├── schemas.py               — 9 Pydantic-схем (transcribe, chat, list)
├── repository.py            — CRUD + update_enrichment
├── openai_client.py         — AudioClient: Whisper (transcribe_long), TTS-1
├── audio_split.py           — ffmpeg subprocess (re-encode → segment, 64k mono)
├── enrich_service.py        — LLM JSON-mode: title + summary + keywords
├── indexing_service.py      — enrich → chunk(2000/400) → embed batch → upsert
├── vector_store.py          — MediaTranscriptionVectorStore (коллекция media_transcriptions)
├── chat_service.py          — Unified RAG по 5 коллекциям, параллельный search
├── utils.py                 — translate_to_english (копия из knowledge.py — техдолг)
└── router.py                — 6 endpoints + background indexing + real cleanup

migrations/versions/
├── i7j8k9l0m123_add_media_transcriptions.py
└── j8k9l0m1n234_add_media_enrichment_fields.py
```

### Frontend

```
frontend/dashboard/src/
├── api.js                   — 6 новых функций (transcribeAudio, synthesizeAudio,
│                              listTranscriptions, getTranscription, deleteTranscription, mediaChat)
└── BiotactDashboard.jsx     — раздел «Медиа» с 3 табами (Изображение / Видео / Аудио)
                              + история STT с пагинацией + unified chat sidebar
                              + цитирование источников с кликабельными media-записями
```

### Инфраструктура

- `Dockerfile`: `ffmpeg` в runtime-stage
- `docker-compose.prod.yml`: `build: .` для api (чтобы CD мог ребилдить образ)
- `.github/workflows/deploy.yml`: `docker compose build api && up -d api` + `alembic upgrade head` (без `|| echo`)
- `deploy/nginx/core.biotact.uz.conf`: snapshot продакшн-конфига с `client_max_body_size 300M`

---

## Архитектура

### Общий доступ

Все транскрипции видны всем авторизованным пользователям. Chat-sidebar ищет по всем записям. **Удалять может только автор** (`uploaded_by == current_user.id`), чужие — `403 Forbidden`.

Модель безопасности по API: JWT Bearer (`CurrentUserDep`). Ключ OpenAI хранится только на сервере, всё проходит через backend.

### Модели данных (PostgreSQL)

```
media_transcriptions
├── id                SERIAL PK
├── transcription_id  VARCHAR(50) UNIQUE INDEX     — бизнес-ключ (UUID)
├── original_filename VARCHAR(500)
├── title             VARCHAR(255)                 — MVP-title → LLM-title
├── text              TEXT                         — полный транскрипт
├── summary           TEXT DEFAULT ''              — LLM: 1-2 предложения о теме
├── keywords          JSONB DEFAULT '[]'           — LLM: 5-10 ключевых слов
├── is_indexed        BOOLEAN DEFAULT false        — готова ли RAG-индексация
├── chunk_count       INTEGER DEFAULT 0
├── uploaded_by       FK → users.id CASCADE INDEX
└── created_at / updated_at (TIMESTAMPTZ)
```

### Qdrant — коллекция `media_transcriptions`

- Размерность: 3072 (text-embedding-3-large)
- Distance: Cosine
- Создаётся автоматически в FastAPI `lifespan` (`MediaTranscriptionVectorStore.ensure_collection()`)

Payload на каждую точку:

```json
{
  "transcription_id": "aa1ddad4-...",
  "user_id": 123,
  "created_at": "2026-04-17T11:03:58+00:00",
  "original_filename": "2026-04-17 09.29.m4a",
  "title": "Проект клинической нутрициологии",
  "summary": "Речь идёт о новом проекте в области клинической нутрициологии...",
  "keywords": ["нутрициология", "пробиотики", "штаммы", ...],
  "chunk_index": 3,
  "content": "полный текст чанка для цитирования"
}
```

### Chunking транскрипта

- Источник: `documents/indexing_service.chunk_text()` (паттерн разделения по предложениям с fallback на границы абзацев)
- Параметры: `chunk_size=2000` символов (~500 токенов), `chunk_overlap=400` (~20%)
- Батч для embedding: 100 чанков на запрос

---

## REST API

Префикс: `/api/v1/media`. Все endpoints требуют JWT.

### Аудио

| Метод  | Путь                                      | Описание                                              |
|--------|-------------------------------------------|-------------------------------------------------------|
| POST   | `/audio/transcribe`                       | Multipart upload → Whisper → сохранить + запустить индексацию. 25 MB direct, >20 MB → split |
| POST   | `/audio/synthesize`                       | JSON `{text, voice}` → MP3 stream (tts-1, 6 голосов)  |
| GET    | `/audio/transcriptions?limit=&offset=`    | Пагинированный список всех записей                    |
| GET    | `/audio/transcriptions/{id}`              | Полный текст + summary + keywords                     |
| DELETE | `/audio/transcriptions/{id}`              | Только автор. Удаляет запись + все векторы в Qdrant   |

### Chat

| Метод | Путь            | Описание                                                        |
|-------|-----------------|-----------------------------------------------------------------|
| POST  | `/chat`         | Unified RAG: embed → параллельный search по 5 коллекциям → LLM ответ с цитатами |

---

## Flow: транскрибация

```
┌──────────────────────────────────────────────────────────────────┐
│ Клиент: POST /audio/transcribe (multipart, JWT)                  │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────┐  size ≤ 20 MB    ┌──────────────────────┐
│ router.transcribe_audio │──────────────────▶│ OpenAI Whisper       │
│ (семафор для split)     │                  │ (language=ru)        │
└────────┬────────────────┘                  └──────────┬───────────┘
         │ size > 20 MB                                  │
         ▼                                               │
┌─────────────────────────┐                             │
│ audio_split.split_audio │                             │
│ ffmpeg: mp3 64k mono,   │                             │
│ segment 10 min          │                             │
└────────┬────────────────┘                             │
         │ list[bytes]                                   │
         ▼                                               │
┌─────────────────────────┐  asyncio.gather   ┌──────────▼───────────┐
│ transcribe_long         │◀─────────────────▶│ Whisper × N chunks   │
│ (Semaphore=5)           │                  │ (параллельно, до 5)  │
└────────┬────────────────┘                  └──────────────────────┘
         │ "\n\n".join(chunks)
         ▼
┌─────────────────────────┐
│ repo.create(MVP title)  │
│ session.commit() ←─── гарантирует видимость для BackgroundTask
│ background_tasks.add()  │
│ return TranscribeResponse
└────────┬────────────────┘
         │ (response уходит клиенту)
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ _index_transcription_background (новая session)                 │
│ 1. enrich_service → {title, summary, keywords} (gpt-4o-mini)    │
│ 2. chunk_text(2000/400)                                         │
│ 3. embedding_service.embed_texts batch                          │
│ 4. vector_store.upsert_chunks → Qdrant                          │
│ 5. repo.update_enrichment → is_indexed=true                     │
└─────────────────────────────────────────────────────────────────┘
```

**Защита от OOM:** endpoint-уровневый `_LONG_TRANSCRIBE_SEM = Semaphore(1)` — одновременно режется/индексируется только один длинный файл. Короткие (≤ 20 MB) проходят без ожидания.

---

## Flow: unified chat

```
POST /media/chat {message, history}
   │
   ▼
MediaChatService.query
   │
   ├── translate_to_english(message)    — только если не-ASCII
   ├── embed_text(ru) + embed_text(en)  — параллельно
   │
   ▼
asyncio.gather(search × 5 коллекций)
   ├── media_transcriptions  (ru)
   ├── user_files            (ru)
   ├── knowledge-evolution   (ru)
   ├── dr_berg               (en embedding)
   └── nutrition_library     (en embedding)
   │
   ▼
Merge по score DESC → top 8
   │
   ▼
LLM (gpt-4o, temp=0.3) с system-prompt "отвечай на русском,
ссылайся на источник, не выдумывай"
   │
   ▼
MediaChatResponse {
  answer: "...",
  sources: [
    { source_type, title, snippet, score, ref_id }
  ]
}
```

Параметры поиска: `TOP_PER_COLLECTION=4`, `TOP_FINAL=8`, `SCORE_THRESHOLD=0.3`.

В UI карточки источников типа `media` **кликабельны** — клик переключает таб на Аудио→STT и открывает транскрипт. Остальные типы (`files`, `biotact`, `dr_berg`, `nutrition`) — plain cards с типом, названием и процентом релевантности.

---

## Frontend

### Раздел «Медиа» в `BiotactDashboard.jsx`

Три таба сегментированным контроллером:

- **Изображение** — заглушка «Скоро» (placeholder)
- **Видео** — заглушка «Скоро»
- **Аудио** — активный раздел; внутри переключатель режима:
  - **Аудио → Текст** — dropzone + `<audio controls>` + «Транскрибировать» + textarea + copy/download + **карточка истории с пагинацией** (20 на страницу, delete у своих записей, индикатор «индексируется»)
  - **Текст → Аудио** — textarea до 4096 символов (или upload `.txt`) + селектор голоса + «Синтезировать» + `<audio>` + «Скачать .mp3»

### Chat-sidebar

Справа всегда виден (паттерн проекта). Для `section === 'media'`:
- Заголовок «Медиа Поиск» · «По всем источникам»
- Быстрые подсказки: «О чём говорили на последней встрече?», «Что было про пробиотики?», «Найди упоминание штаммов»
- Placeholder инпута: «Ищи по записям и базам...»
- Ответы AI показывают блок «Источники» снизу с кликабельными карточками media-записей

---

## Ограничения и предпосылки

1. **Whisper** — официальный лимит 25 MB на файл. Split в backend автоматически режет на куски по 10 минут через ffmpeg `libmp3lame 64k mono`.
2. **OpenAI TTS** — 4096 символов на запрос, 6 голосов (nova, alloy, echo, fable, onyx, shimmer). Формат вывода — mp3.
3. **Enrichment может вернуть невалидный JSON** — тогда сохраняется запись с MVP-title (первое предложение или дата), `is_indexed=false`. Переиндексация возможна вручную через вызов `_index_transcription_background(transcription_id)`.
4. **Концурентность**: один split-upload одновременно (`_LONG_TRANSCRIBE_SEM=1`). Одна индексация одновременно (`_indexing_semaphore=1` в indexing_service).
5. **Клики на источники**: только `media:*` ведут на оригинал. Для `files`, `biotact`, `dr_berg`, `nutrition` — plain-cards без перехода.
6. **Узбекский**: Whisper официально не поддерживает. На узбекском транскрипт будет плохого качества.
7. **Видимость**: все авторизованные видят всю историю и ищут по всем транскриптам. Фильтра по ролям/группам нет.
8. **Image / Video табы** — UI-заглушки, endpoints не реализованы. Генерация изображений/видео — отдельные задачи.

---

## Техдолг

- `modules/media/utils.py::translate_to_english` — копия из `api/v1/knowledge.py`. Вынести в общий `services/rag/utils.py`.
- Nginx-конфиг `client_max_body_size 300M` применяется вручную на сервере. Snapshot лежит в `deploy/nginx/core.biotact.uz.conf`, но не автоматически синхронизируется через CD.
- Нет rerank-слоя (cross-encoder / Cohere Rerank) — полагаемся на чистый косинус. При росте базы можно добавить.
- Нет переиндексации старых записей через API. Сейчас только вручную через `docker exec biotact-api python -c ...`.
- Нет retry на OpenAI rate-limit (429). Обычно хватает, но при пиковой нагрузке может упасть.
- Нет streaming ответа LLM в chat (SSE/WebSocket) — blocking request.
- Deploy не graceful: длинные in-flight upload'ы при рестарте контейнера получают 502. Решение — `stop_grace_period` + uvicorn `--timeout-graceful-shutdown`.
- Нет кликабельности для не-media источников в чате (files / biotact / dr_berg / nutrition).

---

## Эксплуатация

### Переиндексировать запись вручную

```bash
ssh bcv2 "docker exec biotact-api python -c \"
import asyncio
from biotact.modules.media.router import _index_transcription_background
asyncio.run(_index_transcription_background('<transcription_id>'))
\""
```

### Посмотреть состояние записей

```sql
SELECT transcription_id, LEFT(title, 60) AS title, is_indexed, chunk_count,
       length(text) AS text_len, jsonb_array_length(keywords) AS kw_cnt, created_at
FROM media_transcriptions
ORDER BY created_at DESC
LIMIT 10;
```

### Посмотреть Qdrant

```python
# внутри контейнера biotact-api
from qdrant_client import AsyncQdrantClient
client = AsyncQdrantClient(host='qdrant', port=6333)
await client.get_collection('media_transcriptions')  # → points_count и т.д.
```

### Nginx — увеличить лимит загрузки

Редактировать `/etc/nginx/sites-enabled/biotact-core-v2`, `location /api/`, строку `client_max_body_size 300M;`. Проверить и перезагрузить:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

После изменения обновить snapshot в `deploy/nginx/core.biotact.uz.conf` и коммитнуть.
