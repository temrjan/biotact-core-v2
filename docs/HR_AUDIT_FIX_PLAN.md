# HR Module — План правок (post-/check)

**Дата:** 2026-06-08
**Источник:** аудит в чате + 13 находок `/check`
**Целевой репозиторий:** `biotact-core-v2` (HR module), миграции + код + тесты
**Статус:** план утверждён, ожидает старта Фазы 1

---

## 1. Контекст и цель

HR-модуль (`src/biotact/modules/hr/`, 3 385 LOC, 24 файла) обрабатывает PII (паспорта, зарплаты, адреса) трёх HR-пользователей BIOTACT. Аудит выявил:

- **3 категории P0:** IDOR на скачивании, отсутствие RBAC, path traversal в upload, prompt injection через history
- **Архитектурные:** `chat/service.py` 663 LOC с noqa-suppressed complexity, digest как чужая подсистема внутри HR, мёртвый код
- **Качество:** 0 тестов, 24 широких `except Exception`, хардкоды моделей/имён, дубли DB-запросов
- **Эксплуатационные:** прямые правки `.docx` на диске разрывают БД-кэш `template_fields`

## 2. Open questions — резолвлено

| # | Вопрос | Решение |
|---|---|---|
| 1 | Кто видит библиотеку шаблонов | Только HR (`HR_ALLOWED_EMAILS`). Обычным сотрудникам — нет. |
| 2 | `hr_admin` vs `hr_user` | **Одна роль** для 3 человек. Разделение — когда команда вырастет до 5+. |
| 3 | Legacy `/download-docx` | Удалить, если фронт не вызывает (grep в PR-6). |
| 4 | Retention | **Per-category:** статутные (ТД/Приказ/МО) хранить вечно, транзитные (NDA, Соглашение PD/возмещение, доп.соглашение) — 30 дней hard-delete. |
| 5 | Аудит-лог `hr_audit_log` | Не нужен. `logger.info` + `journalctl` достаточно для 3 пользователей. |

## 3. /check — итог 13 находок

**Применено в план:**

| # | Находка | Severity | Действие |
|---|---|---|---|
| 1 | OpenAI prompt-caching syntax (cache_control = Anthropic) | blocking | PR-13 переписан: split prefix/suffix + замер `cached_tokens` |
| 2 | python-magic не в зависимостях | important | Заменено на stdlib magic-byte check (8 байт) |
| 3 | `tests/security/` папки нет | nit | Тесты → `tests/integration/test_hr_security.py` |
| 4 | NOT NULL DEFAULT миграция → outage | blocking | Колонку убрали целиком (Finding 8) |
| 5 | Race condition в версионировании | important | `UNIQUE (category) WHERE is_active` + `FOR UPDATE` |
| 6 | 30-day retention vs трудовое право | important | Per-category retention (см. resolution #4 выше) |
| 7 | PR-4: 5 файлов — over-engineered | suggestion | Свернули до 3: `service / categories / prompts` |
| 8 | RBAC через БД для 3 юзеров — overkill | suggestion | Заменено на `HR_ALLOWED_EMAILS` env-var |
| 9 | `git mv digest/` не проверяет docker/CI/env | important | PR-5 step 0: full-repo grep по 8 расширениям |
| 10 | PG версия не зафиксирована | suggestion | PR-7 docstring: assert PG ≥11 |
| 11 | "14 PR" не сходится | nit | Перенумеровано: **15 PR** |
| 12 | Фронт не обновится сам | important | Добавлена явная out-of-scope пометка |
| 13 | Snapshot-тест non-deterministic из-за `datetime.now()` | important | PR-4 step 0: inject clock + `freezegun` в dev-deps |

## 4. План по фазам и PR

### Out-of-scope для backend-аудита (отдельные тикеты)
- Скрытие HR-меню в `frontend/dashboard` для non-HR пользователей.
- Новый UX для 403/404 ответов RBAC.

### Process для каждого PR
1. Перед началом — `/python` standards load (per CLAUDE.md «Codex First»).
2. Ветка: `hr/p<N>-<slug>` из `main`.
3. PR с описанием → CI (lint + tests + deploy) → review → merge.
4. После мержа — обновить `STATUS.md` в `hr-module/`.

---

### Фаза 1 — P0 безопасность (БЛОКИРУЮЩАЯ для прода)

#### PR-1 · `hr/p1-rbac-env-allowlist` (~50 LOC)

**Goal:** ограничить HR-эндпоинты списком email из `.env`.

**Шаги:**
1. `core/dependencies.py`:
   ```python
   def require_hr_email(current_user: CurrentUserDep) -> User:
       allowlist = {e.strip().lower() for e in settings.hr_allowed_emails.split(",") if e.strip()}
       if current_user.email.lower() not in allowlist:
           raise HTTPException(status.HTTP_403_FORBIDDEN, "HR access required")
       return current_user
   RequireHREmailDep = Annotated[User, Depends(require_hr_email)]
   ```
2. `core/config.py:Settings.hr_allowed_emails: str = ""` (csv).
3. `.env.example` + прод `.env` на bcv2: `HR_ALLOWED_EMAILS=a@biotact.uz,b@biotact.uz,c@biotact.uz` (емейлы согласовать с Шефом до мержа).
4. Юнит-тест: 3 кейса (email в списке → пускает, не в списке → 403, пустой env → 403 для всех кроме явного админа).

**Acceptance:**
- `pytest tests/unit/test_require_hr_email.py` — PASS.
- Без env-var все HR endpoint'ы возвращают 403 (fail-closed).

**Risk:** забыл прописать email в `.env` → HR заблокирован. **Mitigation:** деплой проверяет `len(allowlist) >= 1` в startup; иначе FAIL fast в логах.

**Rollback:** `git revert`, `.env` пуст → старый CurrentUserDep continues to pass auth-only.

---

#### PR-2 · `hr/p2-rbac-apply-and-filter` (~250 LOC + tests)

**Goal:** заменить `CurrentUserDep` → `RequireHREmailDep` на всех HR endpoint'ах + фильтрация документов по `created_by` (всё HR-команда видит всё, т.к. одна роль; никаких per-user фильтров).

**Шаги:**
1. `library/router.py`, `chat/router.py`, `documents/router.py`: глобальная замена `CurrentUserDep` → `RequireHREmailDep` на POST/GET/DELETE.
2. `documents/router.py::download_rendered`: SELECT по `file_id`, если запись не найдена → 404 (без палева существования).
3. `documents/router.py::list_documents` и `delete_document`: без фильтра по owner (все HR равны).
4. Index: `CREATE INDEX ix_hr_documents_file_id_lookup ON hr_documents(file_id)` (уже unique → бесплатно).
5. Acceptance тест (integration):
   - User c email в allowlist → 200 на всех endpoint'ах.
   - User c email не в allowlist → 403 на всех.
   - `download_rendered(file_id="nonexistent")` → 404 (не 200, не 500).

**Risk:** существующие frontend-вызовы для non-HR упадут в 403 — это и есть цель. **Mitigation:** см. out-of-scope frontend задачу.

---

#### PR-3 · `hr/p3-input-hardening` (~250 LOC + tests)

**Goal:** закрыть path traversal, DoS, prompt injection, fake DOCX. Без новых зависимостей.

**Шаги:**

1. **Filename sanitize** — `library/service.upload_template`:
   ```python
   import os
   raw_name = file.filename or "unknown"
   safe_basename = os.path.basename(raw_name.replace("\\", "/"))  # cross-platform
   ext = safe_basename.rsplit(".", 1)[-1].lower() if "." in safe_basename else ""
   if ext not in ("docx", "pdf", "txt", "md"):
       raise HTTPException(400, "Unsupported file type")
   storage_name = f"{uuid.uuid4().hex}.{ext}"  # на диске только uuid.ext
   file_path = UPLOAD_DIR / storage_name
   # name в БД — safe_basename (для отображения в UI)
   ```

2. **Streaming size check + magic bytes** (stdlib only, no python-magic):
   ```python
   MAX_UPLOAD = 20 * 1024 * 1024  # 20 MB
   MAGIC_BYTES = {
       "docx": b"PK\x03\x04",  # ZIP
       "pdf":  b"%PDF-",
   }
   first_chunk = await file.read(1024)
   if ext in MAGIC_BYTES and not first_chunk.startswith(MAGIC_BYTES[ext]):
       raise HTTPException(400, "File content does not match declared type")
   total = len(first_chunk)
   with file_path.open("wb") as f:
       f.write(first_chunk)
       while chunk := await file.read(65536):
           total += len(chunk)
           if total > MAX_UPLOAD:
               f.close()
               file_path.unlink(missing_ok=True)
               raise HTTPException(413, "Upload too large (>20 MB)")
           f.write(chunk)
   ```

3. **Chat history schema** — `chat/router.py`:
   ```python
   class ChatMessage(BaseModel):
       role: Literal["user", "assistant"]
       content: str = Field(min_length=1, max_length=5000)
   class HRChatRequest(BaseModel):
       message: str = Field(min_length=1, max_length=5000)
       history: list[ChatMessage] | None = Field(default=None, max_length=20)
   ```
   В `service.py:469` цикл по `history` использует `m.role` / `m.content` напрямую.

4. **Error sanitization** — `documents/router.py:107`:
   ```python
   import secrets
   correlation_id = secrets.token_hex(8)
   logger.exception("render failed template=%d cid=%s", req.template_id, correlation_id)
   raise HTTPException(500, f"Render failed. Reference: {correlation_id}")
   ```

**Acceptance** (`tests/integration/test_hr_security.py`):
- `test_filename_with_traversal_strips_to_basename` — PASS
- `test_upload_oversized_returns_413` — PASS
- `test_fake_docx_extension_rejected` — PASS (даём text-файл с расширением `.docx`)
- `test_history_with_system_role_rejected_422` — PASS (Pydantic Literal валидация)
- `test_render_error_does_not_leak_internals` — PASS (ответ не содержит file_path)

**Risk:** низкий — все изменения дополняют валидацию.

---

### Фаза 2 — Архитектурный refactor

#### PR-4 · `hr/p4-chat-decompose` (~600 LOC moved, +30 net)

**Goal:** разбить `chat/service.py` (663 LOC) на 3 файла, заинжектить clock для детерминизма.

**Целевая структура:**
```
chat/
├── service.py     (~150 LOC — оркестрация process_message + execute_tool)
├── prompts.py     (~150 LOC — build_system_prompt(categories), OPENAI_TOOLS)
└── categories.py  (~250 LOC — DATA: dict[category, CategoryRules] + postprocess fns)
```

**Шаги:**
1. **Step 0 — injectable clock:**
   ```python
   # chat/service.py
   class HRChatService:
       def __init__(self, ..., now_fn: Callable[[], datetime] = lambda: datetime.now(UTC)):
           self._now = now_fn
   # _postprocess_fields(data, category, now): использует переданный now() вместо datetime.now()
   ```
   В тестах — `now_fn=lambda: datetime(2026, 6, 8, tzinfo=UTC)`.

2. `chat/categories.py`:
   ```python
   @dataclass(frozen=True)
   class CategoryRules:
       required_fields: tuple[str, ...]
       defaults: dict[str, str]
       postprocess: Callable[[dict[str,str], datetime], dict[str,str]]
       field_rules_for_llm: str
   CATEGORIES: dict[str, CategoryRules] = {
       "td_osnovnoy": CategoryRules(...),
       "td_sovmestitelstvo": CategoryRules(...),
       # ... 11 категорий
   }
   ```
3. `chat/prompts.py`:
   ```python
   STATIC_SYSTEM_PROMPT = """..."""  # без template list
   def build_system_prompt(templates: list[Template]) -> str:
       dynamic = "\n".join(f"- id={t.id}..." for t in templates)
       return STATIC_SYSTEM_PROMPT + dynamic
   OPENAI_TOOLS = [...]
   ```
4. `chat/service.py` — только оркестрация, без `_postprocess_fields` (он переехал в categories).
5. Снять `# noqa: PLR0912, PLR0915` в новой структуре — функции стали маленькими.
6. Добавить `freezegun ^= "^1.5.0"` в dev-deps.

**Acceptance:**
- Snapshot test с фиксированной датой через freezegun: `assert render(input) == expected_bytes`. Same in / same out для каждой из 11 категорий.
- `wc -l chat/service.py` ≤ 200.
- `ruff check src/biotact/modules/hr/chat` без suppressions.

**Risk:** разрыв импортов. **Mitigation:** инкрементальный коммит-по-файлу внутри PR.

---

#### PR-5 · `hr/p5-extract-digest` (~100 LOC + git mv)

**Goal:** вынести `digest/` (Telegram-бот) из HR.

**Шаги:**

1. **Step 0 — pre-flight grep:**
   ```bash
   grep -rn 'modules\.hr\.digest\|modules/hr/digest\|hr_digest\|hr/digest' \
     --include='*.py' --include='*.yml' --include='*.yaml' \
     --include='*.toml' --include='*.ini' --include='*.env*' \
     --include='Dockerfile*' --include='*.sh' \
     . > /tmp/digest_refs.txt
   ```
   Зафиксировать список затрагиваемых файлов **в описании PR**.

2. `git mv src/biotact/modules/hr/digest src/biotact/modules/news_digest`.
3. Обновить импорты во всех файлах из step 0.
4. **БД таблицы НЕ переименовываем** (`hr_digest_*` остаются как есть с комментарием в моделях):
   ```python
   class DigestRun(Base):
       __tablename__ = "hr_digest_runs"  # legacy name, kept for migration stability
   ```
5. Acceptance: тот же grep step 0 → 0 matches.

**Risk:** низкий, чистый рефакторинг импортов.

---

#### PR-6 · `hr/p6-dead-code-cleanup` (~100 LOC removed)

**Goal:** убрать legacy и мёртвый код.

**Шаги:**
1. Проверить использование `HR_SYSTEM_PROMPT` из `hr/config.py`:
   ```bash
   grep -rn 'HR_SYSTEM_PROMPT\|hr_config' src/ tests/
   ```
   Если только `from biotact.modules.hr.config import hr_config` в `main.py` без последующего использования объекта — удалить и hr_config, и HR_SYSTEM_PROMPT, и `RAGModuleConfig` импорт.

2. Удалить `extracted_styles` колонку (миграция: `ALTER TABLE hr_templates DROP COLUMN extracted_styles`).

3. Endpoint `POST /hr/documents/download-docx`:
   ```bash
   grep -rn 'download-docx\|text_to_docx' frontend/ src/ tests/
   ```
   Если фронт не вызывает — удалить endpoint + `docx_generator.py` файл целиком.
   Если вызывает — оставить, навесить `RequireHREmailDep`.

4. Перенести все function-level imports в `chat/service.py` и `library/service.py` на топ-уровень.

**Acceptance:** все existing тесты PASS, `wc -l` модуля -200.

---

### Фаза 3 — Версионирование и retention

#### PR-7 · `hr/p7-template-versioning-schema` (~150 LOC + migration)

**Goal:** схема версий шаблонов с race-condition-safe constraints.

**Шаги:**
1. **Pre-flight:** проверить PG версию (`SELECT version()` на bcv2 staging). Зафиксировать в docstring миграции: `# Requires PostgreSQL >=11 (ADD COLUMN NOT NULL DEFAULT metadata-only)`.

2. Миграция (alembic):
   ```sql
   ALTER TABLE hr_templates
     ADD COLUMN version INT NOT NULL DEFAULT 1;
   ALTER TABLE hr_templates
     ADD COLUMN is_active BOOL NOT NULL DEFAULT TRUE;
   ALTER TABLE hr_templates
     ADD COLUMN superseded_by_id INT NULL REFERENCES hr_templates(id) ON DELETE SET NULL;
   ALTER TABLE hr_templates
     ADD CONSTRAINT uq_hr_template_category_version UNIQUE (category, version);
   CREATE UNIQUE INDEX uq_hr_template_active_per_category
     ON hr_templates(category)
     WHERE is_active;
   ```
3. Модели + schemas: добавить `version: int`, `is_active: bool`, `superseded_by_id: int | None`.
4. Backfill — не нужен, текущие 11 шаблонов получат `version=1, is_active=TRUE` через DEFAULT.

**Acceptance:**
- `alembic upgrade head` + `alembic downgrade -1` на staging-копии прод-БД — PASS.
- Попытка вручную INSERT'нуть второй active в той же категории → DB error `unique_violation`.

---

#### PR-8 · `hr/p8-template-versioning-flow` (~300 LOC + tests)

**Goal:** upload bumps version transactionally, rollback endpoint.

**Шаги:**
1. `library/service.upload_template`:
   ```python
   async with db.begin_nested():  # savepoint
       prev = (await db.execute(
           select(HRTemplate)
           .where(HRTemplate.category == category, HRTemplate.is_active == True)
           .with_for_update()
       )).scalar_one_or_none()
       new_version = (prev.version + 1) if prev else 1
       if prev:
           prev.is_active = False
       template = HRTemplate(category=category, version=new_version, is_active=True, ...)
       db.add(template)
       await db.flush()
       if prev:
           prev.superseded_by_id = template.id
   ```
2. `get_template_by_category` → `WHERE category=:c AND is_active=TRUE` (используется LLM tool в чате).
3. Endpoint `POST /hr/library/{id}/rollback` (RequireHREmailDep):
   - Транзакционно: текущий active той же категории → `is_active=False`, target → `is_active=True, superseded_by_id=None`.
4. Endpoint `GET /hr/library/{id}/history` → список всех версий той же категории, отсортированных по `version DESC`.
5. **Обновить процесс правок:** в `STATUS.md` и `memory/project_hr_module_templates_fix.md` зафиксировать: «прямые правки `.docx` на диске запрещены; только через POST /hr/library».

**Acceptance** (integration test):
- Upload v1 → render → результат с v1.
- Upload v2 (та же категория) → render → результат с v2. Версия v1 → `is_active=False, superseded_by_id=v2.id`.
- Rollback к v1 → render → результат с v1. v2 → `is_active=False`.
- Concurrent upload симуляция (2 task'а одновременно через `asyncio.gather`) → один успех, второй `IntegrityError` (поймать в API → 409 Conflict с retry-hint).

---

#### PR-9 · `hr/p9-retention-per-category` (~120 LOC + test)

**Goal:** auto-cleanup транзитных документов через 30 дней; статутные хранить вечно.

**Шаги:**
1. Конфиг `hr_config.retention`:
   ```python
   STATUTORY_CATEGORIES = frozenset({
       "td_osnovnoy", "td_sovmestitelstvo",
       "prikaz_priem", "mat_otvetstvennost",
   })  # не удаляются автоматически
   RETENTION_DAYS_TRANSIENT = 30
   ```
2. APScheduler job в `core/scheduler.py` (cron daily 03:00 UTC):
   ```python
   async def cleanup_expired_hr_documents() -> None:
       cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS_TRANSIENT)
       result = await db.execute(
           select(HRDocument)
           .join(HRTemplate, HRDocument.template_id == HRTemplate.id)
           .where(HRDocument.created_at < cutoff)
           .where(HRTemplate.category.notin_(STATUTORY_CATEGORIES))
       )
       deleted_count = 0
       for doc in result.scalars():
           Path(doc.file_path).unlink(missing_ok=True)
           await db.delete(doc)
           deleted_count += 1
       logger.info("HR retention: deleted %d transient documents (>%dd)", deleted_count, RETENTION_DAYS_TRANSIENT)
   ```
3. **Конкретный список транзитных категорий — согласовать с Шефом** в комментариях PR.

**Acceptance:**
- Integration test: создать 2 doc'а (один с `template.category="td_osnovnoy"`, один `"nda_gpd"`), оба с `created_at = now() - 31d` → запустить job → ТД остался, NDA удалён (запись + файл).

**Risk:** случайное удаление нужного. **Mitigation:** перед физическим `unlink` — лог `WARNING` с file_id; первый месяц мониторить `journalctl` после ночного запуска.

---

### Фаза 4 — Тесты (baseline)

#### PR-10 · `hr/p10-unit-tests` (~400 LOC tests)

**Goal:** unit-coverage чистых функций.

**Покрытие:**
- `num_to_text.num_to_text_uz` — 20+ кейсов: 0, 1, 21, 100, 1000, 1M, 1.5M, отрицательные, граничные scales.
- `num_to_text.num_to_text_ru` — base coverage через num2words sanity.
- `num_to_text.format_salary` — пустая строка, цифры с пробелами, цифры с буквами, ноль.
- `chat.categories.postprocess_<category>` — per-category snapshot: вход → ожидаемый выход. С `freezegun`-заморозкой времени.
- `library.scanner.scan_template_fields` — фикстура DOCX с `{{ FOO }}`, со split runs (Word разрывает placeholder на 2 `<w:r>`), с табличными ячейками.
- `chat.service._parse_int`, `_is_short_date`, `_date_to_full_russian`.

**Acceptance:** `pytest tests/unit/hr/` + `pytest --cov=biotact.modules.hr` ≥ 80% на затронутых файлах.

---

#### PR-11 · `hr/p11-integration-tests` (~500 LOC tests)

**Goal:** полный цикл с mock OpenAI.

**Сценарии:**
1. Upload DOCX → scan → render → download (через `/render` endpoint).
2. Chat flow: HTTPx test client → `POST /hr/chat/message` → AI mock возвращает tool_calls → `/download/{file_id}` → assert bytes ≠ empty.
3. Версионирование: upload v1 → upload v2 (та же категория) → assert render использует v2; rollback → assert использует v1.
4. Mock OpenAI через `respx` или фикстура с pre-canned responses.
5. Real Postgres через `testcontainers` (уже есть в `tests/integration/` setup).

**Acceptance:** CI зелёный, тесты <90s.

---

#### PR-12 · `hr/p12-security-regression-tests` (~250 LOC tests, в `tests/integration/test_hr_security.py`)

**Goal:** регрессионные тесты P0-фиксов (закрывают PR-1, PR-2, PR-3).

**Сценарии:**
- IDOR: HR-user A создаёт документ; не-HR-user (email не в allowlist) → 403 на `GET /download/{file_id}`.
- Несуществующий file_id → 404, не 200 и не 500.
- Path traversal: `POST /library` filename=`../../etc/passwd.docx` → файл на диске = `<uuid>.docx`, оригинал name в БД sanitize'нут.
- Path traversal Windows-style: filename=`..\\..\\etc\\passwd.docx` → тот же sanitize.
- DoS: stream 30 MB upload → 413 Payload Too Large.
- Magic bytes: переименованный txt с расширением `.docx` → 400.
- Prompt injection #1: history с `role: "system"` → 422 Pydantic validation.
- Prompt injection #2: history с `role: "tool"` → 422.
- Error sanitization: render с битым шаблоном → ответ содержит correlation_id, не содержит file_path.

**Acceptance:** все PASS.

---

### Фаза 5 — Качество и оптимизация

#### PR-13 · `hr/p13-config-extraction` (~200 LOC)

**Goal:** hardcode → config / `.env`.

**Шаги:**
1. `core/config.Settings`:
   ```python
   hr_openai_model: str = "gpt-5.4-mini"
   hr_max_tool_rounds: int = 5
   hr_history_window: int = 10
   hr_director_short_latin: str = "ISHMATOV SH.R."
   hr_director_full_latin: str = "ISHMATOV SHERZOD RUSTAMOVICH"
   hr_hr_director_short_latin: str = "KOROTUN O.A."
   hr_upload_dir: Path = Path("data/hr_templates")
   hr_render_dir: Path = Path("data/hr_rendered")
   ```
2. Все хардкоды в `chat/service.py` (model, директор) → читают из `settings`.
3. `documents/router.py:30` (mkdir на import) → перенести в `main.py:on_startup`.

**Acceptance:** при смене директора — правка `.env` + restart, без правок кода и без деплоя.

---

#### PR-14 · `hr/p14-openai-prompt-caching` (~80 LOC)

**Goal:** воспользоваться OpenAI auto-prompt-caching (≥1024 tokens stable prefix).

**Шаги:**
1. `chat/prompts.build_system_prompt`: реструктурировать так, чтобы:
   - **Static prefix** (всегда одинаков): инструкции + список категорий + правила полей. ≥1024 токенов.
   - **Dynamic suffix** (меняется): список загруженных шаблонов с их id и fields.
2. Log: после каждого OpenAI call'а:
   ```python
   cached = getattr(response.usage, "prompt_tokens_details", None)
   cached_tokens = cached.cached_tokens if cached else 0
   logger.info("OpenAI call: prompt=%d cached=%d completion=%d",
               response.usage.prompt_tokens, cached_tokens, response.usage.completion_tokens)
   ```
3. **Никаких `cache_control` маркеров** — OpenAI кеширует автоматически.

**Acceptance:** в логах после 2+ последовательных вызовов `cached_tokens > 0`. Замерить % cached на 10 рендерах.

---

#### PR-15 · `hr/p15-quality-polish` (~150 LOC)

**Goal:** мелочи стиля + edge cases.

**Шаги:**
- `except Exception` → конкретные exception types (24 случая по списку аудита: `OpenAIError`, `OSError`, `IntegrityError`, `ValueError`, `json.JSONDecodeError`).
- Magic numbers → named constants в `chat/service.py`: `MAX_TOOL_ROUNDS`, `HISTORY_WINDOW`, `LOG_ARG_TRUNCATE`.
- `os.path.exists + os.remove` → `Path.unlink(missing_ok=True)` (library/service.py:210, documents/router.py:200).
- `tool_calls[0]` → iterate всех tool_calls (`for tc in choice.message.tool_calls`).
- `hasattr(self, "_messages_context")` → init `self._messages_context: str = ""` в `__init__`.
- `library/router.py:30` `category: str` → `category: Literal["td_osnovnoy", "td_sovmestitelstvo", ...]` (взять из `chat.categories.CATEGORIES.keys()`).
- Pagination на `list_templates` (`page`, `per_page` как в `list_documents`).

**Acceptance:** `ruff check src/biotact/modules/hr` без suppressions, без warnings. `mypy --strict` без новых ошибок.

---

## 5. Сводка PR

| # | PR | Фаза | LOC ≈ | Блокирует прод? |
|---|---|---|---:|---|
| 1 | RBAC via env allowlist | 1 | 50 | **ДА** |
| 2 | RBAC apply | 1 | 250 | **ДА** |
| 3 | Input hardening | 1 | 250 | **ДА** |
| 4 | Chat decompose + clock injection | 2 | 630 (moved) | нет |
| 5 | Extract digest | 2 | 100 | нет |
| 6 | Dead code cleanup | 2 | -200 (removed) | нет |
| 7 | Template versioning schema | 3 | 150 | нет |
| 8 | Template versioning flow | 3 | 300 | нет |
| 9 | Per-category retention | 3 | 120 | нет |
| 10 | Unit tests | 4 | 400 | нет |
| 11 | Integration tests | 4 | 500 | нет |
| 12 | Security regression tests | 4 | 250 | нет |
| 13 | Config extraction | 5 | 200 | нет |
| 14 | OpenAI prompt caching | 5 | 80 | нет |
| 15 | Quality polish | 5 | 150 | нет |
| | **Итого** | | **~3 680** | |

**Порядок мержа:**

```
PR-1 → PR-2 → PR-3   (Фаза 1, последовательно — каждый зависит от предыдущего)
   ├─ PR-4 ── PR-10   (refactor + unit tests параллельно)
   ├─ PR-5
   ├─ PR-6
   ├─ PR-7 → PR-8 → PR-9   (versioning + retention)
   ├─ PR-11             (integration tests, после PR-4)
   ├─ PR-12             (security regression, после Фазы 1)
   └─ PR-13 → PR-14 → PR-15   (полировка, в конце)
```

**Оценка времени (грубо, single engineer):**

- Фаза 1 (P0): 2-3 рабочих дня
- Фаза 2: 3-4 дня
- Фаза 3: 2 дня
- Фаза 4: 3-4 дня
- Фаза 5: 2 дня
- **Итого:** 12-15 рабочих дней + review-циклы

## 6. Открытые пункты до старта

1. **Список email для `HR_ALLOWED_EMAILS`** — подтвердить у Шефа 3 емейла (2 admin + 1 HR).
2. **Финальный список «транзитных» категорий** для PR-9 retention — подтвердить, что NDA / Соглашение PD / возмещение / доп.соглашение можно удалять через 30 дней.
3. **Frontend ticket** — кто заводит и когда (out-of-scope этого плана, но нужно скоординировать).
4. **PostgreSQL версия на bcv2** — `psql -c "SELECT version()"` перед PR-7 (фиксация в docstring миграции).
5. **`POST /hr/documents/download-docx`** — Шеф проверит/спросит фронт-разработчика использует ли. Если нет — удаляем в PR-6.
