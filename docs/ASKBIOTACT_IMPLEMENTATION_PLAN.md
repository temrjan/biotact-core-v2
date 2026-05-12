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

### Фаза 1 — CONDENSE rewrite (2026-05-12) ❌ ROLLED BACK

> Реализована, задеплоена, eval не прошёл stop-condition `must_mention = 1.0` (упал до 0.862). Revert'нута двумя коммитами (`e332daf` + `b876dba`). Полный post-mortem — в `docs/EVAL_BASELINE.md`.

**Что было сделано:**
- `src/biotact/services/condense.py` — async `condense_query()` с lru_cache промптом + Redis-cache по `(dept, hash(original + history))` + 3-уровневый fallback на original message.
- `prompts/condense.txt` — Quivr-style rewriter с RU/UZ language invariant.
- `src/biotact/modules/askbiotact/service.py:_process_rag_query` — заменил regex `enrich_query` на `condense_query` после DB-insight branch; `<context_hint>` блок в system_prompt; Pilot всё ещё получает ORIGINAL `message`.
- 18 unit-тестов `test_condense.py` + 3 invariant-теста `test_phase1_invariants.py`.
- `scripts/run_eval.py` обновлён чтобы eval мерил CONDENSE retrieval.

**Почему откатилось:**

| Метрика | Baseline | Phase 1 | Verdict |
|---|---|---|---|
| recall@5 | 0.909 | 0.955 | +4.6pp (planned ≥+5pp — narrow miss) |
| **must_mention** | **1.000** | **0.862** | **-13.8pp ❌ STOP-CONDITION** |
| faithfulness | 0.438 (judge-noise) | 0.375 | -6.3pp same-day, regression |
| safety_redirect | 1.000 | 1.000 | ✅ (insurance спас) |
| violations | 0.000 | 0.000 | ✅ |

**Корневая причина (2 паттерна):**

1. **PRICE_ENRICHMENT lost.** `enrich_query` (regex) для price-queries добавлял semantic-core который матчил `prices.txt` chunks. CONDENSE — LLM rewrite — этот boost не воспроизводит. 4 кейса (`price-uz-001`, `follow_up-ru-003`, `follow_up-uz-001`, `follow_up-uz-003`) потеряли числа цен. **/selfcheck Finding 2 предупреждал, я недостаточно учёл.**

2. **Medical retrieval collapse.** CONDENSE переписывал short symptoms/safety follow-ups так, что retrieval уходил от gold-chunks полностью (recall@5=0 в 9 кейсах). `safety_filter` Phase 0.6 спасал текст ответа, но retrieval — на 0.

**Процессные learnings:**
- Eval запустили ПОСЛЕ deploy → ~2 часа prod-time с regression. Должен был быть pre-push gate.
- Faithfulness как метрика недетерминирована (judge-noise +9.4pp без изменений кода). Stop-conditions ставить на recall@5 / must_mention / safety_redirect / violations.
- Same-day baseline snapshot обязателен.

---

### Фаза 1.5 — CONDENSE-hybrid (после явного решения Captain'а) 📋 candidate

**Цель:** поднять recall@5 на short follow-up'ах БЕЗ regression на price/safety/symptoms.

**Идея:** CONDENSE только там где регекс заведомо плох — короткие follow-up'ы вне safety/price. Регекс остаётся primary для остальных путей.

```python
if enriched_message == message:
    if is_short_query(message) and detect_safety_trigger(message) is None and not is_price_query(message):
        enriched_message = await condense_query(...)   # short follow-up only
    else:
        enriched_message = enrich_query(message, chat_history)  # regex preserves PRICE_ENRICHMENT + medical context
```

**Жёсткий gate (pre-push, не post-deploy):**
1. Локальные изменения + unit-тесты.
2. **Pre-push eval на bcv2** через `docker cp` файлов в `biotact-api` БЕЗ commit/push: same-day snapshot baseline + same-day snapshot test-варианта.
3. **Stop-conditions:**
   - `recall@5 +5pp vs same-day baseline` ✅ обязательно
   - `must_mention = 1.000` ✅ строго (не <)
   - `safety_redirect = 1.000` ✅ строго
   - `violations = 0` ✅ строго
   - `faithfulness` — информативная, не gate (judge-noise)
4. Если все 4 gate-метрики PASS → commit + push → CD. Если FAIL → fix локально, repeat 2.

**Stop-condition фазы:** если hybrid тоже не дотягивает recall@5 +5pp на short follow-ups → закрыть направление CONDENSE, рассмотреть Phase 4 (reranker) или останов на Phase 0.6.

**Артефакты:** condense service (re-add) + hybrid guard в service.py + tests + eval evidence.

**НЕ делать в Phase 1.5:**
- Не возвращать `<context_hint>` блок в system_prompt — он не дал измеримой пользы в Phase 1.
- Не убирать regex `enrich_query` — он source of truth для price/long/safety путей.
- Не пушить без pre-push eval-gate. Без исключений.

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
| Этот план | Phases 0/0.5/0.6 закрыты; Phase 1 ROLLED BACK; Phase 1.5 candidate |
| `.claude/workflow-state.json` | state = `idle`, 27+ transitions, Phase 1 rollback зафиксирован |
| Eval baseline + harness | ✅ зафиксирован, 32 кейса (RU=18, UZ=14, 7 safety) |
| Safety guardrails (промпт + code) | ✅ shipped — safety_redirect 1.0, violations 0 |
| Phase 1 (CONDENSE) | ❌ rolled back — must_mention regression. См. `docs/EVAL_BASELINE.md` |
| Navigator | Не существует — Phase 2 (после успешного Phase 1.X или Phase 4) |
| CI на main | ✅ Lint + Tests зелёные (HEAD = `b876dba` revert) |

**Развилка по следующему шагу (Captain решает):**

| Вариант | Что | Когда уместен |
|---|---|---|
| A. **Phase 1.5 hybrid** (см. секцию выше) | CONDENSE только для `is_short_query AND not safety AND not price` | Хочется ещё попробовать улучшить recall@5 на коротких follow-up'ах с минимальным риском |
| B. **Phase 4 reranker** | Cohere Rerank multilingual поверх существующего retrieval | Reranker аддитивен (top-N → top-5), не должен ронять must_mention. НО: не вытащит то чего нет в top-N |
| C. **Стоп на Phase 0.6** | Текущая baseline здоровая, дальше не трогать | Risk-averse путь — текущее качество достаточно для пилота |

**Без решения Captain'а — план в подвешенном состоянии.** Перед стартом любого варианта обязательно: same-day snapshot baseline + pre-push eval gate.

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
- **2026-05-12** — Phase 1 (CONDENSE rewrite, commits `f0395a2` + `078a364`) shipped и развёрнут. Post-deploy eval показал: recall@5 +4.6pp (narrow miss), **must_mention 1.000 → 0.862 (regression)**, 9 кейсов recall@5=0 в symptoms/safety. Stop-condition нарушен.
- **2026-05-12** — Phase 1 ROLLED BACK через 2 revert-коммита (`e332daf` + `b876dba`). Post-revert eval подтвердил восстановление baseline (4/5 метрик exact match). Зафиксировано открытие: gpt-4o-mini judge недетерминирован (+9.4pp faithfulness без изменений кода). Phase 1.5 (hybrid CONDENSE) добавлена как candidate, требует решения Captain'а перед стартом.
