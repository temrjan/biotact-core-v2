"""The chat only ever sees the active version of a template.

Versioning (#52-#54) made a category hold several rows: replacing a template
supersedes the previous one, and rolling back re-activates an older version. The
chat was never taught about it — both places that show templates to the model
went through ``list_templates``, which filters nothing, while the deterministic
matcher behind ``find_template`` correctly filtered on ``is_active``.

Nothing in what the model is shown distinguishes the versions — no ``version``,
no ``is_active`` — so once a category held two rows the choice between a current
and a superseded contract was arbitrary and silent. That is not fixable by
prompting: the model cannot select on a signal it was never given.

Where each property is pinned, and why: the exclusion itself lives in SQL, so it
is asserted on the statement sent to the database rather than re-implemented in
a double (a double that filtered rows itself would only prove the double works).
The chat-facing paths are then pinned to the shared source, which is what stops
them drifting apart again.

The library tab keeps listing every version flat (that is #54's rollback UI);
only the two chat-facing paths are filtered.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.hr.chat.documents import generate_hr_document
from biotact.modules.hr.chat.service import HRChatService
from biotact.modules.hr.library.service import list_render_eligible


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key="sk-test",
        hr_chat_model="gpt-test",
        hr_max_tool_rounds=5,
        hr_history_window=10,
    )


def _row(
    template_id: int,
    category: str,
    *,
    version: int,
    fields: list[str] | None,
) -> SimpleNamespace:
    """A template row as the library layer hands it over."""
    return SimpleNamespace(
        id=template_id,
        name=f"{category}_v{version}.docx",
        category=category,
        template_fields=fields,
        version=version,
    )


_ACTIVE = _row(4, "td_osnovnoy", version=2, fields=["FIO_LATIN"])


def _capturing_db(rows: list[SimpleNamespace]) -> tuple[MagicMock, dict[str, object]]:
    """A DB double that records the statement and yields ``rows``."""
    captured: dict[str, object] = {}

    async def _execute(statement: object) -> MagicMock:
        captured["statement"] = statement
        scalars = MagicMock()
        scalars.all.return_value = rows
        result = MagicMock()
        result.scalars.return_value = scalars
        result.scalar_one_or_none.return_value = rows[0] if rows else None
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    return db, captured


class TestRenderEligibleSource:
    """The single source both chat-facing paths now read."""

    @pytest.mark.asyncio
    async def test_query_excludes_superseded_and_unusable_rows(self) -> None:
        """Superseded versions and templates without placeholders never load."""
        db, captured = _capturing_db([_ACTIVE])

        await list_render_eligible(db)

        where_clause = str(getattr(captured["statement"], "whereclause", ""))
        assert "is_active" in where_clause
        assert "template_fields IS NOT NULL" in where_clause

    @pytest.mark.asyncio
    async def test_row_with_empty_field_list_is_dropped(self) -> None:
        """``IS NOT NULL`` lets an empty JSONB list through; Python catches it."""
        empty = _row(9, "prikaz_priem", version=1, fields=[])
        db, _ = _capturing_db([_ACTIVE, empty])

        eligible = await list_render_eligible(db)

        assert [t.id for t in eligible] == [4]


class TestChatFacingPathsUseTheSharedSource:
    """Both listings the model can see read the filtered source, not all rows.

    Patching the shared source is the assertion: were either path still calling
    ``list_templates``, the patch would go unused and the unfiltered query would
    run instead.
    """

    @pytest.mark.asyncio
    async def test_system_context_is_built_from_eligible_templates(self) -> None:
        source = AsyncMock(return_value=[_ACTIVE])
        service = HRChatService(_settings(), MagicMock(), user_id=1)

        with (
            patch("biotact.modules.hr.chat.service.AsyncOpenAI"),
            patch("biotact.modules.hr.chat.service.list_render_eligible", new=source),
        ):
            context = await service._get_template_context()

        source.assert_awaited_once()
        assert context.startswith("Доступные шаблоны")
        assert "id=4" in context

    @pytest.mark.asyncio
    async def test_system_context_is_empty_when_nothing_is_eligible(self) -> None:
        """Every template superseded or unusable → offer nothing, not a stale row."""
        source = AsyncMock(return_value=[])
        service = HRChatService(_settings(), MagicMock(), user_id=1)

        with (
            patch("biotact.modules.hr.chat.service.AsyncOpenAI"),
            patch("biotact.modules.hr.chat.service.list_render_eligible", new=source),
        ):
            context = await service._get_template_context()

        assert context == ""

    @pytest.mark.asyncio
    async def test_listing_tool_is_built_from_eligible_templates(self) -> None:
        """The tool output carries no id or version — filtering is all it has."""
        source = AsyncMock(return_value=[_ACTIVE])
        service = HRChatService(_settings(), MagicMock(), user_id=1)

        with (
            patch("biotact.modules.hr.chat.service.AsyncOpenAI"),
            patch("biotact.modules.hr.chat.service.list_render_eligible", new=source),
        ):
            listing = await service._tool_list_available_templates({})

        source.assert_awaited_once()
        assert "td_osnovnoy_v2.docx" in listing


class TestGenerateGuard:
    """The server refuses to render from a superseded version."""

    @pytest.mark.asyncio
    async def test_lookup_itself_excludes_superseded_rows(self) -> None:
        """The id alone is not enough to reach a template any more."""
        db, captured = _capturing_db([])

        await generate_hr_document(
            db,
            {"template_id": 2, "data": {}},
            openai=MagicMock(),
            model="gpt-test",
            user_id=1,
            messages_context="ctx",
            now=datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
        )

        # Only the WHERE clause counts: ``select(HRTemplate)`` names is_active
        # among the selected columns regardless of any filtering.
        where_clause = str(getattr(captured["statement"], "whereclause", ""))
        assert "is_active" in where_clause

    @pytest.mark.asyncio
    async def test_stale_template_id_renders_nothing(self) -> None:
        """And the refusal tells the model how to recover."""
        db, _ = _capturing_db([])
        render = MagicMock()

        with patch("biotact.modules.hr.chat.documents.render_template", new=render):
            outcome = await generate_hr_document(
                db,
                {"template_id": 2, "data": {"FIO_LATIN": "IVANOV I. I."}},
                openai=MagicMock(),
                model="gpt-test",
                user_id=1,
                messages_context="ctx",
                now=datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
            )

        assert not outcome.startswith("/api/")
        assert "актуальн" in outcome
        render.assert_not_called()
        db.add.assert_not_called()
