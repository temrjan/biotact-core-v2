# PR-1 — Скачивание шаблона (HR template download)

> Выжимка под конкретный PR (прецедент #50/#51). Umbrella-план на 3 PR:
> `2026-07-21-hr-templates-download-replace.md` (рабочий untracked).
> Статус: **Гейт-1 APPROVED + Гейт-2 APPROVED**. Коммит `dd9ddb8`.

## Цель
Дать HR скачать файл активного шаблона одной кнопкой (чтобы поправить в Word и загрузить
обратно) — без разработчика.

## Скоуп — что входит
- Backend: `GET /hr/library/{template_id}/download` → `FileResponse` (имя = `name`,
  media-type по `file_type`; `os.path.exists`→404 на пропавшем файле; auth `RequireHREmailDep`).
- Сервис: `get_template_file(db, id) -> HRTemplate | None` (ORM-строка — роутеру нужны
  `file_path`/`file_type`, которых нет в response-схемах).
- Frontend: `api.hrDownloadTemplate(id, filename)` + кнопка «Скачать» в строке вкладки «Шаблоны».

## Что ЯВНО не входит
- Замена/версии/откат (PR-2/PR-3), правки истории, изменение хранилища, структурная
  валидация вёрстки.

## Затронутые файлы
- `src/biotact/modules/hr/library/router.py`
- `src/biotact/modules/hr/library/service.py`
- `frontend/dashboard/src/api.js`
- `frontend/dashboard/src/BiotactDashboard.jsx`
- `tests/unit/hr/test_template_download.py` (новый, 9 тестов)

## Критерии приёмки — все выполнены
- Скачивание → валидные байты + `Content-Disposition` (имя) + верный media-type (docx/pdf/txt/md).
- Несуществующий id → 404; файл пропал с диска → 404 (не 500).
- Невалидный токен → 401; аутентифицирован, но не-HR → 403 (детерминированные коды).
- `/{id}/download` не перехватывается `/{category}/history`.

## Definition of Done — выполнен
- ✅ ruff `src tests` · ruff format `--check` (199) · mypy `src` (137) — зелёные.
- ✅ `pytest -m "unit or not integration"` → 488 passed, 0 failed (podman PG).
- ✅ Само-ревью: `/security-review` чисто · `/review` 0 blocking/important.
- ✅ Гейт-2 Ревьюера: APPROVED (независимая верификация гейтов + Starlette header-injection по исходнику).
- ⏳ merged / ветка удалена — после пуша (на Капитане).

## Тест-план — исполнен
red→green доказан дважды (эндпоинт `4 failed`→`6 passed`; media-ветка `3 failed`→`9 passed`).
Покрытие: happy-path, 404 (нет id / нет файла), 401, 403, роут-резолвинг, media-type по типам.
Фронт: харнесса нет → ручной `npm run build` ✅ (Ревьюер, 5.40s), eslint-проблемы pre-existing.
