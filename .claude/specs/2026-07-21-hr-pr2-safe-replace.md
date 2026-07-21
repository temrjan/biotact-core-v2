# PR-2 — Безопасная замена шаблона (safe replace)

> Выжимка под конкретный PR (прецедент #50/#51). Umbrella на 3 PR:
> `2026-07-21-hr-templates-download-replace.md` (рабочий untracked).
> Статус: **Гейт-1 APPROVED** (в umbrella). Кресло: Инженер.

## Цель
При замене шаблона (HR качает → правит в Word → грузит обратно) не дать тихо залить
битый или обеднённый шаблон в прод.

## Скоуп — что входит
- Backend:
  - `_assert_docx_openable(path)` — нечитаемый DOCX (python-docx не открывает) → **422**,
    ставится ДО extract/scan (fail-fast); `scan_template_fields` остаётся fail-soft.
  - При загрузке в категорию с активной версией: `dropped = set(old.template_fields or []) −
    set(new_fields)`; если непусто и нет `confirm=true` → **409** со структурным
    `detail={"code":"dropped_placeholders","dropped":[...],"message":...}`.
  - `confirm: bool` query-параметр на `POST /hr/library`; версионирование вынесено в
    `_insert_new_version` (граница `IntegrityError`→409 сохранена).
- Frontend: `api.hrUploadTemplate(file, category, confirm)`; `handleHrUpload` ловит 409
  dropped → `confirm()` со списком полей → повтор с `confirm=true`; кнопка «Заменить» в строке
  (преселект категории + пикер).

## Что ЯВНО не входит
- Структурная валидация вёрстки / `td_verify`, авто-починка нумерации, хранение `data`.

## Затронутые файлы
- `src/biotact/modules/hr/library/{service.py,router.py}`
- `frontend/dashboard/src/{api.js,BiotactDashboard.jsx}`
- **тесты:** `tests/factories.py` (new), `tests/unit/hr/test_template_replace.py` (new, 5),
  + миграция fake-docx→real-docx в 6 файлах (см. «Отклонение»).

## Критерии приёмки — все выполнены
- Битый docx → 422, на диск/в БД ничего не попало.
- Замена с потерей поля без confirm → 409 + `dropped`; с `confirm=true` → 201, `version` поднят,
  старая деактивирована, `superseded_by_id` проставлен.
- Замена без потерь (или добавление поля) → 201 без трения. Первая загрузка → 201.

## Definition of Done — выполнен
- ✅ ruff `src tests` · format `--check` (201) · mypy `src` (137) — зелёные.
- ✅ `pytest -m "unit or not integration"` → **493 passed, 0 failed** (podman PG).
- ✅ Интеграционные (не в CI): 3 мигрированных файла прогнаны локально — 21 passed.
- ✅ Frontend: `npm run build` ✅; eslint — новых проблем нет (5 pre-existing на main).
- ✅ Само-ревью: security-review чисто · python-review 0 crit/err (1 suggestion применена: rename
  `_assert_docx_openable`).
- ⏳ merged / ветка удалена — после Гейт-2 + пуша (на Капитане).

## Тест-план — исполнен
red→green доказан дважды (глушением обоих гвардов): corrupt `→ не-422` и dropped `→ не-409`
падают, восстановление → зелёные. Покрытие: corrupt→422, first-upload→201, dropped→409+detail,
confirm→201+version, add-field→201.

## Отклонение от плана (и почему)
- **Миграция тест-фикстур fake→real docx.** Новый гвард `_assert_docx_openable` отвергает
  `b"PK..."`-заглушки, которыми 6 тест-файлов грузили «docx». Перевёл их на настоящий
  минимальный docx через общий `tests/factories.make_docx_bytes`. Это вынужденное следствие
  ратифицированного гварда (плюс dropped-тесты и так требуют docx с плейсхолдерами). Задет и
  `test_upload_security.py::test_db_failure_unlinks_partial_file` (полный гейт поймал: fake docx
  теперь падал на гварде раньше мокнутого `db.flush`) — payload переведён на real docx.
- **Рефактор `_insert_new_version`.** Вставки гвардов подняли `upload_template` за лимит
  `PLR0915` — вынес версионирование в хелпер (чиню причину, не подавляю).
