"""The fallback-extraction WIRING, end to end.

test_field_rules_prompts covers the rule *source*; this covers that the source
is actually wired through: ``extract_data_from_context`` builds its prompt from
``build_extractor_rules(category)``, and ``generate_hr_document`` feeds it the
template's real category. These are the mutations Bug №2 was made of
("extractor ignores category", "documents passed the wrong category").
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.hr.chat.documents import generate_hr_document
from biotact.modules.hr.chat.extractor import extract_data_from_context

# Text unique to the nda_gpd rule block — absent from the COMMON block, so its
# presence proves the CATEGORY rules (not just common ones) reached the prompt.
_NDA_GPD_RULE_MARKER = "к которому относится NDA"
_CONTEXT = "гражданско правовой договор №4 от 27.04.2026"


def _openai_capturing(sink: dict[str, object]) -> MagicMock:
    async def _create(**kwargs: object) -> SimpleNamespace:
        sink["messages"] = kwargs["messages"]
        message = SimpleNamespace(content="{}")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(side_effect=_create)
    return openai


@pytest.mark.asyncio
async def test_extractor_prompt_carries_category_rules_fields_and_context() -> None:
    sink: dict[str, object] = {}
    openai = _openai_capturing(sink)

    await extract_data_from_context(
        openai,
        "gpt-test",
        _CONTEXT,
        ["GPD_NUMBER", "GPD_DATE"],
        "nda_gpd",
    )

    prompt = sink["messages"][0]["content"]  # type: ignore[index]
    # Category-specific rule wired in (fails if the extractor ignores category).
    assert _NDA_GPD_RULE_MARKER in prompt
    # Common rules and the requested fields and the conversation are all present.
    assert "FIO_LATIN" in prompt
    assert "GPD_NUMBER" in prompt
    assert _CONTEXT in prompt


@pytest.mark.asyncio
async def test_generate_document_passes_template_category_to_extractor() -> None:
    db_template = SimpleNamespace(
        id=12,
        category="nda_gpd",
        name="nda_gpd.docx",
        file_path="/app/data/hr_templates/x.docx",
        template_fields=["GPD_NUMBER", "GPD_DATE"],
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = db_template
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    captured: dict[str, object] = {}

    async def _extract(
        _openai: object,
        _model: str,
        _context: str,
        _fields: list[str],
        category: str,
    ) -> dict[str, str]:
        captured["category"] = category
        return {}

    with (
        patch(
            "biotact.modules.hr.chat.documents.extract_data_from_context",
            side_effect=_extract,
        ),
        # data is empty → every field missing → the extractor runs; the render
        # then fails, which is irrelevant — we only assert the category passed.
        patch(
            "biotact.modules.hr.chat.documents.render_template",
            side_effect=ValueError("stop after extract"),
        ),
    ):
        await generate_hr_document(
            db,
            {"template_id": 12, "data": {}},
            openai=MagicMock(),
            model="gpt-test",
            user_id=1,
            messages_context="ctx",
            now=datetime(2026, 7, 20, tzinfo=UTC),
        )

    assert captured["category"] == "nda_gpd"
