"""Lock the side-effect contract of ``AskBiotactService.process_pure``.

The whole point of the public ``process_pure`` method (vs ``get_ai_response``)
is that the eval harness can call it without polluting production state:
no Redis chat-history writes, no ExtractionAgent firing, no order detection.

These tests catch a future refactor that re-introduces side effects into
the shared ``_process_rag_query`` path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from biotact.modules.askbiotact.service import AskBiotactService


@pytest.fixture
def service() -> AskBiotactService:
    """Service with mocked dependencies (no real Redis / OpenAI / Postgres)."""
    svc = AskBiotactService.__new__(AskBiotactService)
    svc._redis = None
    svc._redis_host = "localhost"
    svc._redis_port = 6379
    svc._extraction_agent = None
    svc._openai_client = None
    svc._openai_api_key = "sk-test"
    svc._notification_bot_token = None
    svc._sales_group_chat_id = None
    return svc


class TestProcessPureSideEffects:
    """``process_pure`` must NOT mutate Redis, NOT fire extraction, NOT order-detect."""

    @pytest.mark.asyncio
    async def test_no_redis_calls(self, service: AskBiotactService) -> None:
        mock_redis = AsyncMock()
        service._redis = mock_redis

        with patch.object(
            service,
            "_process_rag_query",
            new=AsyncMock(return_value="ok"),
        ):
            answer = await service.process_pure(
                message="hi",
                chat_history=[],
                customer_context=None,
                telegram_id=None,
            )

        assert answer == "ok"
        mock_redis.set.assert_not_called()
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()
        mock_redis.exists.assert_not_called()

    @pytest.mark.asyncio
    async def test_extraction_agent_not_fired(
        self, service: AskBiotactService
    ) -> None:
        with (
            patch.object(service, "_get_extraction_agent") as mock_get_agent,
            patch.object(
                service,
                "_process_rag_query",
                new=AsyncMock(return_value="X"),
            ),
        ):
            await service.process_pure(
                message="hi",
                chat_history=[{"role": "user", "content": "hi"}],
                customer_context=None,
                telegram_id=12345,
            )

        mock_get_agent.assert_not_called()


class TestProcessPureDelegation:
    """``process_pure`` forwards the exact arguments to ``_process_rag_query``."""

    @pytest.mark.asyncio
    async def test_forwards_args_verbatim(
        self, service: AskBiotactService
    ) -> None:
        history = [{"role": "user", "content": "X"}]
        with patch.object(
            service,
            "_process_rag_query",
            new=AsyncMock(return_value="forwarded"),
        ) as mock_inner:
            answer = await service.process_pure(
                message="msg",
                chat_history=history,
                customer_context="ctx",
                telegram_id=42,
            )

        assert answer == "forwarded"
        mock_inner.assert_awaited_once_with("msg", history, "ctx", 42)

    @pytest.mark.asyncio
    async def test_default_telegram_id_is_none(
        self, service: AskBiotactService
    ) -> None:
        with patch.object(
            service,
            "_process_rag_query",
            new=AsyncMock(return_value="answer"),
        ) as mock_inner:
            await service.process_pure(message="m", chat_history=[])

        mock_inner.assert_awaited_once_with("m", [], None, None)
