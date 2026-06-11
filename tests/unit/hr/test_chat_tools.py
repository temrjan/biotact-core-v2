"""Unit tests for HR chat AI tool handlers (PR-5)."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.hr.chat.service import HRChatService


def _make_service(user_id: int = 42) -> HRChatService:
    settings = MagicMock()
    settings.openai_api_key = "sk-test"
    settings.hr_chat_model = "gpt-4o-mini"
    settings.hr_max_tool_rounds = 5
    settings.hr_history_window = 10
    db = MagicMock()
    return HRChatService(settings, db, user_id=user_id)


class TestToolDispatch:
    """_execute_tool dispatches to named handlers."""

    @pytest.mark.unit
    async def test_unknown_tool_returns_error(self) -> None:
        service = _make_service()
        result = await service._execute_tool("unknown_tool", {})
        assert "Неизвестный инструмент" in result


class TestToolCreateGiftRequest:
    """create_gift_request tool."""

    @pytest.mark.unit
    async def test_creates_gift_with_all_fields(self) -> None:
        service = _make_service(user_id=7)
        mock_gift = MagicMock()
        mock_gift.id = 123
        mock_gift.status.value = "new"

        with patch(
            "biotact.modules.hr.chat.service.create_gift",
            new_callable=AsyncMock,
            return_value=mock_gift,
        ):
            result = await service._execute_tool(
                "create_gift_request",
                {
                    "initiator": "HR",
                    "recipient": "Иванов",
                    "occasion": "ДР",
                    "category": "Личный",
                    "budget": 100_000,
                    "presentation_date": "2026-06-20",
                    "comment": "Срочно",
                },
            )

        assert "123" in result
        assert "new" in result

    @pytest.mark.unit
    async def test_responsible_is_always_current_user(self) -> None:
        """The tool never forwards responsible_person_id.

        Even if the model injects it into the args, the create schema has
        no such field — the gifts service assigns the authenticated user
        from user_id.
        """
        service = _make_service(user_id=99)
        mock_gift = MagicMock()
        mock_gift.id = 456
        mock_gift.status.value = "new"

        mock_create_gift = AsyncMock(return_value=mock_gift)
        with patch(
            "biotact.modules.hr.chat.service.create_gift",
            new=mock_create_gift,
        ):
            await service._execute_tool(
                "create_gift_request",
                {
                    "initiator": "HR",
                    "recipient": "Петров",
                    "occasion": "Юбилей",
                    "category": "Корп",
                    "budget": 200_000,
                    "responsible_person_id": 5,
                },
            )

        call_args = mock_create_gift.call_args
        assert call_args.kwargs["user_id"] == 99
        sent_data = call_args.args[1]
        assert "responsible_person_id" not in type(sent_data).model_fields

    @pytest.mark.unit
    async def test_invalid_date_format_returns_error(self) -> None:
        service = _make_service()
        result = await service._execute_tool(
            "create_gift_request",
            {
                "initiator": "HR",
                "recipient": "Сидоров",
                "occasion": "ДР",
                "category": "Личный",
                "budget": 100_000,
                "presentation_date": "не дата",
            },
        )
        assert "Неверный формат даты" in result

    @pytest.mark.unit
    async def test_missing_required_fields_returns_error(self) -> None:
        service = _make_service()
        result = await service._execute_tool(
            "create_gift_request",
            {
                "initiator": "HR",
                "budget": 100_000,
            },
        )
        assert "Не хватает обязательных полей" in result
        assert "recipient" in result
        assert "occasion" in result
        assert "category" in result


class TestToolListUpcomingEvents:
    """list_upcoming_events tool."""

    @pytest.mark.unit
    async def test_lists_events_in_range(self) -> None:
        service = _make_service()
        mock_event = MagicMock()
        mock_event.date = date(2026, 6, 15)
        mock_event.employee_name = "Петрова Мария"
        mock_event.occasion_type.value = "birthday"
        mock_event.department = "Маркетинг"

        mock_result = MagicMock()
        mock_result.items = [mock_event]

        mock_list_events = AsyncMock(return_value=mock_result)
        with patch(
            "biotact.modules.hr.chat.service.list_events",
            new=mock_list_events,
        ):
            result = await service._execute_tool(
                "list_upcoming_events",
                {"days": 14, "department": "Маркетинг"},
            )

        assert "Петрова Мария" in result
        assert "birthday" in result
        call_kwargs = mock_list_events.call_args.kwargs
        assert call_kwargs["department"] == "Маркетинг"
        assert call_kwargs["size"] == 100

    @pytest.mark.unit
    async def test_no_events_returns_message(self) -> None:
        service = _make_service()
        mock_result = MagicMock()
        mock_result.items = []

        with patch(
            "biotact.modules.hr.chat.service.list_events",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await service._execute_tool("list_upcoming_events", {"days": 7})

        assert "не найдено" in result


class TestToolGetGiftStatus:
    """get_gift_status tool."""

    @pytest.mark.unit
    async def test_returns_gift_details(self) -> None:
        service = _make_service()
        mock_gift = MagicMock()
        mock_gift.id = 77
        mock_gift.status.value = "approved"
        mock_gift.recipient = "Иванов"
        mock_gift.occasion = "ДР"
        mock_gift.budget = 300_000
        mock_gift.gift_name = "Часы"
        mock_gift.presentation_date = date(2026, 6, 20)

        with patch(
            "biotact.modules.hr.chat.service.get_gift",
            new_callable=AsyncMock,
            return_value=mock_gift,
        ):
            result = await service._execute_tool("get_gift_status", {"gift_id": 77})

        assert "approved" in result
        assert "Иванов" in result
        assert "300000" in result
        assert "2026-06-20" in result

    @pytest.mark.unit
    async def test_not_found_returns_message(self) -> None:
        service = _make_service()

        with patch(
            "biotact.modules.hr.chat.service.get_gift",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await service._execute_tool("get_gift_status", {"gift_id": 999})

        assert "не найдена" in result

    @pytest.mark.unit
    async def test_missing_gift_id_returns_message(self) -> None:
        service = _make_service()
        result = await service._execute_tool("get_gift_status", {})
        assert "Не указан ID" in result

    @pytest.mark.unit
    async def test_invalid_gift_id_type_returns_message(self) -> None:
        service = _make_service()
        result = await service._execute_tool("get_gift_status", {"gift_id": "abc"})
        assert "Неверный формат ID" in result
