"""LLM-as-judge for faithfulness scoring.

One Pydantic-validated call per case (gpt-4o-mini, temperature=0).
Cached in Redis by hash(answer + chunks) for 7 days to keep nightly cost bounded.
Cache is optional — if Redis is None, every call hits the API.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS: int = 7 * 24 * 3600
JUDGE_MODEL: str = "gpt-4o-mini"
JUDGE_MAX_TOKENS: int = 400

JUDGE_SYSTEM_PROMPT: str = (
    "You are a strict evaluator of RAG answers. "
    "Given a CONTEXT (chunks retrieved from a knowledge base) and an ANSWER "
    "produced by an assistant, decide whether every factual claim in the ANSWER "
    "is supported by the CONTEXT. "
    "If the answer contains numbers, names, or claims not present in the context, "
    "mark it as not faithful. "
    "Respond ONLY in the structured JSON format."
)


class FaithfulnessVerdict(BaseModel):
    """Structured output from the LLM judge."""

    faithful: bool = Field(
        description="True if every factual claim is supported by the context."
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims in the answer that are not in the context.",
    )
    reasoning: str = Field(
        default="",
        description="One-sentence justification.",
    )


class FaithfulnessJudge:
    """LLM-judge wrapper with optional Redis-backed cache."""

    def __init__(
        self,
        openai_api_key: str,
        redis_client: aioredis.Redis | None = None,
        cache_namespace: str = "eval:judge:faithfulness",
    ) -> None:
        self._client = AsyncOpenAI(api_key=openai_api_key)
        self._redis = redis_client
        self._namespace = cache_namespace

    async def score(
        self,
        answer: str,
        chunks_text: list[str],
    ) -> FaithfulnessVerdict | None:
        """Return verdict or None on API failure (caller decides degradation policy)."""
        context = "\n\n---\n\n".join(chunks_text) if chunks_text else "(empty)"
        cache_key = self._cache_key(answer, context)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            response = await self._client.beta.chat.completions.parse(
                model=JUDGE_MODEL,
                temperature=0,
                response_format=FaithfulnessVerdict,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"CONTEXT:\n{context}\n\nANSWER:\n{answer}",
                    },
                ],
                max_completion_tokens=JUDGE_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning("Judge API error: %s", e)
            return None

        verdict = response.choices[0].message.parsed
        if verdict is None:
            logger.warning("Judge returned no parsed content")
            return None

        await self._cache_set(cache_key, verdict)
        return verdict

    def _cache_key(self, answer: str, context: str) -> str:
        digest = hashlib.sha256(
            f"{answer}\n----\n{context}".encode()
        ).hexdigest()
        return f"{self._namespace}:{digest}"

    async def _cache_get(self, key: str) -> FaithfulnessVerdict | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.get(key)
        except Exception as e:
            logger.warning("Judge cache read error: %s", e)
            return None
        if raw is None:
            return None
        try:
            return FaithfulnessVerdict.model_validate_json(raw)
        except Exception as e:
            logger.warning("Judge cache decode error: %s", e)
            return None

    async def _cache_set(self, key: str, verdict: FaithfulnessVerdict) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(
                key,
                verdict.model_dump_json(),
                ex=CACHE_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning("Judge cache write error: %s", e)
