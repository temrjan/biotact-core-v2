"""Tests for the CONDENSE query rewrite service."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIError
from redis.exceptions import RedisError

from biotact.services.condense import (
    _cache_key,
    _format_history,
    condense_query,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_openai(content: str | None = "BIFOLAK NEO цена") -> MagicMock:
    """Build an AsyncOpenAI mock returning ``content`` from chat.completions."""
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _mk_redis(
    get_return: str | bytes | None = None,
    get_side_effect: Exception | None = None,
    set_side_effect: Exception | None = None,
) -> MagicMock:
    """Build a Redis mock with configurable get/set behavior."""
    client = MagicMock()
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(return_value=get_return)
    if set_side_effect is not None:
        client.set = AsyncMock(side_effect=set_side_effect)
    else:
        client.set = AsyncMock(return_value=True)
    return client


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_format_history_empty() -> None:
    assert _format_history([]) == "(пусто)"


def test_format_history_renders_roles() -> None:
    history = [
        {"role": "user", "content": "расскажи про BIFOLAK NEO"},
        {"role": "assistant", "content": "BIFOLAK NEO — пробиотик."},
    ]
    rendered = _format_history(history)
    assert "Клиент: расскажи про BIFOLAK NEO" in rendered
    assert "Бот: BIFOLAK NEO — пробиотик." in rendered


def test_format_history_truncates_to_tail() -> None:
    history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
    rendered = _format_history(history)
    # Only last 4 turns are surfaced
    assert "msg9" in rendered
    assert "msg6" in rendered
    assert "msg5" not in rendered


def test_format_history_skips_empty_content() -> None:
    history = [
        {"role": "user", "content": "   "},
        {"role": "assistant", "content": "ok"},
    ]
    rendered = _format_history(history)
    assert rendered == "Бот: ok"


def test_cache_key_is_stable_and_unique() -> None:
    k1 = _cache_key("askbiotact", "сколько стоит?", "Клиент: BIFOLAK NEO")
    k2 = _cache_key("askbiotact", "сколько стоит?", "Клиент: BIFOLAK NEO")
    k3 = _cache_key("askbiotact", "состав?", "Клиент: BIFOLAK NEO")
    k4 = _cache_key("hr", "сколько стоит?", "Клиент: BIFOLAK NEO")
    assert k1 == k2
    assert k1 != k3
    assert k1 != k4
    assert k1.startswith("condense:askbiotact:")


# ---------------------------------------------------------------------------
# condense_query — happy path & cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_condense_returns_llm_output_when_no_cache() -> None:
    openai = _mk_openai("BIFOLAK NEO цена")
    redis = _mk_redis(get_return=None)

    result = await condense_query(redis, openai, "а сколько стоит?", [])

    assert result == "BIFOLAK NEO цена"
    openai.chat.completions.create.assert_awaited_once()
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_condense_returns_cached_value_and_skips_openai() -> None:
    openai = _mk_openai("should not be called")
    redis = _mk_redis(get_return="BIFOLAK NEO цена")

    result = await condense_query(redis, openai, "а сколько стоит?", [])

    assert result == "BIFOLAK NEO цена"
    openai.chat.completions.create.assert_not_awaited()
    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_condense_decodes_bytes_from_redis() -> None:
    openai = _mk_openai("should not be called")
    redis = _mk_redis(get_return=b"BIFOLAK NEO \xd0\xbe\xd0\xbf\xd0\xb8\xd1\x81")

    result = await condense_query(redis, openai, "состав?", [])

    assert result == "BIFOLAK NEO опис"
    openai.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_condense_works_without_redis() -> None:
    openai = _mk_openai("BIFOLAK MAGNIY состав")

    result = await condense_query(None, openai, "состав?", [])

    assert result == "BIFOLAK MAGNIY состав"
    openai.chat.completions.create.assert_awaited_once()


# ---------------------------------------------------------------------------
# Fallback contract — never breaks pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_condense_falls_back_on_timeout() -> None:
    async def slow_call(*args, **kwargs):
        await asyncio.sleep(10)

    openai = MagicMock()
    openai.chat.completions.create = slow_call

    result = await condense_query(None, openai, "оригинал", [], timeout=0.01)

    assert result == "оригинал"


@pytest.mark.asyncio
async def test_condense_falls_back_on_openai_error() -> None:
    openai = MagicMock()
    openai.chat.completions.create = AsyncMock(
        side_effect=APIError("boom", request=MagicMock(), body=None)
    )

    result = await condense_query(None, openai, "оригинал", [])

    assert result == "оригинал"


@pytest.mark.asyncio
async def test_condense_falls_back_on_empty_response() -> None:
    openai = _mk_openai(content="")

    result = await condense_query(None, openai, "оригинал", [])

    assert result == "оригинал"


@pytest.mark.asyncio
async def test_condense_falls_back_on_none_content() -> None:
    openai = _mk_openai(content=None)

    result = await condense_query(None, openai, "оригинал", [])

    assert result == "оригинал"


# ---------------------------------------------------------------------------
# Redis errors — degrade gracefully, do not crash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_condense_survives_redis_read_error() -> None:
    openai = _mk_openai("recovered")
    redis = _mk_redis(get_side_effect=RedisError("read down"))

    result = await condense_query(redis, openai, "оригинал", [])

    assert result == "recovered"
    openai.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_condense_survives_redis_write_error() -> None:
    openai = _mk_openai("computed")
    redis = _mk_redis(set_side_effect=RedisError("write down"))

    result = await condense_query(redis, openai, "оригинал", [])

    assert result == "computed"


# ---------------------------------------------------------------------------
# Prompt construction — verify what we send to gpt-4o-mini
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_condense_sends_prompt_with_history_and_question() -> None:
    openai = _mk_openai("cond")
    history = [
        {"role": "user", "content": "расскажи про BIFOLAK NEO"},
        {"role": "assistant", "content": "BIFOLAK NEO — пробиотик."},
    ]

    await condense_query(None, openai, "а сколько стоит?", history)

    call = openai.chat.completions.create.await_args
    assert call.kwargs["model"] == "gpt-4o-mini"
    assert call.kwargs["temperature"] == 0.0
    assert call.kwargs["max_tokens"] == 120
    messages = call.kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    prompt = messages[0]["content"]
    assert "Клиент: расскажи про BIFOLAK NEO" in prompt
    assert "ВОПРОС: а сколько стоит?" in prompt


@pytest.mark.asyncio
async def test_condense_strips_whitespace_from_llm_output() -> None:
    openai = _mk_openai("  BIFOLAK NEO цена  \n")

    result = await condense_query(None, openai, "сколько?", [])

    assert result == "BIFOLAK NEO цена"


@pytest.mark.asyncio
async def test_condense_caches_by_original_not_condensed() -> None:
    """Cache key uses (original message + history), so the same follow-up
    from the same client hits the cache regardless of LLM non-determinism."""
    openai_1 = _mk_openai("rewrite A")
    openai_2 = _mk_openai("rewrite B — should never be returned")
    redis = _mk_redis(get_return=None)

    first = await condense_query(redis, openai_1, "состав?", [])
    assert first == "rewrite A"

    # Simulate the cache being populated after the first call.
    redis.get = AsyncMock(return_value="rewrite A")
    second = await condense_query(redis, openai_2, "состав?", [])

    assert second == "rewrite A"
    openai_2.chat.completions.create.assert_not_awaited()
