# Модуль «Документы» — File Storage + RAG Chat

> Общая площадка обмена документами с AI-поиском по содержимому.
> Дата: 2026-04-02 | Ветка: main | CI: Lint + Tests green

---

## Что сделано

### Backend (8 файлов, ~1700 строк)

```
src/biotact/modules/filestorage/
├── __init__.py            — описание модуля
├── models.py              — Folder + File (SQLAlchemy 2.0)
├── schemas.py             — Pydantic request/response (14 схем)
├── repository.py          — FileRepository (async CRUD, 16 методов)
├── file_service.py        — Upload/download/delete на FS
├── indexing_service.py    — Parse → chunk → embed → Qdrant
├── vector_store.py        — FileVectorStore (коллекция user_files)
├── chat_service.py        — OpenAI Function Calling + RAG
└── router.py              — 15 REST endpoints + background tasks
```

### Frontend (2 файла, ~570 строк добавлено)

```
frontend/dashboard/src/
├── api.js                 — 14 новых API-функций
└── BiotactDashboard.jsx   — модуль "Документы" в 3-column layout
```

### Миграция

```
migrations/versions/e3f4g5h6i789_add_folders_and_files.py
```

---

## Архитектура

### Общий доступ

Все файлы и папки видны всем авторизованным пользователям. Это **общая площадка**, не персональное хранилище. Удалять может только автор (uploaded_by).

### Модели данных (PostgreSQL)

```
folders
├── id             SERIAL PK
├── folder_id      UUID UNIQUE INDEX        — бизнес-ключ
├── name           VARCHAR(255)
├── parent_id      FK → folders.id CASCADE  — NULL = корень
├── uploaded_by    FK → users.id CASCADE    — автор
├── created_at / updated_at
└── UNIQUE(parent_id, name) nulls_not_distinct

files
├── id             SERIAL PK
├── file_id        UUID UNIQUE INDEX
├── name           VARCHAR(500)
├── original_name  VARCHAR(500)
├── mime_type      VARCHAR(100)
├── size           BIGINT
├── storage_path   TEXT                     — /data/uploads/{uuid}/{name}
├── folder_id      FK → folders.id CASCADE
├── uploaded_by    FK → users.id CASCADE
├── is_indexed     BOOLEAN DEFAULT false    — проиндексирован в Qdrant?
├── chunk_count    INT DEFAULT 0
├── share_token    VARCHAR(64) UNIQUE NULL  — для публичных ссылок
├── created_at / updated_at
```

### Qdrant — коллекция `user_files`

- Размерность: 3072 (text-embedding-3-large)
- Distance: Cosine
- Payload: `file_id`, `file_name`, `chunk_index`, `content`
- Создаётся автоматически в lifespan startup
- Поиск без фильтра по user_id (общая платформа)

### API Endpoints

| Метод | URL | Auth | Описание |
|-------|-----|------|----------|
| POST | `/api/v1/files/folders` | JWT | Создать папку |
| GET | `/api/v1/files/folders?parent_id=` | JWT | Список папок |
| PATCH | `/api/v1/files/folders/{id}` | JWT | Переименовать (только автор) |
| DELETE | `/api/v1/files/folders/{id}` | JWT | Удалить + содержимое (только автор) |
| POST | `/api/v1/files/upload?folder_id=` | JWT | Загрузить файл (multipart) |
| GET | `/api/v1/files/?folder_id=` | JWT | Список файлов |
| GET | `/api/v1/files/{id}/download` | JWT | Скачать файл |
| DELETE | `/api/v1/files/{id}` | JWT | Удалить файл (только автор) |
| POST | `/api/v1/files/{id}/share` | JWT | Создать share-ссылку (только автор) |
| DELETE | `/api/v1/files/{id}/share` | JWT | Отозвать share-ссылку |
| GET | `/api/v1/files/shared/{token}` | Нет | Скачать по share-ссылке |
| GET | `/api/v1/files/breadcrumbs/{id}` | JWT | Навигация (цепочка папок) |
| GET | `/api/v1/files/stats` | JWT | Статистика (файлов, объём, indexed) |
| POST | `/api/v1/files/chat` | JWT | Чат с AI по документам (RAG) |

### Индексация (BackgroundTask)

```
Upload файла → сохранить на диск → записать в БД → ответить 201
    ↓ (background)
Parse (pymupdf / python-docx / openpyxl / plain text)
    ↓
Chunk (1000 символов, overlap 200, sentence boundary)
    ↓
Embed (OpenAI text-embedding-3-large, batch по 100)
    ↓
Upsert в Qdrant (коллекция user_files)
    ↓
UPDATE files SET is_indexed=true, chunk_count=N
```

- Semaphore(1) — одновременно индексируется максимум 1 файл (защита RAM)
- Лимит: 20 MB на файл
- Форматы: PDF, DOCX, DOC, TXT, MD, CSV, JSON, XLSX, XLS

### Chat Flow (FilesChatService)

```
User: "Какая выручка за Q1?"
    ↓
1. OpenAI (gpt-4o) с tool: search_documents, tool_choice: auto
    ↓
2. LLM решает вызвать search_documents(query="выручка Q1")
    ↓
3. Embed query → Qdrant search (top 5, threshold 0.3) → чанки
    ↓
4. Второй вызов LLM с контекстом из найденных чанков
    ↓
5. Ответ с указанием файлов-источников
```

Автономный handler — **не использует** module_registry / ChatService / CommandExecutor. Паттерн как marketing/chat — отдельный endpoint.

### Frontend

- **GNOME Adwaita-style папки** — SVG иконки, голубой (#3584e4), flat front, drop-shadow
- **Карточки файлов** — цветные badge по типу (PDF красный, DOCX синий, XLSX зелёный)
- **Toolbar** — кнопки "Загрузить" и "Папка", breadcrumbs навигация, stats
- **Drag & Drop** — overlay при перетаскивании файлов
- **Статус индексации** — `✓ indexed` (зелёный) / `⏳ indexing` (голубой, пульсирующий)
- **Удаление** — кнопка появляется при hover (только для автора)
- **Чат sidebar** — режим "Документы AI", quick actions, source badges

---

## Что осталось (для production deploy)

### Обязательно перед деплоем

1. **Alembic миграция на сервере:**
   ```bash
   ssh 7demo
   cd /opt/biotact-core-v2
   docker compose exec api alembic upgrade head
   ```

2. **Установить парсеры документов** (в Dockerfile или requirements.txt):
   ```
   pymupdf>=1.25.0
   python-docx>=1.1.0
   openpyxl>=3.1.0
   ```

3. **Docker volume для uploads:**
   ```yaml
   # docker-compose.prod.yml
   services:
     api:
       volumes:
         - uploads_data:/data/uploads
   volumes:
     uploads_data:
   ```

4. **Починить deploy (nginx SSL):**
   Сертификат `nutrigen.biotact.uz` отсутствует на bcv2. Либо получить через certbot, либо убрать этот nginx site. Это не связано с filestorage — существующая проблема.

### Рекомендуется (после MVP)

5. **Переиндексация при старте** — в lifespan добавить: найти файлы с `is_indexed=false` и запустить индексацию. Сейчас если сервер рестартнёт во время индексации — файл останется неиндексированным.

6. **Лимиты из Settings** — перенести `MAX_FILE_SIZE_BYTES`, `UPLOAD_BASE_DIR`, `CHUNK_SIZE` из hardcode в `config.py` (env variables).

7. **Qdrant cleanup при удалении папок** — реализовано, но рекурсия через N+1 SQL. При глубокой иерархии заменить на `WITH RECURSIVE` CTE.

8. **Polling is_indexed** — фронтенд не обновляет статус индексации автоматически. Добавить polling каждые 5 секунд для файлов со статусом `indexing`.

9. **Превью файла** — модалка с метаданными, первые строки текста, кнопка скачать.

10. **Поиск через UI** — input в toolbar для фильтрации файлов по имени (клиентский) + полнотекстовый поиск (серверный).

---

## Коммиты

```
568b79a feat(filestorage): add Folder + File models, migration, schemas, repository
dc9c3c4 feat(filestorage): add FileService, REST router, register in API
b997bcf feat(filestorage): add indexing pipeline, RAG chat, Qdrant vector store
b91cf3a feat(filestorage): add Documents UI — file manager + chat sidebar
163005f feat: add Documents module — shared file storage with RAG chat (merge)
407ab51 fix(filestorage): resolve mypy and ruff format CI failures
baea84d fix(filestorage): fix remaining mypy errors (arg-type, unused-ignore)
```

## CI Status

- **Lint (ruff + mypy):** green
- **Tests (pytest 141):** green
- **Deploy:** red (не связано — nginx SSL cert для nutrigen)
