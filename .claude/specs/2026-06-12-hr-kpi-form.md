# HR KPI form — вкладка «KPI» внутри «Подарков» (frontend)

> DISCOVER пройден 2026-06-12 (grill-me: ASSUMPTIONS подтверждены Капитаном без поправок; GUESS по размещению принят; подход A выбран из трёх). Approve word получен.

## Goal — one paragraph

Дать Директору и HR ежемесячный учёт KPI модуля «Подарки» прямо в дашборде: таблица записей по месяцам с процентами выполнения (проценты считает бэкенд) и форма создания/правки. Бэкенд полностью готов (PR #30: CRUD `/api/v1/hr/gifts/kpi`, уникальность месяц+год, 409 на дубль) — задача чисто фронтовая.

## Approach — chosen + why

**Вариант A (утверждён Капитаном):** локальные вкладки внутри `GiftFlowPage` (`tab: 'board' | 'kpi'`), без правок монолита BiotactDashboard и без react-router. Budget/Report (следующая задача) встанет третьей вкладкой этой же панели; общий TabBar выделим только тогда — правило третьего use case.

## Components — list

- `GiftFlowPage.jsx` — tab-state + панель вкладок «Доска» | «KPI»; рендер доски по умолчанию, без изменений её логики
- `src/components/gifts/kpi/KpiSection.jsx` — контейнер вкладки: загрузка списка, loading/error-состояния, кнопка «Добавить»
- `src/components/gifts/kpi/KpiTable.jsx` — таблица: месяц/год, 5 метрик (план / факт / % от бэкенда), индикатор заметок, действия (править, удалить с подтверждением)
- `src/components/gifts/kpi/KpiFormModal.jsx` — create/edit: месяц+год (select; **disabled при edit** — поля immutable на бэке), 10 числовых полей (≥0), notes (≤2000)
- `api.js` — `listKpi`, `createKpi`, `updateKpi`, `deleteKpi` (+ обработка 409)

## Assumptions — betting on / could kill this / consciously ignoring

- **Ставим на:** `KPIResponse` отдаёт вычисленные проценты выполнения (docstring «computed completion percentages» — schemas.py:208); фронт ничего не считает. Точные имена computed-полей уточняю по models/service в первый час кода.
- **Может убить:** формат list-ответа `/kpi` — пагинированный `{items,total,page,size}` (как gifts) или плоский массив; проверка по router/service в первый час, оба варианта дешёвые.
- **Осознанно игнорируем (v1):** сохранение state доски при переключении вкладок (доска перемонтируется — ровно как сейчас при переключении секций монолита); фильтры/сортировка по годам (записей ~12/год); экспорт; графики (территория Budget/Report).

## PR scope

- **Title:** `feat(hr): KPI tab with monthly records table and form (frontend)`
- **IN:** вкладки в GiftFlowPage; компоненты `kpi/`; api-функции; обработка 409 (тост «KPI за этот месяц уже существует», форма не закрывается)
- **OUT:** бэкенд (не трогаем совсем); графики/аналитика; Budget/Report; TabBar-абстракция; правки BiotactDashboard.jsx; react-router

## Files touched

`frontend/dashboard/src/components/gifts/GiftFlowPage.jsx` (вкладки), новые `frontend/dashboard/src/components/gifts/kpi/{KpiSection,KpiTable,KpiFormModal}.jsx`, `frontend/dashboard/src/api.js` (+4 функции). Прогноз ≤ ~450 строк диффа.

## Acceptance criteria — «PR готов, когда…»

- [ ] Вкладка «KPI» внутри «Подарков»; по умолчанию открыта «Доска»; доска не регрессирует (создание/перемещение/детали работают как до PR)
- [ ] Таблица: записи по месяцам, для каждой из 5 метрик — план, факт, % (значение бэкенда, не вычисление фронта)
- [ ] Создание: месяц+год выбираются; дубль месяца → 409 → понятный тост, введённые данные не теряются
- [ ] Правка: месяц+год disabled; PATCH шлёт только изменённые поля
- [ ] Удаление — с подтверждением
- [ ] Тема light/dark через существующий GiftThemeContext; default exports; стиль модуля gifts (MVP-решения PR-1 в силе)
- [ ] `npm run lint`: 0 ошибок в новых/изменённых файлах (4 известные ошибки монолита — не наша зона)
- [ ] Коммиты conventional, без AI-подписей

## Definition of Done

PR влит в main, ветка удалена, CI зелёный, автодеплой фронта прошёл, smoke на проде выполнен, обновление доков не требуется.

## Test plan

- Локально: `npm run build` + `npm run lint` (новые файлы — чисто)
- `/review` на diff перед Гейтом 2 — это код, флот применим (первый inline/fleet-прогон с tests-first из B4)
- Smoke на проде после merge (разделение труда: я — API-проверки и setup, Капитан — клики в UI): создать KPI текущего месяца → попытка дубля → 409-тост → правка факта → проценты обновились → удаление → «Доска» работает как раньше
