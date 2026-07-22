"""A document is never rendered with blank placeholders.

``generate_hr_document`` used to render unconditionally: it computed ``missing``,
ran the fallback extractor, merged whatever came back and rendered — without ever
re-checking. docxtpl runs on a default Jinja environment, so an unfilled
``{{ PASSPORT_SERIES }}`` silently became an empty string and the chat still
reported "документ создан". These tests pin the server-side completeness gate.

The gate lives AFTER ``postprocess`` on purpose: ten of the twenty-five fields in
the production ТД templates are derived (SALARY_TEXT, HOURS_WEEK, CONTRACT_DATE…),
so a gate placed before it would interrogate HR about values the system computes
itself. ``test_derived_field_is_not_demanded`` and ``test_absent_date_key_is_not_demanded``
guard that placement.
"""

from __future__ import annotations

import io
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from biotact.modules.hr.chat.documents import generate_hr_document

_URL_PREFIX = "/api/v1/hr/documents/download/"


def _db_returning(db_template: SimpleNamespace) -> MagicMock:
    """A DB double whose single query resolves to ``db_template``."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = db_template
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.flush = AsyncMock()
    return db


def _template(category: str, fields: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        id=12,
        category=category,
        name=f"{category}.docx",
        file_path="/app/data/hr_templates/x.docx",
        template_fields=fields,
    )


async def _run(
    db: MagicMock,
    data: dict[str, str],
    template: SimpleNamespace,
    render_dir: Path,
    *,
    extracted: dict[str, str] | None = None,
) -> tuple[str, MagicMock]:
    """Run the tool with the extractor and the renderer stubbed out.

    Returns the tool result plus the ``render_template`` double, so a test can
    assert the renderer was never reached.
    """
    render = MagicMock(return_value=io.BytesIO(b"rendered-docx"))
    with (
        patch(
            "biotact.modules.hr.chat.documents.extract_data_from_context",
            new=AsyncMock(return_value=extracted or {}),
        ),
        patch("biotact.modules.hr.chat.documents.render_template", new=render),
        patch(
            "biotact.modules.hr.chat.documents.get_settings",
            return_value=SimpleNamespace(hr_render_dir=str(render_dir)),
        ),
    ):
        result = await generate_hr_document(
            db,
            {"template_id": 12, "data": data},
            openai=MagicMock(),
            model="gpt-test",
            user_id=1,
            messages_context="ctx",
            now=datetime(2026, 7, 22, 9, 0, tzinfo=UTC),
        )
    return result, render


class TestGateBlocksIncompleteData:
    """A field the user never supplied stops the document."""

    @pytest.mark.asyncio
    async def test_missing_field_blocks_render(self, tmp_path: Path) -> None:
        template = _template("mat_otvetstvennost", ["FIO_LATIN", "PASSPORT_SERIES"])
        db = _db_returning(template)

        result, render = await _run(
            db, {"FIO_LATIN": "IVANOV I. I."}, template, tmp_path
        )

        assert not result.startswith(_URL_PREFIX)
        # The model is told what to ask for — not handed the whole field list.
        assert "PASSPORT_SERIES" in result
        assert "FIO_LATIN" not in result
        render.assert_not_called()
        db.add.assert_not_called()
        assert list(tmp_path.iterdir()) == []


class TestGateRespectsDerivedFields:
    """Fields the post-processor computes are never demanded from HR."""

    @pytest.mark.asyncio
    async def test_derived_field_is_not_demanded(self, tmp_path: Path) -> None:
        """SALARY_TEXT is generated from SALARY — asking for it would be absurd."""
        template = _template("td_osnovnoy", ["SALARY", "SALARY_TEXT"])
        db = _db_returning(template)

        result, render = await _run(db, {"SALARY": "5000000"}, template, tmp_path)

        assert result.startswith(_URL_PREFIX)
        render.assert_called_once()

    @pytest.mark.asyncio
    async def test_absent_date_key_is_not_demanded(self, tmp_path: Path) -> None:
        """CONTRACT_DATE defaults to today even when the key never arrives.

        The LLM is instructed not to invent data, so it omits the key entirely
        rather than sending it empty. Before the fix ``_fill_date_defaults`` only
        filled keys that were already present, so the gate would have asked HR for
        the contract date on every single document.
        """
        template = _template("gpd_uslugi", ["FIO_LATIN", "CONTRACT_DATE"])
        db = _db_returning(template)

        result, render = await _run(
            db, {"FIO_LATIN": "IVANOV I. I."}, template, tmp_path
        )

        assert result.startswith(_URL_PREFIX)
        render.assert_called_once()
        assert render.call_args.args[1]["CONTRACT_DATE"] == "22.07.2026"


class TestGatePassesCompleteData:
    """Regression: a fully supplied document still renders exactly as before."""

    @pytest.mark.asyncio
    async def test_complete_data_renders_and_persists(self, tmp_path: Path) -> None:
        template = _template("nda_gpd", ["FIO_LATIN", "GPD_NUMBER"])
        db = _db_returning(template)

        result, render = await _run(
            db, {"FIO_LATIN": "IVANOV I. I.", "GPD_NUMBER": "4"}, template, tmp_path
        )

        assert result.startswith(_URL_PREFIX)
        render.assert_called_once()
        db.add.assert_called_once()
        assert len(list(tmp_path.iterdir())) == 1

    @pytest.mark.asyncio
    async def test_extractor_result_satisfies_the_gate(self, tmp_path: Path) -> None:
        """A value recovered by the fallback extractor counts as supplied."""
        template = _template("nda_gpd", ["FIO_LATIN", "GPD_NUMBER"])
        db = _db_returning(template)

        result, render = await _run(
            db,
            {"FIO_LATIN": "IVANOV I. I."},
            template,
            tmp_path,
            extracted={"GPD_NUMBER": "4"},
        )

        assert result.startswith(_URL_PREFIX)
        render.assert_called_once()


class _ListHandler(logging.Handler):
    """Capture fully-rendered log lines (message + any traceback)."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(logging.Formatter("%(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def hr_log_lines() -> Iterator[list[str]]:
    """Capture ``biotact.modules.hr.*`` INFO+ lines regardless of propagation."""
    handler = _ListHandler()
    logger = logging.getLogger("biotact.modules.hr")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield handler.lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


@pytest.mark.asyncio
async def test_blocked_render_logs_names_not_values(
    tmp_path: Path, hr_log_lines: list[str]
) -> None:
    """The gate logs which fields are missing — never what HR already typed."""
    template = _template("mat_otvetstvennost", ["FIO_LATIN", "PASSPORT_SERIES"])
    db = _db_returning(template)
    await _run(db, {"FIO_LATIN": "IVANOV IVAN IVANOVICH"}, template, tmp_path)

    joined = "\n".join(hr_log_lines)
    assert "PASSPORT_SERIES" in joined
    assert "IVANOV IVAN IVANOVICH" not in joined
