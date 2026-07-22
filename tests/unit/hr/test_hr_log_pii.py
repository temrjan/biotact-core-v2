"""HR INFO logs must never carry field VALUES (passports, addresses, ФИО).

Enabling INFO for ``biotact.modules.hr`` is only safe if the call-sites log
field names / counts / ids — not values. Guards the sites fixed in PR-A:
``service`` tool-call args and the ``documents`` render logs (happy + failing).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.hr.chat.documents import generate_hr_document
from biotact.modules.hr.chat.service import HRChatService

_PASSPORT = "AE4049022"
_ADDRESS = "г. Ташкент, Сергелийский район, ул. Навруз, д.109"


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key="sk-test",
        hr_chat_model="gpt-test",
        hr_max_tool_rounds=5,
        hr_history_window=10,
    )


def _tool_call_response(name: str, arguments: dict[str, object]) -> SimpleNamespace:
    tool_call = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )
    message = SimpleNamespace(content="", tool_calls=[tool_call])
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="tool_calls", message=message)],
        usage=None,
    )


def _final_response() -> SimpleNamespace:
    message = SimpleNamespace(content="готово", tool_calls=None)
    return SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=message)],
        usage=None,
    )


@pytest.mark.asyncio
async def test_tool_call_args_values_not_logged(hr_log_lines: list[str]) -> None:
    """The ``HR tool:`` log records arg KEYS, never the PII arg values."""
    pii_args = {
        "template_id": 12,
        "data": {"PASSPORT": _PASSPORT, "ADDRESS": _ADDRESS},
    }
    create = AsyncMock(
        side_effect=[
            _tool_call_response("generate_document", pii_args),
            _final_response(),
        ]
    )
    templates = AsyncMock(return_value=[])
    with (
        patch("biotact.modules.hr.chat.service.AsyncOpenAI") as mock_cls,
        patch("biotact.modules.hr.chat.service.list_render_eligible", new=templates),
        patch(
            "biotact.modules.hr.chat.service.generate_hr_document",
            new=AsyncMock(return_value="/api/v1/hr/documents/download/abc"),
        ),
    ):
        mock_cls.return_value.chat.completions.create = create
        service = HRChatService(_settings(), MagicMock(), user_id=1)
        await service.process_message("создай nda", history=[])

    joined = "\n".join(hr_log_lines)
    assert "HR tool: generate_document" in joined  # the site fired
    assert "args_keys=" in joined
    assert _PASSPORT not in joined  # ← would fail under the old `args=%s` logging
    assert _ADDRESS not in joined


@pytest.mark.asyncio
async def test_render_failure_does_not_leak_field_values(
    hr_log_lines: list[str],
) -> None:
    """A failing render logs the template id, not the ``data`` values."""
    db_template = SimpleNamespace(
        id=12,
        category="nda_gpd",
        name="nda_gpd.docx",
        file_path="/app/data/hr_templates/x.docx",
        template_fields=["GPD_NUMBER", "PASSPORT"],
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = db_template
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    args = {"template_id": 12, "data": {"GPD_NUMBER": "4", "PASSPORT": _PASSPORT}}
    with patch(
        "biotact.modules.hr.chat.documents.render_template",
        side_effect=ValueError("render boom"),
    ):
        message = await generate_hr_document(
            db,
            args,
            openai=MagicMock(),
            model="gpt-test",
            user_id=1,
            messages_context="",
            now=datetime(2026, 7, 20, tzinfo=UTC),
        )

    assert message.startswith("Ошибка рендеринга")
    joined = "\n".join(hr_log_lines)
    assert "Render failed for template 12" in joined  # the site fired
    assert _PASSPORT not in joined  # value must not ride the traceback into logs
