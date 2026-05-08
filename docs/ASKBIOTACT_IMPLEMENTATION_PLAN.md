# AskBiotact — план улучшения качества (Navigator + Pilot)

> Рабочий документ. Любой ИИ-коллаборатор, открывший этот файл, должен мочь вступить в работу с того места, где она остановилась. Captain (omadgo) держит финальное решение.

---

## 1. Онбординг: что нужно знать за 60 секунд

### Что такое AskBiotact
RAG-консультант BIOTACT (БАДы + кухонная техника, Узбекистан). Канал — Telegram, языки — RU/UZ. Стек: Python 3.11 / FastAPI / Qdrant / OpenAI / Redis / Postgres. Подробности — `src/biotact/modules/askbiotact/AskBiotact-README.md` и интерактивная схема `docs/askbiotact_pipeline.html`.

### Команда (метафора авиации)
| Роль | Кто это |
|---|---|
| **Captain** | omadgo — задаёт миссию, держит вектор продукта. Не персонаж в коде. |
| **Navigator** | Новый компонент — LLM-стратег между вопросом клиента и эмбеддингом. Изучает обстановку, читает CRM, прокладывает курс (rewritten query, missing slots, strategy). |
| **Pilot** | Существующий chat LLM — получает план + чанки, формирует ответ клиенту. |
| **ExtractionAgent** | Существующий async-агент. Долго будет жить параллельно с Navigator (shadow mode), потом cut-over. |

### Главная боль (для контекста)
1. Обогащение запроса делается **regex'ом** (не LLM) — короткие follow-up'ы ломаются.
2. В Pilot уходит **оригинальный** вопрос, не обогащённый.
3. **Нет reranker'а**, threshold 0.30 пропускает шум.
4. ~~**Нет eval-сета** — все улучшения сейчас вслепую.~~ ✅ закрыто (Phase 0): 32-кейсный eval + nightly hook через `/loop`.
5. ExtractionAgent работает после ответа — на текущий ход бесполезен.
6. ~~**Бот рекомендовал продукты в зонах риска** (беременность / дети до 3 / cardiac).~~ ✅ закрыто (Phase 0.5/0.6): промпт + code-level `safety_filter` → 10/10 redirect, 0 violations.

### Архитектурный вектор
Phase-by-phase: сначала измерить (eval), потом дешёвый апгрейд retrieval'а, потом Navigator как обычная функция (не LangGraph), потом качественная итерация промпта, потом полировка retrieval'а. **Rust пока не трогаем** — bottleneck I/O, не язык.

---

## 2. Скиллы: cheat-sheet и логика выбора

### Cheat-sheet

| Скилл | Когда вызывать | Что делает | Что НЕ делает |
|---|---|---|---|
| `/workflow <task>` | В самом начале каждой фазы | Создаёт/читает `.claude/workflow-state.json`, переводит idle → planning. Iron Laws (нет кода в planning, нет commit без review). | Не пишет код, не делает ревью |
| `/check` | После того как Claude предложил план | Adversarial review плана — мин. 5 findings в 5 категориях (Facts, Edge cases, Simplicity, Compatibility, Format). Запрещены слова "should/probably/seems to". | Не одобряет переход в coding — это решает Captain словом "одобрено/да/go" |
| `/selfcheck` | Когда Claude сам сомневается в свежем предложении | Лёгкая версия /check — 4 категории, вызывается без перевода в planning. Полезен между большими шагами. | Не заменяет `/check` для серьёзных решений |
| `/quality-check` | Раз в 2 недели или перед серьёзной фазой | Идёт в Reddit r/ClaudeCode, GitHub awesome-lists, блоги Anthropic — ищет свежие best practices. | Не правит код, только research |
| `/python` | Перед написанием любого Python-кода в фазе | Загружает Python KB (CORE.md + домен FastAPI / RAG / pytest). Tool-first. | Не пишет код за тебя — задаёт стандарты |
| `/review` (= /kreview) | После coding, перед commit | Если diff < 200 строк — single-agent inline review. Если ≥ 200 — флот 5 агентов + confidence-scorer. Severity blocking → important → suggestion → nit. | Не коммитит сам. Iron Law: не commit без `reviewing → shipped` |
| `/python-review` | Когда нужен фокусированный Python-аудит критичного файла | Один эксперт-Python проходит по checklist'у Корректность → Производительность → Безопасность → Читаемость. | Менее покрытый чем флот /review — для прицельного использования |
| `/security-review` | При изменениях в auth / PII / данных клиента | Security-аудит pending changes на ветке. | Не заменяет общий /review — дополнение |
| `/simplify` | Когда чувствуешь over-engineering в свежем коде | Ищет дубли, лишние абстракции, упрощает. | Не добавляет фичи |
| `/verify` | После деплоя (`shipped` state) | Ищет smoke-test (scripts/smoke.sh / Makefile / npm / CLAUDE.md), запускает, сканирует логи на ERROR/5xx. Verdict: ship / fix-before-ship / investigate. | Не делает rollback — только сигналит |
| `/loop <interval> <skill>` | Для nightly eval, мониторинга | Запускает скилл по расписанию (каждые N минут или авто-pacing). | Не для одноразовых задач |
| `/schedule` | Для cron-задач, переживающих сессию | Создаёт remote-агентов на cron. | — |
| `/claude-api` | Если переключаем LLM на Anthropic | Загружает Claude/Anthropic SDK best practices, prompt caching. | Не для OpenAI |

### Decision tree: какой скилл сейчас

```
Пользователь дал задачу?
├── Да → /workflow <task>          # idle → planning
│   └── План готов?
│       ├── Нет → пиши план       # сам, в planning state
│       └── Да → /check            # обязательно ≥5 findings
│           └── Captain одобрил?
│               ├── Да → /python (или /codex)   # planning → coding
│               │   └── Кодишь
│               │       └── Готово?
│               │           └── /review          # coding → reviewing
│               │               └── Чисто?
│               │                   ├── Да (только sugg/nit) → commit → push
│               │                   │   └── Деплой произошёл? → /verify
│               │                   └── Нет (blocking/important) → правки → /review
│               └── Нет → /check ещё раз с правками
└── Я (Claude) сделал большое предложение?
    └── /selfcheck                  # лёгкая перепроверка
```

**Правила параллельной работы:**
- `/quality-check` — раз в 2 недели независимо.
- `/loop` — для nightly eval после Phase 0.
- `/schedule` — для еженедельного мониторинга метрик.

**Чего НЕ делать:**
- Не пропускать `/check` (Iron Law) кроме `/workflow fast` (диф < 10 строк, не auth/crypto).
- Не коммитить без `/review`.
- Не пушить без подтверждения Captain'а.

---

## 3. Фазы реализации

Каждая фаза — отдельный `/workflow` цикл (idle → planning → coding → reviewing → shipped). Между фазами — измерение через eval-сет.

### Фаза 0 — Eval foundation (3–5 дней) ✅ shipped 2026-05-08 (commits `bfc3d05` + `f7b7351`)

**Цель:** получить численную метрику качества. Без неё фазы 1–4 идут вслепую.

**Воркфлоу:**
1. `/workflow "build eval set + harness for AskBiotact RAG"` → planning
2. `/check` — особенно проверить: SME для валидации ответов, покрытие RU+UZ, retrieval ground truth, защита PII в датасете
3. Captain одобряет → `/python` (домен: pytest + RAG)
4. Пишем:
   - `tests/eval/biotact_gold_set.jsonl` — 30 диалогов (10 цена, 10 симптомы/рекомендация, 10 follow-up "а сколько стоит?")
   - `scripts/run_eval.py` — прогоняет gold set, считает: retrieval recall@5, answer faithfulness (LLM-judge), grounding (нет ли в ответе данных не из чанков)
   - `scripts/smoke.sh` — обновить, чтобы /verify умел гонять часть eval как smoke
5. `/review` (диф будет ~200–400 строк → fleet mode)
6. `/python-review` отдельно для `run_eval.py` — критичный файл, должен работать без сюрпризов
7. Запустить eval против текущего pipeline → **зафиксировать baseline**
8. `/verify staging` после деплоя

**Stop-condition:** baseline зафиксирован, eval воспроизводимо запускается. Без этого фаза 1 не начинается.

**Артефакты:** `tests/eval/biotact_gold_set.jsonl`, `scripts/run_eval.py`, `docs/EVAL_BASELINE.md`

---

### Фаза 0.5 — Safety guardrails в промпте ✅ shipped 2026-05-08 (cap 3 итерации; commits `4f713fd` → `c278661` → `fdb8867` → `f787155`)

> Изначально планировалась как «препарат safety-кейсов в gold-set», но baseline #1 показал критический gap (safety_redirect 0.625 — бот рекомендовал BIFOLAK MAGNIY беременной). Фаза превратилась в активные итерации промпта: добавлен раздел "АБСОЛЮТНЫЕ ОТКАЗЫ" + counter-rule "вне отказов — называй имена" + явная child-age семантика. Gold-set расширен на 2 chronic кейса (32 всего). После 3 итераций — 9/10 redirect, 1/10 violation borderline. cap исчерпан → Phase 0.6.

### Фаза 0.6 — Code-level safety guard ✅ shipped 2026-05-08 (commit `4ef1923`)

Insurance над промпт-уровнем Phase 0.5. Добавлен `src/biotact/modules/askbiotact/safety_filter.py`:
- `detect_safety_trigger(message)` — regex-classifier: pregnancy / child_under_3 / cardiac / chronic / None
- `apply_safety_filter(answer, message, trigger)` — strip имён BIOTACT-продуктов + добавить boilerplate redirect к специалисту, idempotent

Интегрирован в `service.py:_process_rag_query` после `generate_response`. 12 unit-тестов покрывают детекцию + filtering + idempotency + lang detection.

**Финальные метрики на 32 кейсах:**

| Метрика | Baseline #1 | Phase 0.6 final |
|---|---|---|
| Recall@5 | 0.909 | 0.909 |
| Faithfulness | 0.333 | 0.344 |
| **Safety redirect rate** | 0.625 | **1.000** 🟢 |
| **Must-mention coverage** | 0.852 | **1.000** 🟢 |
| **Must-not-mention violations** | 0.375 | **0.000** 🟢 |

Все safety-кейсы по-прежнему `sme_validated_by: null` — перед production-launch на пациентах требуется ревью медицинских специалистов.

### Фаза (исходный план 0.5 — оставлено как историческая запись)

**Цель:** для медицинского бота safety guardrails — отдельная сквозная забота.

**Воркфлоу:**
1. `/workflow "draft safety guardrails for AskBiotact"` → planning
2. `/check` — особенно: какие симптомы → отказ + врач, как обрабатывать беременность/детей, PII в логах
3. `/quality-check` — посмотреть свежие best practices по medical LLM safety
4. Captain одобряет → пишем `docs/SAFETY_GUARDRAILS.md` (документ, не код)
5. Добавляем 5 safety-кейсов в `biotact_gold_set.jsonl` ("должен отказать и направить к врачу")
6. `/review` для тестов
7. Apply guardrails в `prompts/askbiotact.txt` если уточнения нужны

**Stop-condition:** safety-кейсы есть в eval-сете и проходят (бот корректно отказывается).

---

### Фаза 1 — Минимальный апгрейд retrieval'а (2–3 дня) 📋 next

**Цель:** заметное улучшение recall@5 при минимальных изменениях.

**Воркфлоу:**
1. `/workflow "add CONDENSE rewrite + enrichment hint + retrieval cache"` → planning
2. `/check` — особенно: cache invalidation, latency budget (+300–600ms на CONDENSE), fallback при сбое gpt-4o-mini, как enrichment попадает в Pilot (hint в system_prompt, не подмена question)
3. Captain одобряет → `/python` (FastAPI + RAG)
4. Изменения:
   - `src/biotact/modules/askbiotact/service.py`: вызвать `condense_query()` перед embedding, добавить hint в system_prompt Pilot'а
   - `src/biotact/services/condense.py` — новый файл, 1 промпт gpt-4o-mini (Quivr-style CONDENSE_TASK_PROMPT)
   - `src/biotact/services/retrieval_cache.py` — Redis-cache по `(department, hash(condensed_query))`, TTL 1ч
   - prompt в `prompts/condense.txt`
5. `/review` (диф ~150–250 строк, может быть single-agent или fleet)
6. Прогон eval → должен вырасти recall@5 на ≥ 5pp
7. **Канарейка:** деплой 10% → `/verify staging` → 50% → 100%
8. Обновить `docs/askbiotact_pipeline.html` слайд 1+2

**Stop-condition:** eval не показал ≥ 5pp улучшения → откат, разбор, не идём в фазу 2.

**Артефакты:** condense service, cache layer, обновлённый pipeline diagram.

---

### Фаза 2 — Navigator как plain async function (1 неделя)

**Цель:** ввести стратега, но без LangGraph. Plain Python, чистые контракты.

**Воркфлоу:**
1. `/workflow "introduce Navigator agent with explicit contracts"` → planning
2. `/check` — особенно: contract design (SearchPlan / NavigatorAgent / PilotLLM), shadow mode для dialog_state, не ломать ExtractionAgent, latency-бюджет, идемпотентность
3. Captain одобряет → `/python` + чтение `service.py:268-341` (где сейчас RAG-pipeline)
4. Изменения:
   - `src/biotact/modules/askbiotact/navigator.py` — новый класс с типизированным контрактом:
     ```python
     class SearchPlan(BaseModel):
         rewritten_query: str
         missing_slots: list[str]
         clarify_question: str | None
         strategy: Literal["single", "hyde", "multi_query"]

     class NavigatorAgent:
         async def plot_course(message, history, crm_card) -> SearchPlan: ...
     ```
   - `src/biotact/modules/askbiotact/pilot.py` — выделить chat LLM как `PilotLLM`, переписать `_process_rag_query` чтобы получал `SearchPlan`
   - `migrations/<rev>_navigator_decisions.py` — таблица для логов решений Navigator
   - `migrations/<rev>_dialog_state.py` — Letta-style memory (shadow mode, ExtractionAgent остаётся)
5. `/review` fleet (>200 строк точно)
6. `/security-review` — новые таблицы с user data, проверить PII handling
7. Прогон eval → ловим регрессии
8. Канарейка → `/verify`

**Stop-condition:** answer faithfulness не выросла → не идём в фазу 3, разбор.

**Артефакты:** `navigator.py`, `pilot.py`, две миграции, обновлённый pipeline diagram (слайд 1).

---

### Фаза 3 — Качественная итерация промпта Navigator (1–2 недели)

**Цель:** главный скачок качества через прицельную работу с промптом против eval-сета.

**Воркфлоу:**
1. `/workflow "iterate Navigator prompt against eval set"` → planning
2. `/check` — особенно: расширение eval-сета до 100 диалогов, LLM-judge для UZ корректен, нет ли overfitting
3. Captain одобряет
4. Расширить gold set до 100 диалогов (важно: SME валидирует, не Claude)
5. `/loop "nightly /verify" interval=24h` — настроить регулярный прогон eval
6. Ручная итерация промпта Navigator против метрик. Каждый прогон — фиксировать в `docs/NAVIGATOR_PROMPT_LOG.md`
7. **Только если упёрлись в потолок** ручной итерации:
   - `/quality-check` — посмотреть свежие техники
   - Перевести Navigator на DSPy Signature, запустить MIPROv2
8. Cut-over: ExtractionAgent → Navigator memory (после 2 недель shadow mode без расхождений)

**Stop-condition:** answer faithfulness и retrieval recall@5 вышли на плато.

---

### Фаза 4 — Retrieval polish (опционально, 1 неделя)

**Цель:** последний жим из retrieval'а. Делать только если eval показывает что узкое место именно тут.

**Воркфлоу:**
1. `/workflow "add reranker (+ optional multi-query)"` → planning
2. `/check`
3. Captain одобряет → `/python`
4. Cohere Rerank multilingual (RU+UZ supported), k=20 → top-5
5. Опционально: multi-query / HyDE из MedRAG `follow_up_ask`
6. `/review` + `/verify`

**Stop-condition:** reranker не дал ≥ 5pp recall@5 → откат, не делаем multi-query.

---

## 4. Сквозные практики

### `/selfcheck` после каждого большого предложения Claude
Когда Claude (я) предлагаю архитектуру / план / решение размером больше 5 шагов — Captain просит `/selfcheck`. Это лёгкая (без `/workflow`-перехода) перепроверка по 4 категориям. Полезно между `/check` и началом coding'а.

### `/quality-check` — раз в 2 недели
Свежие best practices по Claude Code и RAG-quality меняются быстро. Раз в 2 недели Captain (или nightly через `/loop`) запускает `/quality-check`, читает находки, решает что внедрять.

### `/loop nightly /verify` — после фазы 0
Когда eval-харность готова (фаза 0), настраиваем `/loop` на nightly прогон. Если recall@5 / faithfulness просели — уведомление Captain'у.

### `/schedule` — еженедельный отчёт
Раз в неделю — отчёт по метрикам качества (cron remote agent). Captain видит тренд.

### Когда `/workflow fast` уместен
Только: диф < 10 строк, не трогает `auth|payment|secret|token|password|crypto`. Например — правка опечатки в промпте, изменение значения константы. Skip `/check`, но `/review` всё равно обязательный.

---

## 5. Текущее состояние и следующий шаг

| Что | Статус |
|---|---|
| Этот план | Актуален; Phases 0/0.5/0.6 закрыты, Phase 1 — next |
| `.claude/workflow-state.json` | Активен; 18 transitions; state = `shipped` |
| Eval baseline + harness | ✅ зафиксирован, 32 кейса (RU=18, UZ=14, 7 safety) |
| Safety guardrails (промпт + code) | ✅ shipped — safety_redirect 1.0, violations 0 |
| Navigator | Не существует — следующая фаза 2 (после Phase 1) |
| CI на main | ✅ Lint + Tests зелёные (commit `44ccc68`); Tests integration skip-if-missing-secret |

**Следующий шаг (когда Captain даст добро):**
```
/workflow "Phase 1 — CONDENSE rewrite + retrieval cache + enriched in Pilot"
```
Это начнёт Phase 1: заменить regex-обогащение на 1 LLM-промпт CONDENSE (Quivr-style) + Redis-cache по hash(query) + передавать enriched_message как hint в system_prompt Pilot'а. Цель — поднять recall@5 на коротких follow-up'ах.

---

## 6. Связанные документы

- `src/biotact/modules/askbiotact/AskBiotact-README.md` — текущая архитектура модуля
- `docs/askbiotact_pipeline.html` — визуальная схема (4 слайда: текущий пайплайн, простыми словами, bottlenecks, top-5 prior art + план)
- `prompts/askbiotact.txt` — текущий системный промпт Pilot'а
- Memory: `askbiotact_navigator_agent_idea.md` — архитектурное решение Captain'а

## 7. История правок плана

- **2026-05-08** — создан после исследования (Onyx, LangGraph, Letta, Quivr, DSPy) и `/selfcheck`-перепроверки. Captain выбрал имена Navigator + Pilot, иерархия Captain → Navigator → Pilot зафиксирована.
- **2026-05-08** — Phase 0 (eval harness) shipped. Baseline #1 зафиксирован — выявлен критический safety gap.
- **2026-05-08** — Phase 0.5 (промпт) shipped после 3 итераций — safety с 0.625 до 0.900.
- **2026-05-08** — Phase 0.6 (`safety_filter.py` post-filter) shipped — safety 1.0, violations 0. CI зелёный.
