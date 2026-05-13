"""Unit tests for AskBiotactService."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from biotact.modules.askbiotact.schemas import OrderProduct, ParsedOrder, UserInfo
from biotact.modules.askbiotact.service import AskBiotactService


@pytest.fixture
def service() -> AskBiotactService:
    """Create service with mocked dependencies."""
    svc = AskBiotactService.__new__(AskBiotactService)
    svc._redis = None
    svc._redis_host = "localhost"
    svc._redis_port = 6379
    svc._extraction_agent = None
    svc._openai_client = None
    svc._openai_api_key = "sk-test"
    svc._notification_bot_token = "test-token"
    svc._sales_group_chat_id = "-100123"
    return svc


class TestDetectOrder:
    """Tests for order detection logic."""

    def test_detect_order_with_phone_and_keywords(
        self, service: AskBiotactService
    ) -> None:
        history = [
            {"role": "user", "content": "хочу купить биолак"},
            {"role": "assistant", "content": "отлично, напишите телефон"},
        ]
        result = service.detect_order("+998901234567", history)
        assert result is not None
        assert result["phone"] == "+998901234567"

    def test_detect_order_no_phone(self, service: AskBiotactService) -> None:
        history = [{"role": "user", "content": "хочу купить"}]
        result = service.detect_order("просто текст", history)
        assert result is None

    def test_detect_order_phone_but_no_keywords(
        self, service: AskBiotactService
    ) -> None:
        history = [
            {"role": "user", "content": "привет"},
            {"role": "assistant", "content": "здравствуйте"},
        ]
        result = service.detect_order("+998901234567", history)
        assert result is None


class TestFormatOrderForSales:
    """Tests for order formatting."""

    def test_format_with_products(self, service: AskBiotactService) -> None:
        order = ParsedOrder(
            name="Тест",
            phone="+998901234567",
            products=[OrderProduct(name="BIFOLAK NEO", qty=2)],
        )
        user_info = UserInfo(user_id="123", first_name="Test", username="test_user")
        result = service.format_order_for_sales(order, user_info, "+998901234567")

        assert "BIFOLAK NEO" in result
        assert "2 шт." in result
        assert "133 000" in result  # 66500 * 2
        assert "@test_user" in result

    def test_format_empty_order(self, service: AskBiotactService) -> None:
        order = ParsedOrder(phone="+998901234567")
        user_info = UserInfo(user_id="123")
        result = service.format_order_for_sales(order, user_info, "+998901234567")
        assert "+998901234567" in result


class TestChatHistory:
    """Tests for Redis chat history operations."""

    @pytest.mark.asyncio
    async def test_get_history_empty(self, service: AskBiotactService) -> None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        service._redis = mock_redis

        result = await service.get_chat_history("123", "chat")
        assert result == []
        mock_redis.get.assert_called_once_with("chat:123:history")

    @pytest.mark.asyncio
    async def test_save_history_trims(self, service: AskBiotactService) -> None:
        mock_redis = AsyncMock()
        service._redis = mock_redis

        # Create history longer than MAX_HISTORY * 2
        long_history = [{"role": "user", "content": f"msg{i}"} for i in range(30)]
        await service.save_chat_history("123", "public", long_history)

        # Should have been called with trimmed history
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 86400  # HISTORY_TTL

    @pytest.mark.asyncio
    async def test_order_dedup(self, service: AskBiotactService) -> None:
        mock_redis = AsyncMock()
        mock_redis.exists = AsyncMock(return_value=0)
        service._redis = mock_redis

        result = await service.is_order_already_sent("123")
        assert result is False
        mock_redis.exists.assert_called_once_with("order_sent:123")


class TestResetConversation:
    """Tests for conversation reset."""

    @pytest.mark.asyncio
    async def test_reset_clears_history(self, service: AskBiotactService) -> None:
        mock_redis = AsyncMock()
        service._redis = mock_redis

        with patch(
            "biotact.modules.askbiotact.service.archive_insight",
            new_callable=AsyncMock,
        ) as mock_archive:
            await service.reset_conversation("123", "chat")

            mock_redis.delete.assert_called_once_with("chat:123:history")
            mock_archive.assert_called_once_with(123)
