"""Integration tests for deterministic template resolution.

Requires PostgreSQL (HR models use JSONB / partial indexes); skipped on SQLite.
Core regression: a render-eligible template with ``extracted_text = NULL`` must
resolve (the prod bug hid 9/11 templates, incl. NDA, behind that gate).
"""

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.models.user import User
from biotact.modules.hr.library.models import HRTemplate
from biotact.modules.hr.library.service import (
    get_template_by_category,
    resolve_template,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="HR templates use PostgreSQL-specific types; requires PostgreSQL",
)


async def _add_template(
    session: AsyncSession,
    user_id: int,
    *,
    category: str,
    name: str,
    template_fields: list[str] | None,
    version: int = 1,
    is_active: bool = True,
    extracted_text: str | None = None,
) -> HRTemplate:
    template = HRTemplate(
        name=name,
        category=category,
        file_path=f"/tmp/{name}",
        file_type="docx",
        file_size=100,
        extracted_text=extracted_text,
        template_fields=template_fields,
        version=version,
        is_active=is_active,
        uploaded_by=user_id,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@pytest.mark.asyncio
async def test_resolves_template_with_null_extracted_text(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """REGRESSION: render-eligible template with NULL extracted_text resolves."""
    template = await _add_template(
        test_session,
        test_user.id,
        category="nda_rabotnik",
        name="NDA.docx",
        template_fields=["DIRECTOR_FIO_LATIN"],
        extracted_text=None,  # the prod condition that hid it
    )

    result = await resolve_template(test_session, "nda_rabotnik")

    assert result.match is not None, (
        "template must be found despite NULL extracted_text"
    )
    assert result.match.id == template.id
    assert result.match.extracted_text is None  # proves the gate is NOT extracted_text
    assert result.match.template_fields == ["DIRECTOR_FIO_LATIN"]

    # The single-category primitive uses the same fixed gate.
    active = await get_template_by_category(test_session, "nda_rabotnik")
    assert active is not None
    assert active.id == template.id


@pytest.mark.asyncio
async def test_null_template_fields_excluded(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """A template with no fields is not render-eligible -> not offered."""
    await _add_template(
        test_session,
        test_user.id,
        category="broken",
        name="broken.docx",
        template_fields=None,
    )

    result = await resolve_template(test_session, "broken")

    assert result.match is None
    assert result.candidates == []


@pytest.mark.asyncio
async def test_empty_template_fields_excluded(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """An empty field list is not render-eligible (the ``пуст`` edge)."""
    await _add_template(
        test_session,
        test_user.id,
        category="emptyfields",
        name="empty.docx",
        template_fields=[],
    )

    result = await resolve_template(test_session, "emptyfields")

    assert result.match is None
    assert result.candidates == []


@pytest.mark.asyncio
async def test_inactive_version_excluded_latest_active_wins(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Only the active latest version is a candidate (versioning)."""
    await _add_template(
        test_session,
        test_user.id,
        category="td_osnovnoy",
        name="v1.docx",
        template_fields=["FIO_LATIN"],
        version=1,
        is_active=False,
    )
    active = await _add_template(
        test_session,
        test_user.id,
        category="td_osnovnoy",
        name="v2.docx",
        template_fields=["FIO_LATIN"],
        version=2,
        is_active=True,
    )

    result = await resolve_template(test_session, "td_osnovnoy")

    assert result.match is not None
    assert result.match.id == active.id
    assert len(result.candidates) == 1


@pytest.mark.asyncio
async def test_empty_library_returns_no_candidates(
    test_session: AsyncSession,
) -> None:
    """No render-eligible templates -> empty candidate list (tool says 'upload')."""
    result = await resolve_template(test_session, "nda_rabotnik")

    assert result.match is None
    assert result.candidates == []


@pytest.mark.asyncio
async def test_ambiguous_query_returns_candidate_list(
    test_session: AsyncSession,
    test_user: User,
) -> None:
    """Ambiguous query -> no single match, but the full candidate list."""
    await _add_template(
        test_session,
        test_user.id,
        category="nda_rabotnik",
        name="NDA работник.docx",
        template_fields=["A"],
    )
    await _add_template(
        test_session,
        test_user.id,
        category="nda_gpd",
        name="NDA ГПД.docx",
        template_fields=["B"],
    )

    result = await resolve_template(test_session, "nda")

    assert result.match is None
    assert {c.category for c in result.candidates} == {"nda_rabotnik", "nda_gpd"}
