"""CONDENSE query rewrite service.

Single LLM call (gpt-4o-mini) that rewrites a short follow-up message into a
self-contained search query using chat history. Result is cached in Redis
to amortize latency on repeat queries.

Phase 1 of AskBiotact quality plan. The original message remains the source
of truth for Pilot and for ``detect_safety_trigger`` — CONDENSE output is
intended for retrieval (embedding) only.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from openai import OpenAIError
from redis.exceptions import RedisError

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "condense.txt"
_HISTORY_TAIL = 4
_CONDENSE_MODEL = "gpt-4o-mini"
_CONDENSE_MAX_TOKENS = 120
_CONDENSE_TEMPERATURE = 0.0


@lru_cache(maxsize=1)
def _prompt_template() -> str:
    if not _PROMPT_PATH.exists():
        raise FileNotFoundError(f"CONDENSE prompt not found at {_PROMPT_PATH}")
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _format_history(chat_history: list[dict[str, str]]) -> str:
    """Render the last few turns as plain text for the prompt placeholder."""
    if not chat_history:
        return "(пусто)"
    tail = chat_history[-_HISTORY_TAIL:]
    lines: list[str] = []
    for msg in tail:
        role = "Клиент" if msg.get("role") == "user" else "Бот"
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) or "(пусто)"


def _cache_key(department: str, message: str, history_text: str) -> str:
    """Stable cache key based on original message + rendered history tail."""
    payload = f"{message}\n---\n{history_text}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f"condense:{department}:{digest}"


async def _cache_get(redis: aioredis.Redis, key: str) -> str | None:
    try:
        cached = await redis.get(key)
    except RedisError as e:
        logger.warning("CONDENSE cache read failed: %s", e)
        return None
    if cached is None:
        return None
    return cached if isinstance(cached, str) else cached.decode("utf-8")


async def _cache_set(redis: aioredis.Redis, key: str, value: str, ttl: int) -> None:
    try:
        await redis.set(key, value, ex=ttl)
    except RedisError as e:
        logger.warning("CONDENSE cache write failed: %s", e)


async def condense_query(
    redis: aioredis.Redis | None,
    openai_client: AsyncOpenAI,
    message: str,
    chat_history: list[dict[str, str]],
    *,
    department: str = "askbiotact",
    timeout: float = 2.0,
    cache_ttl: int = 3600,
) -> str:
    """Rewrite a follow-up message into a self-contained search query.

    Returns the condensed query, or the original ``message`` if anything
    goes wrong (timeout, API error, empty response).

    Args:
        redis: Optional Redis client. If ``None``, cache is disabled.
        openai_client: Async OpenAI client (gpt-4o-mini).
        message: Latest user message — also the fallback value.
        chat_history: Recent turns as ``[{"role": "user"|"assistant",
            "content": str}, ...]``. Only the last few turns are used.
        department: Cache key namespace.
        timeout: Hard timeout for the OpenAI call, seconds.
        cache_ttl: TTL for Redis cache entries, seconds.
    """
    history_text = _format_history(chat_history)
    cache_key = _cache_key(department, message, history_text)

    if redis is not None:
        cached = await _cache_get(redis, cache_key)
        if cached:
            logger.info(
                "CONDENSE cache hit: orig='%.80s' cond='%.80s'", message, cached
            )
            return cached

    prompt = _prompt_template().format(chat_history=history_text, question=message)
    started = time.monotonic()

    try:
        response = await asyncio.wait_for(
            openai_client.chat.completions.create(
                model=_CONDENSE_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=_CONDENSE_TEMPERATURE,
                max_tokens=_CONDENSE_MAX_TOKENS,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "CONDENSE timeout (%dms): falling back to original message", latency_ms
        )
        return message
    except OpenAIError as e:
        latency_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "CONDENSE OpenAI error (%dms): %s; falling back to original",
            latency_ms,
            e,
        )
        return message

    latency_ms = int((time.monotonic() - started) * 1000)
    raw = response.choices[0].message.content if response.choices else None
    condensed = (raw or "").strip()

    if not condensed:
        logger.warning(
            "CONDENSE empty response (%dms): falling back to original", latency_ms
        )
        return message

    logger.info(
        "CONDENSE: orig='%.80s' cond='%.80s' lat=%dms",
        message,
        condensed,
        latency_ms,
    )

    if redis is not None:
        await _cache_set(redis, cache_key, condensed, cache_ttl)

    return condensed
