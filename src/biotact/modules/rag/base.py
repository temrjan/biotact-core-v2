"""Base service for RAG-based modules.

RAG modules handle user requests through knowledge retrieval:
1. User sends natural language question
2. Question is embedded using OpenAI
3. Qdrant is searched with department filter
4. Retrieved context is passed to LLM for response generation
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from biotact.modules.base import RAGModuleConfig
from biotact.services.rag.qdrant import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class RAGResult:
    """Result of RAG query.

    Attributes:
        answer: Generated response from LLM.
        sources: List of retrieved sources.
        confidence: Optional confidence score.
    """

    answer: str
    sources: list[SearchResult]
    confidence: float | None = None


class BaseRAGService(ABC):
    """Base service for RAG-based department modules.

    Provides common functionality for RAG processing.
    Subclasses can override methods to customize behavior.

    Example:
        >>> class CallCenterService(BaseRAGService):
        ...     def format_response(self, answer: str, sources: list) -> str:
        ...         # Custom formatting for call center
        ...         return f"{answer}\\n\\nИсточники: {len(sources)}"
    """

    def __init__(self, config: RAGModuleConfig) -> None:
        """Initialize RAG service.

        Args:
            config: Module configuration with prompts and RAG params.
        """
        self.config = config

    @property
    def system_prompt(self) -> str:
        """Get system prompt for this module."""
        return self.config.system_prompt

    @property
    def rag_limit(self) -> int:
        """Get maximum number of search results."""
        return self.config.rag_limit

    @property
    def score_threshold(self) -> float:
        """Get minimum similarity score threshold."""
        return self.config.score_threshold

    @property
    def department_filter(self) -> str:
        """Get Qdrant department filter value."""
        return self.config.department_filter or self.config.department_id

    def get_search_filter(self) -> dict[str, Any]:
        """Get Qdrant filter for this module.

        Returns:
            Filter dictionary for Qdrant search.
        """
        return {
            "must": [
                {
                    "key": "department",
                    "match": {"value": self.department_filter}
                }
            ]
        }

    def build_context_prompt(self, sources: list[SearchResult]) -> str:
        """Build context section for LLM prompt.

        Args:
            sources: Retrieved search results.

        Returns:
            Formatted context string.
        """
        if not sources:
            return "Релевантные документы не найдены в базе знаний."

        context_parts = []
        for i, source in enumerate(sources, 1):
            context_parts.append(
                f"[Документ {i}] (релевантность: {source.score:.2f})\n"
                f"Источник: {source.source}\n"
                f"{source.content}\n"
            )

        return "\n---\n".join(context_parts)

    def format_response(
        self,
        answer: str,
        sources: list[SearchResult],  # noqa: ARG002
    ) -> str:
        """Format final response with sources.

        Override in subclasses for custom formatting.

        Args:
            answer: Generated answer from LLM.
            sources: Retrieved sources.

        Returns:
            Formatted response string.
        """
        return answer

    def filter_sources(self, sources: list[SearchResult]) -> list[SearchResult]:
        """Filter sources by score threshold.

        Args:
            sources: Raw search results.

        Returns:
            Filtered sources above threshold.
        """
        return [s for s in sources if s.score >= self.score_threshold]

    def should_use_fallback(self, sources: list[SearchResult]) -> bool:
        """Check if fallback response should be used.

        Args:
            sources: Retrieved sources.

        Returns:
            True if no relevant sources found.
        """
        filtered = self.filter_sources(sources)
        return len(filtered) == 0

    @abstractmethod
    def get_fallback_response(self) -> str:
        """Get fallback response when no sources found.

        Override for department-specific fallback.

        Returns:
            Fallback message.
        """
        pass

    async def process_query(
        self,
        question: str,  # noqa: ARG002 - used by subclasses
        sources: list[SearchResult],
        chat_history: list[dict[str, str]] | None = None,  # noqa: ARG002
    ) -> RAGResult:
        """Process query with retrieved sources.

        This method will be called by ChatService after Qdrant search.

        Args:
            question: User's question.
            sources: Retrieved search results.
            chat_history: Previous messages for context.

        Returns:
            RAGResult with answer and sources.
        """
        # Filter sources
        filtered_sources = self.filter_sources(sources)

        # Check for fallback
        if self.should_use_fallback(filtered_sources):
            return RAGResult(
                answer=self.get_fallback_response(),
                sources=[],
                confidence=0.0,
            )

        # Build context for LLM (used by ChatService)
        _ = self.build_context_prompt(filtered_sources)

        # Placeholder - actual generation happens in ChatService
        return RAGResult(
            answer="",  # Will be filled by LLM
            sources=filtered_sources,
            confidence=max(s.score for s in filtered_sources) if filtered_sources else 0.0,
        )
