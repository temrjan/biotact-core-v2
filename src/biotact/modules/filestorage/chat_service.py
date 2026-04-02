"""Chat service for document search — OpenAI Function Calling + RAG.

Self-contained handler, does NOT use module_registry or CommandExecutor.
Pattern: same as marketing/chat — separate endpoint with own LLM flow.
"""

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from biotact.core.config import Settings
from biotact.modules.filestorage.schemas import FilesChatResponse, FilesChatSource
from biotact.modules.filestorage.vector_store import FileVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

FILES_SYSTEM_PROMPT = """Ты AI-ассистент общей платформы документов компании Biotact.
Ты помогаешь сотрудникам искать информацию в загруженных документах и сопоставлять данные.

Возможности:
1. Поиск по содержимому всех документов
2. Сопоставление данных из разных файлов
3. Анализ и выводы на основе найденного

Правила:
- Отвечай ТОЛЬКО на основе найденного контекста из документов
- Если информации не найдено — честно скажи об этом
- Указывай имя файла-источника в ответе
- Отвечай на русском, кратко и по делу
- При сопоставлении указывай оба источника
"""

SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_documents",
        "description": "Поиск по содержимому загруженных документов. Используй для любых вопросов о содержимом файлов.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос — что искать в документах",
                },
            },
            "required": ["query"],
        },
    },
}


class FilesChatService:
    """Chat service with RAG over uploaded documents.

    Flow:
    1. Send user message to OpenAI with search_documents tool
    2. If tool_call → embed query → Qdrant search → format context
    3. Second LLM call with context → generate answer with sources
    4. If no tool_call → return direct LLM response
    """

    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService,
        vector_store: FileVectorStore,
    ) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.embedding = embedding_service
        self.vector_store = vector_store

    async def query(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> FilesChatResponse:
        """Process chat message with optional RAG search.

        Args:
            message: User's question.
            history: Previous messages [{role, content}].

        Returns:
            FilesChatResponse with answer and sources.
        """
        # Build messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": FILES_SYSTEM_PROMPT},
        ]
        if history:
            messages.extend(history[-10:])
        messages.append({"role": "user", "content": message})

        # Step 1: Call LLM with tool
        try:
            response = await self.client.chat.completions.create(  # type: ignore[call-overload]
                model=self.model,
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice="auto",
                max_tokens=500,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return FilesChatResponse(
                answer=f"Ошибка при обработке запроса: {e}",
                sources=[],
            )

        choice = response.choices[0].message

        # Step 2: If tool call — do RAG
        if choice.tool_calls:
            return await self._handle_search(message, choice.tool_calls, messages)

        # Step 3: No tool call — direct response
        return FilesChatResponse(
            answer=choice.content or "Не удалось обработать запрос.",
            sources=[],
        )

    async def _handle_search(
        self,
        original_message: str,
        tool_calls: list[Any],
        messages: list[dict[str, Any]],  # noqa: ARG002
    ) -> FilesChatResponse:
        """Handle search_documents tool call.

        Does: embed → Qdrant search → build context → LLM generate answer.
        """
        # Parse search query from tool call
        tc = tool_calls[0]
        try:
            args = json.loads(tc.function.arguments)
            query = args.get("query", original_message)
        except (json.JSONDecodeError, AttributeError):
            query = original_message

        logger.info(f"Document search: {query!r}")

        # Embed query
        query_vector = await self.embedding.embed_text(query)

        # Search Qdrant (all users — shared platform)
        results = await self.vector_store.search(
            query_vector=query_vector,
            limit=5,
            score_threshold=0.3,
        )

        if not results:
            return FilesChatResponse(
                answer="По вашему запросу ничего не найдено в загруженных документах.",
                sources=[],
            )

        # Build context for LLM
        context_parts: list[str] = []
        sources: list[FilesChatSource] = []
        seen_files: set[str] = set()

        for r in results:
            file_name = str(r["file_name"])
            content = str(r["content"])
            score = float(r["score"])

            context_parts.append(f"[{file_name}]:\n{content}")

            if file_name not in seen_files:
                sources.append(FilesChatSource(file_name=file_name, score=score))
                seen_files.add(file_name)

        context_str = "\n\n---\n\n".join(context_parts)

        # Step 3: Generate answer with context
        answer_messages: list[dict[str, Any]] = [
            {"role": "system", "content": FILES_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Контекст из документов:\n{context_str}\n\n"
                    f"Вопрос пользователя: {original_message}\n\n"
                    f"Ответь на основе контекста. Указывай имена файлов-источников."
                ),
            },
        ]

        try:
            answer_response = await self.client.chat.completions.create(  # type: ignore[arg-type]
                model=self.model,
                messages=answer_messages,
                max_tokens=1000,
                temperature=0.3,
            )
            answer = answer_response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Failed to generate answer: {e}")
            answer = "Найдены релевантные документы, но не удалось сформировать ответ."

        return FilesChatResponse(answer=answer, sources=sources)
