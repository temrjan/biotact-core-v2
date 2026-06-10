# HR Module — Implementation Plan (Phase 2-5)

**Repository:** `biotact-core-v2`  
**Module:** `src/biotact/modules/hr/`  
**Date:** 2026-06-08  
**Status:** Phase 1-5 ✅ DONE — HR Module hardening complete (PR-13/14/15 merged)  
**Authors:** Engineering Team + Reviewer  
**Source Plan:** `docs/HR_AUDIT_FIX_PLAN.md` (audit origin)  

---

## 1. Executive Summary

This document is the **authoritative implementation plan** for Phases 2-5 of the HR Module hardening program. It supersedes all previous implementation documents (`HR_MODULE_IMPLEMENTATION.md`, `IMPLEMENTATION_v2.md`, etc.).

**Phase 1 is complete and deployed.** The remaining work covers:
- **Phase 2:** Architecture refactor (decompose monolithic service, extract digest subsystem, dead code removal)
- **Phase 3:** Template versioning with race-condition-safe constraints + per-category document retention
- **Phase 4:** Comprehensive test baseline (unit, integration, security regression)
- **Phase 5:** Config extraction, OpenAI prompt caching, and quality polish

**Total scope:** ~4,750 LOC across 12+ PRs. Estimated duration: **14-18 working days** (single engineer) including review cycles.

**Post-audit additions:** Gifts & Events subsystem (PR-1 Schema + PR-2a API) was added after Phase 1 security audit. This work is tracked as a parallel stream and is not part of the original 12-PR sequence.

**Critical rule:** No direct commits to `main`. Every change goes through a PR → CI (lint + tests) → review → merge.

---

## 2. Current State (Post-Phase 1)

### 2.1 What is deployed

| PR | Status | Deployed |
|---|---|---|
| PR-1 — RBAC via `HR_ALLOWED_EMAILS` | ✅ Merged (#3) | `aa30a53` |
| PR-2 — RBAC apply + IDOR fix | ✅ Merged (#4) | `237bbc9` |
| PR-3 — Input hardening | ✅ Merged (#5) | `cd0c1a8` |
| Hotfix — `HR_ALLOWED_EMAILS` in compose | ✅ Merged (squashed into #5) | `cd0c1a8` |
| **PR-1 (Schema)** — Gifts, Events, History tables + ENUMs | ✅ Merged (#13) | `13a4fa6` |
| **PR-2a (API)** — Gifts + Events endpoints | ✅ Merged (#16) | `main` (commit `e088c15`) ⚠️ |

### 2.2 Known issues after Phase 1

1. **`chat/service.py` is 663 LOC** with `# noqa: PLR0912, PLR0915` suppressions. Complexity is critical.
2. **`digest/` lives inside `modules/hr/`** but is conceptually a separate news-digest subsystem. Coupling is architectural debt.
3. **Dead code exists:** `extracted_styles` column, legacy `/download-docx` endpoint, unused `HR_SYSTEM_PROMPT`.
4. **Zero tests** existed before Phase 1. Current coverage is minimal (only security tests from PR-1/2/3).
5. **Hardcoded values** scattered across chat service: model name, director names, paths, magic numbers.

### 2.3 Environment constraints

- **PostgreSQL 16** on production (`bcv2`)
- **Python 3.11**, FastAPI, SQLAlchemy 2.0 async, Alembic
- **Non-root container user** (`biotact`, UID 1000) — file permissions matter
- **Pydantic Settings** reads from `.env` mounted at `/app/.env`
- **CI/CD:** GitHub Actions → SSH deploy → `docker compose up -d`

---

## 3. Conventions & Standards

### 3.1 Branch naming
```
hr/p<N>-<slug>
```
Examples: `hr/p4-chat-decompose`, `hr/p7-template-versioning`

### 3.2 Commit message format
```
type(scope): imperative description

Body explaining WHY, not just WHAT.
Refs: docs/HR_IMPLEMENTATION_PLAN.md (Phase X, PR-N)
```

### 3.3 PR description template
```markdown
## Goal
One-sentence objective.

## Changes
- Bullet list of files and logic changes.

## Acceptance
- [ ] Criteria checked

## Rollback
How to revert if production breaks.

## Risks
| Risk | Mitigation |
|---|---|
| ... | ... |

## Dependencies
Blocks / blocked by: PR-X
```

### 3.4 Review gates
1. **Author self-review:** `ruff check`, `ruff format`, `pytest` locally
2. **AI review:** `/kreview` (fleet-5 subagents) for diffs ≥ 200 LOC
3. **Security review:** `/security-review` for any auth/RBAC/upload changes
4. **Human review:** Required before merge

---

## 4. Phase 1.5 — Gifts & Events Subsystem (Post-Audit)

> **Goal:** New HR features: gift request tracking and calendar events.
> **Note:** This work is parallel to the original Phase 2-5 plan.

### PR-1 (Schema) · `feature/hr-schema-pr1` — Database Schema

**Status:** ✅ Merged to `main` (#15)

**Changes:**
- 4 tables: `hr_gift_requests`, `hr_gift_status_history`, `hr_events`, `hr_event_reminders`
- 2 ENUMs: `giftstatus`, `occasiontype`
- Indexes: `ix_hr_gift_status`, `ix_hr_gift_presentation_date`, `ix_hr_event_date`

### PR-2a (API) · `feature/hr-gifts-api-pr2a-fixes` — Gifts + Events Endpoints

**Status:** ✅ Merged (#16) — squashed to `main` as commit `e088c15` (2026-06-09)

> ⚠️ **Commit-message anomaly:** `e088c15` carries the message
> `feat(hr): extract hardcoded config to Settings (PR-13)` — a botched rebase/squash label.
> Its actual content is **this** PR-2a Gifts + Events API (+1,469 LOC, 9 files). The *real*
> PR-13 (config extraction, +50/−31) is a separate commit `9f9dd44`. Verified via
> `git show --stat` + `git cherry`: no code lost or duplicated. Left as-is — rewriting the
> message would require a force-push to shared `main`.

**Changes:**
- `modules/hr/gifts/{schemas,service,router}.py` — Gift CRUD, status transitions with `SELECT FOR UPDATE`, audit history
- `modules/hr/events/{schemas,service,router}.py` — Event CRUD with index-friendly date filtering
- `api/v1/__init__.py` — router registration
- `tests/unit/hr/test_{gifts,events}_api.py` — 21 API tests (PostgreSQL-only; skip on SQLite)

**Reviewer fixes applied:**
1. Events date filter: `func.extract` → `date >= start AND date < end` (index-friendly)
2. Auth guard: `test_non_hr_user_forbidden` for both gifts and events
3. Filter tests: mixed data with inclusion/exclusion assertions
4. SET NULL test: `test_delete_event_sets_null_on_gifts`

**Branch cleanup:**
- `feature/hr-gifts-api` (stale, pre-fixes) — **deleted** (locally + origin)
- `salvage/config-to-settings` (orphan `2f22d77`) — **preserved** for future config-extraction PR

---

## 5. Phase 2 — Architecture Refactor

> **Goal:** Reduce complexity, eliminate coupling, remove dead code. No functional changes to user-visible behavior.

**Recommended order (corrected from audit plan):**
```
PR-5 → PR-4 → PR-6
```
Reason: Extract `digest` first so PR-4 doesn't touch digest imports.

---

### PR-5 · `hr/p5-extract-digest` — Extract Telegram Digest from HR Module ✅ MERGED

**Goal:** Move `modules/hr/digest/` to `modules/news_digest/` to eliminate false coupling.

**Scope:**
- Move directory: `git mv src/biotact/modules/hr/digest src/biotact/modules/news_digest`
- Update all imports across the codebase
- **Do NOT** rename database tables (`hr_digest_runs`, `hr_digest_posts` remain as legacy names with code comments)

**Files changed:**
```
src/biotact/modules/hr/digest/ → src/biotact/modules/news_digest/
src/biotact/modules/hr/__init__.py (remove digest exports)
src/biotact/main.py (update import path)
docker-compose.prod.yml (update command path if referenced)
tests/ (update imports)
```

**Detailed steps:**

1. **Pre-flight grep (mandatory before any `git mv`)**
   ```bash
   grep -rn 'modules\.hr\.digest\|modules/hr/digest\|hr_digest\|hr/digest' \
     --include='*.py' --include='*.yml' --include='*.yaml' \
     --include='*.toml' --include='*.ini' --include='*.env*' \
     --include='Dockerfile*' --include='*.sh' \
     . > /tmp/digest_refs.txt
   ```
   Save this list in the PR description.

2. **Execute move**
   ```bash
   git mv src/biotact/modules/hr/digest src/biotact/modules/news_digest
   ```

3. **Update `src/biotact/modules/news_digest/` internal imports**
   Change any `from biotact.modules.hr.digest...` to `from biotact.modules.news_digest...` inside the moved package.

4. **Update consumers**
   - `src/biotact/main.py`: any lifespan registration or import
   - `src/biotact/modules/hr/__init__.py`: remove `digest` from `__all__` if present
   - Tests referencing digest

5. **Add legacy comment in models**
   ```python
   class DigestRun(Base):
       __tablename__ = "hr_digest_runs"
       # Legacy table name kept for migration stability.
       # Module moved to news_digest/ in PR-5.
   ```

6. **Verify zero references**
   Re-run the grep from step 1. Must return zero matches.

**Database migrations:** None.

**Acceptance criteria:**
- [ ] `grep` from step 1 returns 0 matches
- [ ] `pytest` passes (no import errors)
- [ ] `docker compose config` passes (if compose references digest paths)
- [ ] `ruff check src/biotact/modules/news_digest` passes

**Rollback:**
```bash
git revert <merge-commit>
# Or manual:
git mv src/biotact/modules/news_digest src/biotact/modules/hr/digest
# Restore imports from /tmp/digest_refs.txt backup
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| Missed import in obscure file | Step 1 grep covers 8 extensions; CI test suite catches ImportError |
| `docker-compose.prod.yml` command path breaks | Explicitly check `hr-digest-bot` service command in compose |
| Database confusion from legacy names | Code comment + ADR note in PR description |

**Dependencies:** None. Can start immediately.

---

### PR-4 · `hr/p4-chat-decompose` — Decompose `chat/service.py` (663 LOC) ✅ MERGED

**Goal:** Split monolithic `chat/service.py` into 3 focused modules and inject clock for deterministic testing.

**Scope:**
- Extract categories data + postprocess logic → `chat/categories.py`
- Extract prompt building + OpenAI tools → `chat/prompts.py`
- Reduce `chat/service.py` to ~150 LOC (orchestration only)
- Add `freezegun` to dev dependencies
- Replace `datetime.now()` with injectable `now_fn`

**Target structure:**
```
chat/
├── __init__.py
├── router.py
├── schemas.py
├── service.py        # ~150 LOC — process_message + execute_tool only
├── prompts.py        # ~150 LOC — build_system_prompt, OPENAI_TOOLS
└── categories.py     # ~250 LOC — CATEGORIES dict, postprocess functions
```

**Files changed:**
```
src/biotact/modules/hr/chat/service.py      # heavily refactored
src/biotact/modules/hr/chat/categories.py   # NEW
src/biotact/modules/hr/chat/prompts.py      # NEW
pyproject.toml                               # +freezegun dev-dep
tests/unit/hr/test_categories.py            # NEW (snapshot tests)
tests/unit/hr/test_chat_service.py          # modify existing / NEW
```

**Detailed steps:**

1. **Add `freezegun` to dev dependencies**
   ```toml
   [project.optional-dependencies]
   dev = [
       ...,
       "freezegun>=1.5.0",
   ]
   ```
   Run `uv pip install -e ".[dev]"` or `pip install freezegun`.

2. **Create `chat/categories.py`**
   - Move `CATEGORIES` dict (or build it from existing inline dicts)
   - Define `CategoryRules` dataclass:
     ```python
     from dataclasses import dataclass
     from datetime import datetime
     from typing import Callable

     @dataclass(frozen=True)
     class CategoryRules:
         required_fields: tuple[str, ...]
         defaults: dict[str, str]
         postprocess: Callable[[dict[str, str], datetime], dict[str, str]]
         field_rules_for_llm: str
     ```
   - Move each `_postprocess_<category>` function here
   - Keep `CATEGORIES: dict[str, CategoryRules]` as module-level constant

3. **Create `chat/prompts.py`**
   - Extract `STATIC_SYSTEM_PROMPT` (instructions + categories list without dynamic template data)
   - Implement `build_system_prompt(templates: list[Template]) -> str`:
     ```python
     def build_system_prompt(templates: list[Template]) -> str:
         dynamic = "\n".join(
             f"- id={t.id}, name={t.name}, fields={t.fields}"
             for t in templates
         )
         return STATIC_SYSTEM_PROMPT + "\n\nAvailable templates:\n" + dynamic
     ```
   - Move `OPENAI_TOOLS` list here

4. **Refactor `chat/service.py`**
   - Remove all `_postprocess_*` functions (import from categories)
   - Remove prompt construction (import from prompts)
   - Inject clock in `HRChatService.__init__`:
     ```python
     from datetime import datetime, UTC
     from typing import Callable

     class HRChatService:
         def __init__(
             self,
             ...,
             now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
         ):
             self._now = now_fn
     ```
   - All internal calls to `datetime.now()` become `self._now()`
   - Remove `# noqa: PLR0912, PLR0915` suppressions

5. **Update `chat/router.py`**
   - Import `build_system_prompt` from `prompts`
   - Import `CATEGORIES` from `categories` if needed for validation

6. **Write snapshot tests**
   - For each of 11 categories: provide fixed input dict → call postprocess with frozen time → assert exact output
   - Use `freezegun.freeze_time("2026-06-08T00:00:00Z")`

7. **Verify line counts**
   ```bash
   wc -l src/biotact/modules/hr/chat/service.py
   # Must be ≤ 200
   ```

**Database migrations:** None.

**Acceptance criteria:**
- [ ] `wc -l chat/service.py` ≤ 200
- [ ] `ruff check src/biotact/modules/hr/chat` passes with zero noqa suppressions
- [ ] Snapshot tests for all 11 categories pass with frozen time
- [ ] `pytest` passes (no regressions in chat flow)
- [ ] `mypy --strict` shows no new errors in refactored files

**Rollback:**
```bash
git revert <merge-commit>
# If partial revert needed:
git checkout main -- src/biotact/modules/hr/chat/service.py
# Restore deleted functions from git history
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| Import cycle between service.py and categories.py | Categories.py must NOT import service.py (it only needs datetime + typing) |
| Postprocess function signature change breaks caller | Keep signature `(data: dict[str, str], now: datetime) -> dict[str, str]` exact |
| Router uses inline classes that no longer exist | PR-3 already created `chat/schemas.py`; ensure router imports from there |
| `freezegun` conflict with async tests | Use `@freeze_time("...")` on test function, not class; pytest-asyncio compatible |

**Dependencies:**
- **Blocked by:** PR-5 (extract digest) — do PR-5 first to avoid touching digest imports
- **Blocks:** PR-10 (unit tests), PR-11 (integration tests) — tests should target new structure

---

### PR-6 · `hr/p6-dead-code-cleanup` — Remove Legacy Code ✅ MERGED

**Goal:** Eliminate unused code, columns, and endpoints. Reduce module size by ~200 LOC.

**Scope:**
- Investigate and remove `HR_SYSTEM_PROMPT` / `hr_config` if unused
- Drop `extracted_styles` column from `hr_templates`
- Remove legacy `/download-docx` endpoint and `docx_generator.py` (if frontend doesn't call it)
- Move function-level imports to top-level in service files

**Files changed:**
```
src/biotact/modules/hr/config.py           # may be deleted
src/biotact/modules/hr/chat/service.py      # import cleanup
src/biotact/modules/hr/library/service.py   # import cleanup
src/biotact/modules/hr/documents/router.py  # endpoint removal
src/biotact/modules/hr/documents/docx_generator.py  # may be deleted
migrations/versions/xxx_drop_extracted_styles.py    # NEW alembic migration
tests/ (update if tests reference removed code)
```

**Detailed steps:**

1. **Investigate `HR_SYSTEM_PROMPT` usage**
   ```bash
   grep -rn 'HR_SYSTEM_PROMPT\|hr_config' src/ tests/
   ```
   - If ONLY import is in `main.py` and the object is never used → delete `config.py`, remove import from `main.py`
   - If used anywhere → keep but document in PR description

2. **Investigate `/download-docx` usage**
   ```bash
   grep -rn 'download-docx\|text_to_docx' frontend/ src/ tests/
   ```
   - If NO frontend references → delete endpoint + `docx_generator.py`
   - If frontend references → keep endpoint, add `RequireHREmailDep`, document in PR

3. **Drop `extracted_styles` column**
   ```bash
   alembic revision -m "drop extracted_styles from hr_templates"
   ```
   Migration content:
   ```python
   def upgrade() -> None:
       op.drop_column('hr_templates', 'extracted_styles')

   def downgrade() -> None:
       op.add_column(
           'hr_templates',
           sa.Column('extracted_styles', sa.Text(), nullable=True)
       )
   ```
   Run `alembic upgrade head` and `alembic downgrade -1` locally to verify.

4. **Move function-level imports to top-level**
   In `chat/service.py` and `library/service.py`, find imports inside functions:
   ```python
   # BEFORE (inside function)
   def process_message(...):
       from biotact.modules.hr.chat.prompts import build_system_prompt
       ...

   # AFTER (top level)
   from biotact.modules.hr.chat.prompts import build_system_prompt
   ```
   Rationale: function-level imports are usually workarounds for circular imports. After PR-4 decomposition, cycles should be resolved.

5. **Verify no regressions**
   ```bash
   pytest tests/ -k hr
   ruff check src/biotact/modules/hr
   ```

**Database migrations:** Yes — one to drop `extracted_styles`.

**Acceptance criteria:**
- [ ] `grep` for removed symbols returns 0 matches in `src/` and `frontend/`
- [ ] Alembic `upgrade` + `downgrade` passes on local DB
- [ ] All existing tests pass
- [ ] `wc -l src/biotact/modules/hr/` shows net reduction of ~200 LOC
- [ ] `ruff check` passes with zero noqa suppressions

**Rollback:**
```bash
# For code:
git revert <merge-commit>

# For DB column:
alembic downgrade -1
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| Frontend secretly uses `/download-docx` | Explicit grep in `frontend/` directory before deletion |
| `extracted_styles` needed by legacy script | Check `scripts/` directory for references |
| Top-level import creates circular dependency | If cycle appears, revert that specific import to function-level and document |

**Dependencies:**
- **Blocked by:** PR-4 (chat decompose) — import cleanup depends on stable file structure
- **Blocks:** None

---

## 5. Phase 3 — Versioning & Retention

> **Goal:** Enable safe template versioning with rollback + automatic cleanup of transient documents.

---

### PR-7 · `hr/p7-template-versioning-schema` — Database Schema ✅ MERGED

**Goal:** Add version columns to `hr_templates` with race-condition-safe constraints.

**Scope:**
- Alembic migration: `version`, `is_active`, `superseded_by_id`
- Partial unique index: one active template per category
- Update SQLAlchemy models and Pydantic schemas
- Verify PostgreSQL ≥ 11 (for metadata-only `NOT NULL DEFAULT`)

**Files changed:**
```
migrations/versions/xxx_add_template_versioning.py  # NEW
src/biotact/models/hr.py                            # add columns
src/biotact/schemas/hr.py                           # add fields
```

**Detailed steps:**

1. **Verify PG version on production**
   ```bash
   ssh bcv2 'docker exec biotact-postgres psql -U biotact -c "SELECT version();"'
   ```
   Must contain `PostgreSQL 1[2-6].x`. Document in migration docstring:
   ```python
   """Add template versioning columns.

   Requires PostgreSQL >= 11 for metadata-only ADD COLUMN NOT NULL DEFAULT.
   Verified on production: PostgreSQL 16.x.
   """
   ```

2. **Generate migration**
   ```bash
   alembic revision -m "add template versioning to hr_templates"
   ```

3. **Migration content:**
   ```python
   def upgrade() -> None:
       op.add_column(
           'hr_templates',
           sa.Column('version', sa.Integer(), nullable=False, server_default='1')
       )
       op.add_column(
           'hr_templates',
           sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true')
       )
       op.add_column(
           'hr_templates',
           sa.Column('superseded_by_id', sa.Integer(), nullable=True)
       )
       op.create_foreign_key(
           'fk_hr_templates_superseded_by',
           'hr_templates', 'hr_templates',
           ['superseded_by_id'], ['id'],
           ondelete='SET NULL'
       )
       op.create_unique_constraint(
           'uq_hr_template_category_version',
           'hr_templates',
           ['category', 'version']
       )
       op.create_index(
           'ix_hr_template_active_per_category',
           'hr_templates',
           ['category'],
           unique=True,
           postgresql_where=sa.text('is_active IS TRUE')
       )

   def downgrade() -> None:
       op.drop_index('ix_hr_template_active_per_category', table_name='hr_templates')
       op.drop_constraint('uq_hr_template_category_version', 'hr_templates')
       op.drop_constraint('fk_hr_templates_superseded_by', 'hr_templates')
       op.drop_column('hr_templates', 'superseded_by_id')
       op.drop_column('hr_templates', 'is_active')
       op.drop_column('hr_templates', 'version')
   ```

4. **Update models**
   ```python
   class HRTemplate(Base):
       ...
       version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
       is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
       superseded_by_id: Mapped[int | None] = mapped_column(
           ForeignKey("hr_templates.id", ondelete="SET NULL"), nullable=True
       )
       superseded_by: Mapped["HRTemplate"] = relationship(
           "HRTemplate", remote_side="HRTemplate.id", backref="supersedes"
       )
   ```

5. **Update schemas (Pydantic)**
   Add `version: int = 1`, `is_active: bool = True`, `superseded_by_id: int | None = None` to relevant schemas.

6. **Backfill verification**
   Existing 11 templates receive `version=1, is_active=True` via `server_default`. Verify:
   ```python
   from sqlalchemy import select
   from biotact.models.hr import HRTemplate
   templates = await db.execute(select(HRTemplate))
   assert all(t.version == 1 and t.is_active for t in templates)
   ```

7. **Constraint test**
   Attempt to INSERT a second active template in the same category → must raise `IntegrityError`.

**Acceptance criteria:**
- [ ] `alembic upgrade head` passes on staging copy of production DB
- [ ] `alembic downgrade -1` passes and restores original schema
- [ ] Existing 11 templates have `version=1, is_active=True`
- [ ] Attempt to insert duplicate `(category, version)` → `IntegrityError`
- [ ] Attempt to insert second `is_active=True` for same category → `IntegrityError` (via partial index)

**Rollback:**
```bash
alembic downgrade -1
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| `NOT NULL DEFAULT` causes table rewrite on old PG | Verified PG 16 on prod; add docstring requirement |
| Partial unique index not supported by SQLite | Integration tests use PostgreSQL; unit tests mock DB layer |
| Existing code references removed/renamed columns | No columns removed — only added; existing code unchanged |

**Dependencies:**
- **Blocked by:** PR-6 (dead code cleanup) — stable schema before adding columns
- **Blocks:** PR-8 (versioning flow)

---

### PR-8 · `hr/p8-template-versioning-flow` — Upload & Rollback Logic ✅ MERGED

**Goal:** Transactional version bump on upload + rollback endpoint + version history.

**Scope:**
- Modify `upload_template` to create new version and deactivate previous
- Add `POST /hr/library/{id}/rollback`
- Add `GET /hr/library/{id}/history`
- Update `get_template_by_category` to return only active version

**Files changed:**
```
src/biotact/modules/hr/library/service.py   # upload_template refactor
src/biotact/modules/hr/library/router.py    # new endpoints
src/biotact/modules/hr/library/schemas.py   # response models
```

**Detailed steps:**

1. **Refactor `upload_template`**
   ```python
   async def upload_template(
       self,
       category: str,
       file: UploadFile,
       db: AsyncSession,
   ) -> HRTemplate:
       ...  # filename sanitize, magic bytes (existing PR-3 logic)

       async with db.begin_nested():  # savepoint
           prev = (
               await db.execute(
                   select(HRTemplate)
                   .where(HRTemplate.category == category)
                   .where(HRTemplate.is_active == True)
                   .with_for_update()
               )
           ).scalar_one_or_none()

           new_version = (prev.version + 1) if prev else 1

           if prev:
               prev.is_active = False

           template = HRTemplate(
               category=category,
               version=new_version,
               is_active=True,
               name=safe_basename,
               storage_name=storage_name,
               ...
           )
           db.add(template)
           await db.flush()

           if prev:
               prev.superseded_by_id = template.id

           return template
   ```

2. **Update `get_template_by_category`**
   ```python
   async def get_template_by_category(
       self, category: str, db: AsyncSession
   ) -> HRTemplate:
       result = await db.execute(
           select(HRTemplate)
           .where(HRTemplate.category == category)
           .where(HRTemplate.is_active == True)
       )
       return result.scalar_one_or_none()
   ```

3. **Add rollback endpoint**
   ```python
   @router.post("/library/{template_id}/rollback", dependencies=[RequireHREmailDep])
   async def rollback_template(
       template_id: int,
       db: AsyncSessionDep,
   ) -> TemplateResponse:
       async with db.begin_nested():
           target = await db.get(HRTemplate, template_id)
           if not target:
               raise HTTPException(404, "Template not found")

           current = (
               await db.execute(
                   select(HRTemplate)
                   .where(HRTemplate.category == target.category)
                   .where(HRTemplate.is_active == True)
                   .with_for_update()
               )
           ).scalar_one()

           current.is_active = False
           target.is_active = True
           target.superseded_by_id = None

       return TemplateResponse.from_orm(target)
   ```

4. **Add history endpoint**
   ```python
   @router.get("/library/{category}/history", dependencies=[RequireHREmailDep])
   async def list_template_history(
       category: str,
       db: AsyncSessionDep,
   ) -> list[TemplateVersionResponse]:
       result = await db.execute(
           select(HRTemplate)
           .where(HRTemplate.category == category)
           .order_by(HRTemplate.version.desc())
       )
       return [TemplateVersionResponse.from_orm(t) for t in result.scalars()]
   ```

5. **Update STATUS.md and process docs**
   Add note: "Direct `.docx` edits on disk are prohibited. All changes must go through `POST /hr/library`."

6. **Concurrent upload test**
   ```python
   async def test_concurrent_upload_one_wins():
       # Launch 2 uploads for same category simultaneously
       # One succeeds, other gets IntegrityError → API returns 409 Conflict
   ```

**Database migrations:** None (uses schema from PR-7).

**Acceptance criteria:**
- [ ] Upload v1 → render uses v1
- [ ] Upload v2 (same category) → render uses v2; v1 becomes `is_active=False, superseded_by_id=v2.id`
- [ ] Rollback to v1 → render uses v1; v2 becomes `is_active=False`
- [ ] Concurrent upload → one success, one 409 Conflict
- [ ] History endpoint returns versions in descending order

**Rollback:**
```bash
git revert <merge-commit>
# Data state: old active templates remain active; new versioned ones coexist.
# To clean up: manual SQL or next forward migration.
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| Race condition: two uploads create same version | `FOR UPDATE` + unique constraint → one fails with IntegrityError |
| Rollback to deleted template | `ON DELETE SET NULL` on FK; check target exists before rollback |
| Frontend doesn't know about versions | Document API contract change; frontend ticket needed |

**Dependencies:**
- **Blocked by:** PR-7 (versioning schema)
- **Blocks:** None directly; parallel with PR-9

---

### PR-9 · `hr/p9-retention-per-category` — Auto-Cleanup Transient Documents ✅ MERGED

**Goal:** Delete transient HR documents after 30 days; preserve statutory documents forever.

**Scope:**
- Define statutory vs transient categories
- APScheduler daily job at 03:00 UTC
- Physical file deletion + DB row deletion
- Logging for monitoring

**Files changed:**
```
src/biotact/core/scheduler.py              # add job (or new file)
src/biotact/modules/hr/retention.py        # NEW: cleanup logic
docs/HR_IMPLEMENTATION_PLAN.md             # update if category list changes
```

**Detailed steps:**

1. **Define categories (agree with business before merging)**
   ```python
   # src/biotact/modules/hr/retention.py
   STATUTORY_CATEGORIES: frozenset[str] = frozenset({
       "td_osnovnoy",
       "td_sovmestitelstvo",
       "prikaz_priem",
       "mat_otvetstvennost",
   })
   RETENTION_DAYS_TRANSIENT: int = 30
   ```
   > ⚠️ **Must be confirmed with business owner** before merge.

2. **Implement cleanup job**
   ```python
   from datetime import datetime, UTC, timedelta
   from pathlib import Path
   from sqlalchemy import select
   from biotact.models.hr import HRDocument, HRTemplate

   async def cleanup_expired_hr_documents(db: AsyncSession) -> int:
       cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS_TRANSIENT)

       result = await db.execute(
           select(HRDocument)
           .join(HRTemplate, HRDocument.template_id == HRTemplate.id)
           .where(HRDocument.created_at < cutoff)
           .where(HRTemplate.category.notin_(STATUTORY_CATEGORIES))
       )

       deleted_count = 0
       for doc in result.scalars():
           file_path = Path(doc.file_path)
           if file_path.exists():
               logger.warning(
                   "HR retention: deleting transient doc id=%s file=%s age=%dd",
                   doc.id, file_path, (datetime.now(UTC) - doc.created_at).days
               )
               file_path.unlink()
           await db.delete(doc)
           deleted_count += 1

       logger.info(
           "HR retention: completed. Deleted %d transient documents (>%dd)",
           deleted_count, RETENTION_DAYS_TRANSIENT
       )
       return deleted_count
   ```

3. **Register scheduler job**
   In `core/scheduler.py` or `main.py` lifespan:
   ```python
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from apscheduler.triggers.cron import CronTrigger

   scheduler = AsyncIOScheduler()
   scheduler.add_job(
       cleanup_expired_hr_documents,
       trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
       id="hr_retention_cleanup",
       replace_existing=True,
   )
   ```
   Ensure `APScheduler` is in dependencies (likely already present).

4. **Integration test**
   ```python
   async def test_retention_deletes_transient_not_statutory():
       # Create statutory doc (td_osnovnoy) with created_at = now - 31 days
       # Create transient doc (nda_gpd) with created_at = now - 31 days
       # Run cleanup
       # Assert statutory still exists, transient deleted (row + file)
   ```

**Database migrations:** None.

**Acceptance criteria:**
- [ ] Job runs at 03:00 UTC daily
- [ ] Transient document > 30 days deleted (DB row + physical file)
- [ ] Statutory document > 30 days preserved
- [ ] `WARNING` log emitted before each file deletion with `doc.id`
- [ ] Integration test passes with real PostgreSQL

**Rollback:**
```bash
git revert <merge-commit>
# Stop scheduler job
```

**Risks & mitigations:**
| Risk | Mitigation |
|---|---|
| Accidental deletion of needed documents | First month: monitor `journalctl` daily after 03:00 UTC; `WARNING` logs with IDs |
| APScheduler not running (container restart) | Job registered in lifespan; `replace_existing=True` prevents duplicates |
| Timezone confusion | Explicit `timezone="UTC"` in CronTrigger |
| File deleted but DB row remains (or vice versa) | Unlink first, then `await db.delete(doc)`; if unlink fails, log error but still delete DB row to avoid inconsistency |

**Dependencies:**
- **Blocked by:** PR-8 (versioning flow) — uses stable template structure
- **Blocks:** None

---

## 6. Phase 4 — Test Baseline

> **Goal:** Achieve comprehensive automated coverage: unit, integration, and security regression.

---

### PR-10 · `hr/p10-unit-tests` — Unit Coverage ✅ MERGED

**Goal:** Cover pure functions with fast, deterministic unit tests.

**Scope:**
- `num_to_text_uz/ru` — edge cases, scales, negatives
- `chat.categories.postprocess_*` — per-category snapshot with `freezegun`
- `library.scanner.scan_template_fields` — DOCX parsing, split runs, table cells
- `chat.service` helpers: `_parse_int`, `_is_short_date`, `_date_to_full_russian`

**Files changed:**
```
tests/unit/hr/test_num_to_text.py           # NEW
tests/unit/hr/test_categories_postprocess.py # NEW
tests/unit/hr/test_scanner.py               # NEW
tests/unit/hr/test_chat_helpers.py          # NEW
```

**Acceptance:**
- [ ] `pytest tests/unit/hr/` passes
- [ ] `pytest --cov=biotact.modules.hr` ≥ 80% on targeted files
- [ ] No external services (DB, OpenAI, Qdrant) touched

---

### PR-11 · `hr/p11-integration-tests` — Full Cycle Tests ✅ MERGED

**Goal:** End-to-end tests with mock OpenAI and real PostgreSQL.

**Scope:**
- Upload → scan → render → download cycle
- Chat flow with mock OpenAI tool calls
- Versioning: upload v1 → v2 → rollback → assert correct version used

**Files changed:**
```
tests/integration/hr/test_full_cycle.py     # NEW
tests/integration/hr/test_chat_flow.py      # NEW
tests/integration/hr/test_versioning.py     # NEW
```

**Mock OpenAI:** Use `respx` (HTTPX mock) or pre-canned fixture.

**Acceptance:**
- [ ] All integration tests pass with PostgreSQL service container
- [ ] Total execution time < 90 seconds
- [ ] CI green

---

### PR-12 · `hr/p12-security-regression-tests` — Security Regression ✅ MERGED

**Goal:** Lock down all P0 fixes so they cannot regress.

**Scope:** Tests covering every finding from Phase 1:
- IDOR: HR-user A creates doc; non-HR gets 403
- Nonexistent file_id → 404
- Path traversal (Unix + Windows payloads) → sanitized
- DoS: 30 MB upload → 413
- Fake DOCX magic bytes → 400
- Prompt injection (`system` / `tool` role) → 422
- Error sanitization: correlation_id present, file_path absent

**Files changed:**
```
tests/integration/test_hr_security.py       # extend existing file
```

**Acceptance:**
- [ ] All 9 regression scenarios pass
- [ ] Each test has explicit docstring referencing original finding number

---

## 7. Phase 5 — Quality & Optimization

> **Goal:** Production readiness: config-driven, cached, polished.

---

### PR-13 · `hr/p13-config-extraction` — Config-Driven Values ✅ MERGED (#17)

**Goal:** Replace hardcodes with `.env` settings.

**Commit:** `9f9dd44` (squash merge to main)

**Hardcodes extracted:**
- `hr_chat_model` (was `"gpt-5.4-mini"`)
- `hr_max_tool_rounds` (was `5`)
- `hr_history_window` (was `10`)
- `hr_director_short_latin` / `hr_hr_director_short_latin`
- `hr_upload_dir` / `hr_render_dir`
- `hr_max_upload_mb` (was `20`)

**Also fixed:** `mkdir` on import removed from `documents/router.py` and `library/service.py`; moved to `main.py` lifespan startup.

**Acceptance:** Change director name → edit `.env` + restart → works without code deploy. ✅

---

### PR-14 · `hr/p14-openai-prompt-caching` — Prompt Caching ✅ MERGED (#22)

**Goal:** Exploit OpenAI auto-prompt-caching (≥ 1024 tokens stable prefix).

**Approach:**
- Static prefix: instructions + categories + field rules (~1200 tokens)
- Dynamic suffix: loaded templates list (varies per request)
- Log `usage.prompt_tokens_details.cached_tokens` after each call

**No `cache_control` markers needed** — OpenAI handles this automatically.

**Acceptance:** After 2+ sequential calls, `cached_tokens > 0` in logs. Measure % cached on 10 renders.

---

### PR-15 · `hr/p15-quality-polish` — Final Polish ✅ MERGED

**Scope (narrowed during implementation — see rationale below):**
- [x] Narrow 3 *bounded* `except Exception` clauses to specific types:
  - `chat/extractor.py` → `(OpenAIError, json.JSONDecodeError)`
  - `chat/service.py::_get_template_context` → `SQLAlchemyError`
  - `chat/service.py` main OpenAI call → `OpenAIError`
- [x] `[:2000]` → `LOG_ARG_TRUNCATE` constant

**Already satisfied by earlier PRs (verified, no change needed):**
- `os.path.exists + os.remove` → `Path.unlink(missing_ok=True)` — done in PR-6 / PR-9 (all 5 sites).
- `hasattr(self, "_messages_context")` → init in `__init__` — done in PR-4 (`service.py` `__init__`).
- `MAX_TOOL_ROUNDS` / `HISTORY_WINDOW` → already config-driven via Settings (PR-13).

**Deferred — Future / out-of-scope (rationale):**
- **6 of 9 `except Exception` kept broad — intentional architectural guardrails; narrowing would regress:**
  - `documents/router.py` render catch — **active PR-12 error sanitization** (catch-all → 500 + `correlation_id`, no path/trace leak). Narrowing breaks the security guarantee.
  - `library/service.py` upload `except Exception: unlink; raise` — cleanup-and-reraise; narrowing risks orphan-file leaks.
  - `library/scanner.py` (×2), `library/service.py::extract_text`, `chat/documents.py` render — defensive parse/render boundaries over docxtpl / python-docx / pypdf with an unbounded 3rd-party failure space; the broad catch is the intended graceful fallback.
- **`category: str` → `Literal[...]` rejected:** `category` is `Mapped[str]` (DB) + LLM output — an arbitrary runtime string. The postprocess helpers branch on it and no-op gracefully on unknowns, so `str` is the semantically correct type. `Literal` would force a `cast()` at the call site (typing theater, zero runtime benefit) or runtime validation (behavioural change). → separate ticket only if categories ever become a closed enum.
- **`tool_calls[0]` → loop over all tool_calls:** functional change to the round protocol (N assistant tool_calls + N tool messages, `document_url` semantics for multiple `generate_document` calls), not polish. With `tool_choice="auto"` the model emits one call per round today. → separate PR (PR-15b) with a multi-tool integration test if/when needed.
- **Pagination on `list_templates` (`page` / `per_page`):** ~11 templates total; an API-contract change whose two internal callers (`_get_template_context`, `list_available_templates`) need *all* rows. Low value, regression risk. → separate ticket if the library grows.

> **Note:** neither `except Exception` (ruff `BLE` not in `select`) nor the `[:2000]` magic value (`PLR2004` ignored) is flagged by the project's lint/type gates — PR-15 was discretionary hygiene, scoped to changes that improve correctness without behavioural risk.

**Acceptance:**
- [x] `ruff check` + `ruff format --check` — clean
- [x] `mypy --strict` — no new errors
- [x] Existing chat unit tests pass (21)

---

## 8. Runbook & Operations

### 8.1 Add a new HR user

1. Edit `.env` on production:
   ```bash
   ssh bcv2
   cd /opt/biotact-core-v2
   nano .env
   # Add email to HR_ALLOWED_EMAILS=... (CSV, no spaces)
   ```
2. No restart needed if `HR_ALLOWED_EMAILS` is read from `.env` on each request via `get_settings()`.
3. If cached: `docker compose restart api` (15 sec downtime).

### 8.2 Rollback a deployment

```bash
# Code rollback
ssh bcv2 'cd /opt/biotact-core-v2 && git log --oneline -5 && git revert <merge-commit>'

# DB rollback (if migration was applied)
ssh bcv2 'cd /opt/biotact-core-v2 && docker exec biotact-api alembic downgrade -1'

# Re-deploy
ssh bcv2 'cd /opt/biotact-core-v2 && docker compose up -d --build api'
```

### 8.3 Monitor retention job

```bash
# Check last run
ssh bcv2 'docker logs biotact-api 2>&1 | grep -i "HR retention" | tail -5'

# Check for warnings (unexpected deletions)
ssh bcv2 'docker logs biotact-api 2>&1 | grep -i "HR retention: deleting" | tail -20'
```

### 8.4 Verify HR access control

```bash
ssh bcv2 'docker exec biotact-api python -c "from biotact.core.config import get_settings; print(get_settings().hr_allowed_emails)"'
```

---

## 9. Appendix

### 9.1 Timeline (revised estimate)

| Phase | PRs | Duration | Calendar (est.) |
|---|---|---|---|
| 1.5 Gifts/Events | PR-1, PR-2a | 2-3 days | Days 1-3 |
| 2 Refactor | 4, 5, 6 | 4-5 days | Days 4-8 |
| 3 Versioning | 7, 8, 9 | 3-4 days | Days 9-12 |
| 4 Tests | 10, 11, 12 | 4-5 days | Days 13-17 |
| 5 Quality | 13, 14, 15 | 2-3 days | Days 18-20 |
| **Total** | **14+ PRs** | **15-20 days** | **~4 weeks** |

*Includes review cycles. Single engineer assumption.*

### 9.2 Dependency graph

```
PR-1 (Schema) ──> PR-2a (API) ──> PR-2b (Budgets+Report)
                                      └─> PR-3 (AI Chat Tools)
                                            └─> PR-4 (Frontend)
                                                  └─> PR-5 (QA/Polish)

(Parallel to above — original plan)
PR-5 (extract digest)
  └─> PR-4 (chat decompose)
        └─> PR-6 (dead code)
              └─> PR-7 (versioning schema)
                    ├─> PR-8 (versioning flow)
                    └─> PR-9 (retention)
                          └─> PR-10..12 (tests)
                                └─> PR-13..15 (polish)
```

**Parallel tracks possible:**
- PR-10 (unit tests) can start as soon as PR-4 is merged
- PR-12 (security regression) can start as soon as PR-6 is merged

### 9.3 Open questions before start

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Confirm 3 emails for `HR_ALLOWED_EMAILS` | Шеф | ✅ Done |
| 2 | Confirm transient categories list for PR-9 | Шеф | ⏳ Pending |
| 3 | Frontend ticket: hide HR menu for non-HR | Frontend team | ⏳ Pending |
| 4 | PG version on bcv2 (for PR-7 docstring) | DevOps | ✅ Verified: PG 16 |
| 5 | Is `/download-docx` used by frontend? (PR-6) | Frontend team | ⏳ Pending |

---

*End of document. For questions or updates, edit this file and commit through PR.*
