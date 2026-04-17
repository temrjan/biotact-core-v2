"""Unified RAG chat across media transcriptions and other knowledge collections.

Searches 5 Qdrant collections in parallel, merges by score, feeds the
top contexts into the LLM with cite-your-sources instructions.
"""

import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

from biotact.core.config import Settings
from biotact.modules.media.schemas import (
    ChatMessage,
    MediaChatResponse,
    MediaChatSource,
)
from biotact.modules.media.utils import translate_to_english
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class CollectionConfig:
    """Describes how to search a Qdrant collection."""

    key: str  # short id used as source_type (e.g. "media")
    name: str  # actual Qdrant collection name
    language: str  # "ru" or "en"
    text_field: str = "content"
    text_field_alt: str | None = None
    title_field: str | None = None  # payload field to use as display title
    ref_field: str | None = None  # payload field to expose as ref_id


SOURCES: list[CollectionConfig] = [
    CollectionConfig(
        key="media",
        name="media_transcriptions",
        language="ru",
        title_field="title",
        ref_field="transcription_id",
    ),
    CollectionConfig(
        key="files",
        name="user_files",
        language="ru",
        title_field="file_name",
    ),
    CollectionConfig(
        key="biotact",
        name="knowledge-evolution",
        language="ru",
    ),
    CollectionConfig(
        key="dr_berg",
        name="dr_berg",
        language="en",
        text_field_alt="text",
    ),
    CollectionConfig(
        key="nutrition",
        name="nutrition_library",
        language="en",
    ),
]

TOP_PER_COLLECTION = 4
TOP_FINAL = 8
SCORE_THRESHOLD = 0.3
SNIPPET_CHARS = 220

SYSTEM_PROMPT = """Ты AI-ассистент медиа-раздела Biotact.

Твоя задача — найти ответ в предоставленных фрагментах из разных источников: транскриптах встреч, документах компании, внешних медицинских базах.

Правила:
- Опирайся ТОЛЬКО на приведённый контекст.
- Если информации нет — честно скажи.
- В ответе ссылайся на источник: тип и название (например, "в записи «Совещание по продуктам»").
- Отвечай кратко и по делу, на русском.
- Не выдумывай детали, которых нет в контексте."""


@dataclass
class _ChunkHit:
    """Intermediate search hit before reformatting into MediaChatSource."""

    source_type: str
    title: str
    content: str
    score: float
    ref_id: str | None = None
    payload: dict[str, object] = field(default_factory=dict)


class MediaChatService:
    """Unified chat across media transcriptions and knowledge collections."""

    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService,
    ) -> None:
        self.settings = settings
        self.embedding = embedding_service
        self.llm = AsyncOpenAI(api_key=settings.openai_api_key)
        self.qdrant = AsyncQdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            api_key=settings.qdrant_api_key,
        )
        self.model = settings.openai_model

    async def query(
        self,
        message: str,
        history: list[ChatMessage] | None = None,
    ) -> MediaChatResponse:
        """Run unified RAG: embed → parallel search → LLM answer with citations."""
        import asyncio

        if not message.strip():
            return MediaChatResponse(answer="Введите сообщение.", sources=[])

        query_ru = message.strip()
        query_en = await translate_to_english(self.llm, query_ru)

        try:
            embed_ru, embed_en = await asyncio.gather(
                self.embedding.embed_text(query_ru),
                self.embedding.embed_text(query_en)
                if query_en != query_ru
                else self.embedding.embed_text(query_ru),
            )
        except Exception:
            logger.exception("Embedding query failed")
            return MediaChatResponse(
                answer="Не удалось подготовить поиск. Попробуйте позже.",
                sources=[],
            )

        hits = await self._search_all(embed_ru, embed_en)
        if not hits:
            return MediaChatResponse(
                answer="По запросу ничего не найдено в доступных источниках.",
                sources=[],
            )

        answer = await self._generate_answer(query_ru, history, hits)
        return MediaChatResponse(
            answer=answer,
            sources=[self._hit_to_source(h) for h in hits],
        )

    # ──────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────

    async def _search_all(
        self,
        embedding_ru: list[float],
        embedding_en: list[float],
    ) -> list[_ChunkHit]:
        """Parallel search across all configured collections, merged by score."""
        import asyncio

        tasks = [
            self._search_one(
                config,
                embedding_en if config.language == "en" else embedding_ru,
            )
            for config in SOURCES
        ]
        per_collection = await asyncio.gather(*tasks, return_exceptions=True)

        hits: list[_ChunkHit] = []
        for result in per_collection:
            if isinstance(result, BaseException):
                logger.warning("Collection search failed: %s", result)
                continue
            hits.extend(result)

        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:TOP_FINAL]

    async def _search_one(
        self,
        config: CollectionConfig,
        embedding: list[float],
    ) -> list[_ChunkHit]:
        """Query a single collection and convert points to hits."""
        try:
            response = await self.qdrant.query_points(
                collection_name=config.name,
                query=embedding,
                limit=TOP_PER_COLLECTION,
                score_threshold=SCORE_THRESHOLD,
            )
        except Exception as exc:
            logger.warning("Search %s failed: %s", config.name, exc)
            return []

        results: list[_ChunkHit] = []
        for point in response.points:
            payload = point.payload or {}
            content = self._extract_content(payload, config)
            if not content:
                continue
            title = self._extract_title(payload, config)
            ref_id = (
                str(payload[config.ref_field])
                if config.ref_field and payload.get(config.ref_field)
                else None
            )
            results.append(
                _ChunkHit(
                    source_type=config.key,
                    title=title,
                    content=content,
                    score=float(point.score),
                    ref_id=ref_id,
                    payload={
                        k: v for k, v in payload.items() if k != config.text_field
                    },
                )
            )
        return results

    @staticmethod
    def _extract_content(payload: dict[str, object], config: CollectionConfig) -> str:
        """Read chunk text, handling different field names across collections."""
        value = payload.get(config.text_field)
        if not value and config.text_field_alt:
            value = payload.get(config.text_field_alt)
        return str(value or "").strip()

    @staticmethod
    def _extract_title(payload: dict[str, object], config: CollectionConfig) -> str:
        """Choose a human-readable title for the source card."""
        if config.title_field:
            title = payload.get(config.title_field)
            if title:
                return str(title)
        for fallback in ("title", "file_name", "source", "name"):
            candidate = payload.get(fallback)
            if candidate:
                return str(candidate)
        return config.key

    @staticmethod
    def _snippet(content: str) -> str:
        content = content.strip()
        if len(content) <= SNIPPET_CHARS:
            return content
        return content[:SNIPPET_CHARS] + "…"

    def _hit_to_source(self, hit: _ChunkHit) -> MediaChatSource:
        return MediaChatSource(
            source_type=hit.source_type,
            title=hit.title,
            snippet=self._snippet(hit.content),
            score=round(hit.score, 4),
            ref_id=hit.ref_id,
        )

    async def _generate_answer(
        self,
        message: str,
        history: list[ChatMessage] | None,
        hits: list[_ChunkHit],
    ) -> str:
        """Build LLM messages with citations and return the assistant reply."""
        context_parts = [
            f"[{hit.source_type} · {hit.title}]\n{hit.content}" for hit in hits
        ]
        context = "\n\n---\n\n".join(context_parts)

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(
                {"role": m.role, "content": m.content} for m in history[-10:]
            )
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Контекст:\n{context}\n\n"
                    f"Вопрос: {message}\n\n"
                    "Ответь на основе контекста, указывая тип и название источника."
                ),
            }
        )

        try:
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.3,
                max_tokens=800,
            )
        except Exception:
            logger.exception("Chat LLM call failed")
            return "Не удалось получить ответ. Попробуйте позже."

        return response.choices[0].message.content or "Пустой ответ модели."
