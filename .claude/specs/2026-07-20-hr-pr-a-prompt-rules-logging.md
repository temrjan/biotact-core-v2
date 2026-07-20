# PR-A′ — единый источник per-category правил извлечения + наблюдаемость (PII-safe логи)

> Гейт-1 спека. APPROVED WITH NITS Ревьюером; МИНОР-1/2/3 + НИТ внесены (этот раунд, ре-ревью не нужно).
> Ожидает финальный «go» Капитана + его слово по развилке actor (email vs user id). Код — только после «go».
> Пишется через `/python`; тест-план — через `/testing`; перед Гейтом-2 — `/python-review`.
> Скоуп ратифицирован в своде `2026-07-20-hr-fixes-program-plan.md`.

## Цель — один абзац
Устранить рассинхрон двух промптов извлечения (главный `SYSTEM_PROMPT` знает per-category правила,
fallback `_EXTRACTION_PROMPT_TEMPLATE` — нет, из-за чего `GPD_NUMBER/GPD_DATE` и др. не доходят до `data`)
через ОДИН источник правил, из которого собираются ОБА промпта. В том же заходе — вернуть наблюдаемость
прода (сконфигурировать логирование, сейчас его нет → диагностика чата теряется в `lastResort`), **не создав
PII-утечку** в `docker logs`. PR-A′ НЕ закрывает режим «молча-неверно» (корень → form-first) — только убирает
рассинхрон промптов и делает провалы видимыми (какие поля не пришли) и безопасными для логов.

## Скоуп PR — что входит / что ЯВНО не входит
**Входит:**
1. **Единый источник правил** (новый `chat/field_rules.py`): общий блок (COMMON) + per-category правила
   (текст, сейчас зашитый инлайн в `SYSTEM_PROMPT`), вынесенный as-is (смысл правил НЕ меняем). Функции:
   `build_system_rules()` (COMMON + все категории) и `build_extractor_rules(category)` (COMMON + одна категория).
2. **`SYSTEM_PROMPT`** собирается из `build_system_rules()` — детерминированно, один раз при импорте
   (стабильная строка, чтобы авто-кэш OpenAI не ломался; volatile-данных не добавляем).
3. **`extract_data_from_context`** принимает `category`, строит промпт из `build_extractor_rules(category)`;
   `generate_hr_document` пробрасывает `db_template.category`.
   **[МИНОР-2] Неизвестная категория** (новый шаблон/категория из БД) → деградация до COMMON-блока БЕЗ падения
   (никакого `KeyError` на fallback-пути — том самом, который чиним). Покрыто тестом.
4. **Логирование** (новый `core/logging.py::configure_logging()`, `dictConfig`): INFO → stdout, формат
   `time level logger msg`; уровень из `LOG_LEVEL` (дефолт INFO). Вызов в `main.py` на старте. Не конфликтует
   с логгерами uvicorn.
   **ОТКЛОНЕНИЕ от свода (с обоснованием, ратификация Капитана):** включаем INFO НЕ для `biotact` целиком, а
   для **`biotact.modules.hr`**. Причина — аудит ниже: `biotact`-wide INFO «оживил» бы `documents/chat_service.py:192`
   (`args=%s` в documents-чате, тот же класс PII-утечки, ДРУГОЙ модуль, вне скоупа PR-A′). HR-scope даёт ровно
   цель («видеть диагностику HR-чата») без утечки в неаудированном модуле. Расширение на другие модули — отдельная
   задача после их PII-аудита.
5. **PII-safe логи HR-модуля** (аудит ВСЕХ 30 logger-сайтов, таблица ниже). Убрать значения полей на 4 сайтах,
   усилить 1, остальные — safe.
6. **[МИНОР-3]** `chat/documents.py:55`: сейчас только счётчики `%d/%d missing` — расследование YUNUSOV упёрлось
   ровно в «какие». Имена полей НЕ PII → логировать `missing=[имена]`. Одна строка, высокий ROI.
7. **Тесты:** сборка промптов (правила категории в обоих + деградация) + caplog «нет значений полей в логах»
   (happy-path И **[НИТ] падающий рендер** — `logger.exception` не должен протащить значения через traceback).

**ЯВНО НЕ входит:** правка `.docx`-шаблонов (PR-B); form-first форма; изменение СМЫСЛА per-category правил;
UTC-дефолт дат, «первый tool-call», смена модели (бэклог); модуль documents и прочие не-HR (см. «Замечено»).

## Аудит логов HR-модуля (30 сайтов)
**FIX — логируют значения полей (PII), убрать:**
| сайт | сейчас | стало |
|------|--------|-------|
| `chat/router.py:29` | `message=%r` (сырой текст с паспортом/адресом) + email | actor(user id) + `msg_len=%d`, без содержимого |
| `chat/service.py:146` | `args=%s` (полный JSON значений) | `tool=%s args_keys=%s` (только ключи) |
| `chat/documents.py:92` | `employee=%s` (ФИО) | `template=<cat/id> fields=%d`, без ФИО |
| `documents/router.py:114` | `filename=%s` (`req.filename`, «ТД_Иванов.docx») | `template_id=%d fields=%d`, без filename |

**ENHANCE:** `chat/documents.py:55` — добавить `missing=[имена полей]` (не PII) [МИНОР-3].

**SAFE — оставить (значений полей нет):**
- Счётчики/токены/раунды: `extractor.py:54`, `service.py:133`, `retention.py:106/108/127`.
- Пути с uuid/hash-именами: `renderer.py:68`, `documents/router.py:210/212/216`, `library/service.py:242/480`,
  `library/scanner.py:25/28/42`, `library/service.py:128`.
  (`library/service.py:242` — имена шаблонов + имена полей, не PII; `scanner` — имена плейсхолдеров.)
- `exception`-сайты (`documents.py:100`, `extractor.py:57`, `service.py:82/128`, `renderer.py:107`,
  `scanner.py:45`, `retention.py:66/77`) — сообщения безопасны; риск traceback покрыт тестом падающего рендера.

## Замечено, не трогаю (вне скоупа PR-A′)
- `documents/chat_service.py:192` (`Documents chat tool=%s args=%s`) — тот же класс PII-утечки в модуле
  `documents`. В PR-A′ НЕ активируется (INFO scope = только `biotact.modules.hr`). Отдельная задача:
  PII-аудит модуля documents ДО включения его INFO.

## Затронутые файлы
- NEW `src/biotact/core/logging.py`; `src/biotact/main.py` (вызов).
- NEW `src/biotact/modules/hr/chat/field_rules.py`.
- `chat/prompts.py`, `chat/extractor.py`, `chat/documents.py`, `chat/service.py`, `chat/router.py`,
  `documents/router.py`.
- NEW `tests/unit/hr/test_field_rules_prompts.py`, `tests/unit/hr/test_hr_log_pii.py`.

## Критерии приёмки — «PR готов, когда…»
- Для `nda_gpd` правило `GPD_NUMBER/GPD_DATE` есть в СОБРАННОМ extractor-промпте (тест RED без фикса).
- Оба промпта берут правила из ОДНОГО источника (нет дублирующего текста правил).
- `build_extractor_rules(<неизвестная категория>)` возвращает COMMON без исключения (тест).
- `SYSTEM_PROMPT` — стабильная строка (повторная сборка идентична; кэш не ломается).
- `biotact.modules.hr` INFO-логи появляются в stdout (ручная проверка, вывод приложен).
- Ни один из 4 FIX-сайтов не логирует значения полей: caplog с sample-PII (`AE1234567`, телефон, ФИО) —
  значений нет ни в happy-path, ни в падающем рендере; ключи/счётчики/имена полей — можно.
- `ruff`, `mypy`, `pytest` (HR unit+integration) — зелёные, вывод приложен.

## Definition of Done
merged / ветка удалена / тесты+линт+тайпчек зелёные / спека закрыта. Доков к правке нет (при желании — строка
про `LOG_LEVEL` в README/CLAUDE — на усмотрение).

## Тест-план (детализирую через `/testing` перед написанием)
- `tests/unit/hr/test_field_rules_prompts.py`: правило ГПД в `build_extractor_rules("nda_gpd")`;
  правила td в `build_extractor_rules("td_osnovnoy")`; COMMON в обоих; неизвестная категория → COMMON без падения;
  `SYSTEM_PROMPT` содержит все категории; повторная сборка идентична.
- `tests/unit/hr/test_hr_log_pii.py` (caplog): happy-path генерации с sample-PII → значений нет; **падающий
  рендер** (мок кидает исключение со значением в сообщении) → значение не попадает в лог.
- `ruff check . && mypy src/ && pytest tests/unit/hr tests/integration/hr` — всё зелёное.
- Ручное: `LOG_LEVEL=INFO` локально → дернуть чат → `biotact.modules.hr` INFO без значений полей.

## Развилка Капитану (до кода)
- **Actor в `router.py`: email vs внутренний user id.** Рекомендация Ревьюера (и моя) — **user id**: тот же
  принцип минимизации PII, что и весь PR; `current_user.id` уже доступен (`router.py:31`), трассируемость через
  JOIN та же. Факт-переключатель: если внешний комплаенс требует email в аудит-логе — тогда email.
- **Отклонение по scope логов** (`biotact.modules.hr` вместо `biotact`, п.4) — подтвердить.
