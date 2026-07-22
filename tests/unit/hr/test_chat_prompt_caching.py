"""Unit tests for HR chat prompt-caching structure (PR-14).

Verifies the two deliverables of PR-14:
1. The stable instruction block is sent as an isolated system message (a
   byte-identical prefix OpenAI can auto-cache), never concatenated with the
   per-request template list.
2. ``_cached_tokens`` safely reads ``usage.prompt_tokens_details.cached_tokens``
   across the SDK model and lightweight test doubles.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.hr.chat.prompts import SYSTEM_PROMPT
from biotact.modules.hr.chat.service import HRChatService, _cached_tokens


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key="sk-test",
        hr_chat_model="gpt-test",
        hr_max_tool_rounds=5,
        hr_history_window=10,
    )


def _final_response() -> SimpleNamespace:
    """OpenAI response with no tool calls — ends the round loop immediately."""
    message = SimpleNamespace(content="ок", tool_calls=None)
    choice = SimpleNamespace(finish_reason="stop", message=message)
    return SimpleNamespace(choices=[choice], usage=None)


async def _run_and_capture_messages(items: list[object]) -> list[dict[str, object]]:
    """Run process_message with mocked OpenAI + templates, return sent messages."""
    captured: dict[str, list[dict[str, object]]] = {}

    async def _create(**kwargs: object) -> SimpleNamespace:
        captured["messages"] = kwargs["messages"]  # type: ignore[assignment]
        return _final_response()

    templates = AsyncMock(return_value=items)
    with (
        patch("biotact.modules.hr.chat.service.AsyncOpenAI") as mock_cls,
        patch("biotact.modules.hr.chat.service.list_render_eligible", new=templates),
    ):
        mock_cls.return_value.chat.completions.create = AsyncMock(side_effect=_create)
        service = HRChatService(_settings(), MagicMock(), user_id=1)
        await service.process_message("привет", history=[])

    return captured["messages"]


class TestSystemPromptSplit:
    """The cacheable prefix must stay isolated from per-request data."""

    @pytest.mark.asyncio
    async def test_stable_prefix_is_isolated_when_no_templates(self) -> None:
        messages = await _run_and_capture_messages(items=[])
        # First message is exactly SYSTEM_PROMPT — not concatenated with anything.
        assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
        # No empty template message leaked in.
        assert messages[1] == {"role": "user", "content": "привет"}

    @pytest.mark.asyncio
    async def test_templates_go_in_separate_system_message(self) -> None:
        template = SimpleNamespace(
            id=1,
            name="td.docx",
            category="td_osnovnoy",
            template_fields=["FIO"],
        )
        messages = await _run_and_capture_messages(items=[template])
        # Prefix untouched by the dynamic suffix.
        assert messages[0]["content"] == SYSTEM_PROMPT
        # Volatile template list is a distinct, clean system message.
        assert messages[1]["role"] == "system"
        assert messages[1]["content"].startswith("Доступные шаблоны")
        assert "td_osnovnoy" in messages[1]["content"]


class TestCachedTokens:
    """_cached_tokens reads the OpenAI usage detail defensively."""

    def test_returns_value_when_present(self) -> None:
        usage = SimpleNamespace(
            prompt_tokens_details=SimpleNamespace(cached_tokens=512)
        )
        assert _cached_tokens(usage) == 512

    def test_zero_when_usage_missing(self) -> None:
        assert _cached_tokens(None) == 0

    def test_zero_when_details_missing(self) -> None:
        assert _cached_tokens(SimpleNamespace(prompt_tokens_details=None)) == 0

    def test_zero_when_cached_tokens_none(self) -> None:
        usage = SimpleNamespace(
            prompt_tokens_details=SimpleNamespace(cached_tokens=None)
        )
        assert _cached_tokens(usage) == 0
