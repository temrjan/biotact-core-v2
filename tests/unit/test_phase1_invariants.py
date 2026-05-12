"""Phase 1 invariants — CONDENSE feeds retrieval, Pilot keeps the original.

Three invariants this module enforces against regression:

1. ``embedding.embed_text`` receives the CONDENSED string.
2. ``llm_service.generate_response`` is called with ``question=<ORIGINAL>``.
3. The search-context hint block is added to ``system_prompt`` iff
   ``condense_query`` returned something different from the original.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.modules.askbiotact.service import AskBiotactService
from biotact.services.rag.qdrant import SearchResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> AskBiotactService:
    svc = AskBiotactService.__new__(AskBiotactService)
    svc._redis = AsyncMock()
    svc._redis.get = AsyncMock(return_value=None)
    svc._redis.set = AsyncMock()
    svc._redis.delete = AsyncMock()
    svc._redis.exists = AsyncMock(return_value=0)
    svc._redis_host = "localhost"
    svc._redis_port = 6379
    svc._extraction_agent = MagicMock(process_and_save=AsyncMock())
    svc._openai_client = MagicMock()
    svc._openai_api_key = "sk-test"
    svc._notification_bot_token = None
    svc._sales_group_chat_id = None
    return svc


@pytest.fixture
def mock_rag() -> dict[str, MagicMock]:
    embedding = MagicMock()
    embedding.embed_text = AsyncMock(return_value=[0.1] * 3072)

    qdrant = MagicMock()
    qdrant.search = AsyncMock(
        return_value=[
            SearchResult(
                content="BIFOLAK NEO — пробиотик.",
                score=0.91,
                source="catalog.txt",
                metadata={"department": "askbiotact"},
            ),
        ]
    )

    llm = MagicMock()
    llm.generate_response = AsyncMock(return_value="Это пробиотик.")

    return {"embedding": embedding, "qdrant": qdrant, "llm": llm}


def _patch_pipeline(
    service: AskBiotactService,
    mock_rag: dict[str, MagicMock],
    condense_return: str,
) -> object:
    """Patch the RAG pipeline dependencies and condense_query.

    Returns a context manager that activates all patches at once.
    """
    import contextlib

    cm = contextlib.ExitStack()
    cm.enter_context(
        patch.object(
            service, "get_customer_context", new_callable=AsyncMock, return_value=None
        )
    )
    cm.enter_context(
        patch(
            "biotact.modules.askbiotact.service.get_embedding_service",
            return_value=mock_rag["embedding"],
        )
    )
    cm.enter_context(
        patch(
            "biotact.modules.askbiotact.service.get_qdrant_service",
            return_value=mock_rag["qdrant"],
        )
    )
    cm.enter_context(
        patch(
            "biotact.modules.askbiotact.service.get_llm_service",
            return_value=mock_rag["llm"],
        )
    )
    cm.enter_context(
        patch(
            "biotact.modules.askbiotact.service.get_active_insight",
            new_callable=AsyncMock,
            return_value=None,
        )
    )
    cm.enter_context(
        patch(
            "biotact.modules.askbiotact.service.condense_query",
            new_callable=AsyncMock,
            return_value=condense_return,
        )
    )
    return cm


# ---------------------------------------------------------------------------
# Invariant 1+2: condensed → embed_text, ORIGINAL → generate_response(question=)
# ---------------------------------------------------------------------------


async def test_condensed_goes_to_embedding_original_goes_to_pilot(
    service: AskBiotactService, mock_rag: dict[str, MagicMock]
) -> None:
    original = "а сколько стоит?"
    condensed = "BIFOLAK NEO цена"

    with _patch_pipeline(service, mock_rag, condense_return=condensed):
        await service.get_ai_response(
            user_id="42",
            message=original,
            history_prefix="public",
        )

    embed_arg = mock_rag["embedding"].embed_text.await_args.args[0]
    assert embed_arg == condensed, (
        "Condensed query must be used for embedding, not the original."
    )

    pilot_kwargs = mock_rag["llm"].generate_response.await_args.kwargs
    assert pilot_kwargs["question"] == original, (
        "Pilot must answer the ORIGINAL question, not the condensed query."
    )


# ---------------------------------------------------------------------------
# Invariant 3: hint block appears iff condensed != original
# ---------------------------------------------------------------------------


async def test_hint_block_present_when_condensed_differs_from_original(
    service: AskBiotactService, mock_rag: dict[str, MagicMock]
) -> None:
    original = "а состав?"
    condensed = "BIFOLAK NEO состав"

    with _patch_pipeline(service, mock_rag, condense_return=condensed):
        await service.get_ai_response(
            user_id="42",
            message=original,
            history_prefix="public",
        )

    system_prompt = mock_rag["llm"].generate_response.await_args.kwargs["system_prompt"]
    assert "ПОИСКОВЫЙ КОНТЕКСТ" in system_prompt
    assert condensed in system_prompt


async def test_hint_block_absent_when_condense_returns_original(
    service: AskBiotactService, mock_rag: dict[str, MagicMock]
) -> None:
    original = "Какой состав BIFOLAK MAGNIY?"

    with _patch_pipeline(service, mock_rag, condense_return=original):
        await service.get_ai_response(
            user_id="42",
            message=original,
            history_prefix="public",
        )

    system_prompt = mock_rag["llm"].generate_response.await_args.kwargs["system_prompt"]
    assert "ПОИСКОВЫЙ КОНТЕКСТ" not in system_prompt
