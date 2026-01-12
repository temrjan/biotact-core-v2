"""Chat service with module routing.

This service routes chat queries to appropriate module handler:
- Command modules (Dashboard): Use Function Calling via CommandExecutor
- RAG modules (CallCenter, Marketing, HR): Use vector search + LLM generation
"""

import logging
from typing import Any

from biotact.models.chat import ChatSession
from biotact.modules import ModuleType, module_registry
from biotact.modules.base import CommandModuleConfig, RAGModuleConfig
from biotact.modules.command.base import BaseCommandService, CommandResult
from biotact.repositories.chat_repo import ChatRepository
from biotact.schemas.chat import (
    ChatQueryResponse,
    ChatSessionResponse,
    ChatSessionsResponse,
    Source,
)
from biotact.services.command_executor import CommandExecutor
from biotact.services.rag import EmbeddingService, LLMService, QdrantService

logger = logging.getLogger(__name__)


class ChatService:
    """Service for chat operations with module routing.

    Routes requests to appropriate handler based on module type:
    - ModuleType.COMMAND → CommandExecutor + Module Service
    - ModuleType.RAG → Qdrant search + LLM generation
    """

    def __init__(
        self,
        chat_repo: ChatRepository,
        embedding_service: EmbeddingService,
        qdrant_service: QdrantService,
        llm_service: LLMService,
        command_executor: CommandExecutor | None = None,
        command_services: dict[str, BaseCommandService] | None = None,
    ) -> None:
        """Initialize chat service.

        Args:
            chat_repo: Repository for chat persistence.
            embedding_service: Service for text embeddings.
            qdrant_service: Service for vector search.
            llm_service: Service for LLM generation.
            command_executor: Executor for Function Calling (optional).
            command_services: Dict of department_id → CommandService (optional).
        """
        self.chat_repo = chat_repo
        self.embedding = embedding_service
        self.qdrant = qdrant_service
        self.llm = llm_service
        self.command_executor = command_executor
        self.command_services = command_services or {}

    def register_command_service(
        self,
        department_id: str,
        service: BaseCommandService,
    ) -> None:
        """Register a command service for a department.

        Args:
            department_id: Department identifier.
            service: Command service instance.
        """
        self.command_services[department_id] = service

    async def query(
        self,
        user_id: int,
        department_id: str,
        message: str,
        session_id: str | None = None,
    ) -> ChatQueryResponse:
        """Process a chat query with module routing.

        Args:
            user_id: User ID.
            department_id: Department for module routing.
            message: User's message.
            session_id: Optional existing session ID.

        Returns:
            ChatQueryResponse with answer and sources.
        """
        # Get or create session
        chat_session = await self._get_or_create_session(user_id, session_id)

        # Save user message
        await self.chat_repo.add_message(
            session_id=chat_session.id,
            role="user",
            content=message,
        )

        # Get module config
        module_config = module_registry.get(department_id)

        # Route to appropriate handler
        if module_config and module_config.module_type == ModuleType.COMMAND:
            result = await self._handle_command_query(
                message=message,
                department_id=department_id,
                config=module_config,  # type: ignore[arg-type]
                chat_session=chat_session,
            )
        else:
            # Default to RAG (backward compatible)
            result = await self._handle_rag_query(
                message=message,
                department_id=department_id,
                config=module_config,  # type: ignore[arg-type]
                chat_session=chat_session,
            )

        # Save assistant message
        assistant_message = await self.chat_repo.add_message(
            session_id=chat_session.id,
            role="assistant",
            content=result["answer"],
        )

        # Update session title from first message
        if chat_session.message_count <= 2:
            title = await self.llm.generate_title(message)
            await self.chat_repo.update_session_title(chat_session, title)

        return ChatQueryResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            session_id=chat_session.session_id,
            message_id=assistant_message.message_id,
            action_result=result.get("action_result"),
        )

    async def _handle_command_query(
        self,
        message: str,
        department_id: str,
        config: CommandModuleConfig,
        chat_session: ChatSession,
    ) -> dict[str, Any]:
        """Handle query for command-based module.

        Args:
            message: User's message.
            department_id: Department identifier.
            config: Command module configuration.
            chat_session: Current chat session.

        Returns:
            Dict with answer and optional action_result.
        """
        if not self.command_executor:
            logger.warning(f"No command executor for department {department_id}")
            return {"answer": "Модуль команд не настроен"}

        # Get command service for this department
        command_service = self.command_services.get(department_id)

        # Get chat history
        messages = await self.chat_repo.get_messages_by_session(
            session_id=chat_session.id,
            limit=10,
        )
        chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages[:-1]
        ]

        # Get context from service
        context = command_service.get_context() if command_service else {}

        # Process through command executor
        tool_calls, text_response = await self.command_executor.process_message(
            message=message,
            config=config,
            chat_history=chat_history,
            context=context,
        )

        # If no tool calls, return text response
        if not tool_calls:
            return {"answer": text_response or "Не удалось обработать запрос"}

        # Execute tool calls through module service
        if command_service and tool_calls:
            tool_call = tool_calls[0]  # Handle first tool call
            result: CommandResult = await command_service.execute_tool(tool_call)

            # Generate response
            response = await self.command_executor.generate_tool_response(
                original_message=message,
                tool_call=tool_call,
                tool_result=result,
                config=config,
            )

            return {
                "answer": response,
                "action_result": {
                    "type": tool_call.name,
                    "success": result.success,
                    "data": result.data,
                } if result.success else None,
            }

        return {"answer": "Обработчик команд не найден для этого отдела"}

    async def _handle_rag_query(
        self,
        message: str,
        department_id: str,  # noqa: ARG002 - reserved for logging
        config: RAGModuleConfig | None,
        chat_session: ChatSession,
    ) -> dict[str, Any]:
        """Handle query for RAG-based module.

        Args:
            message: User's message.
            department_id: Department identifier.
            config: RAG module configuration (optional).
            chat_session: Current chat session.

        Returns:
            Dict with answer and sources.
        """
        # Get RAG parameters from config or defaults
        rag_limit = config.rag_limit if config else 5
        score_threshold = config.score_threshold if config else 0.3

        # Generate embedding
        query_vector = await self.embedding.embed_text(message)

        # Search Qdrant
        if config and config.department_filter:
            # Use department filter if available
            search_results = await self.qdrant.search(
                query_vector=query_vector,
                department_id=config.department_filter,
                limit=rag_limit,
                score_threshold=score_threshold,
            )
        else:
            # Search all departments (backward compatible)
            search_results = await self.qdrant.search_all_departments(
                query_vector=query_vector,
                limit=rag_limit,
                score_threshold=score_threshold,
            )

        # Get chat history
        messages = await self.chat_repo.get_messages_by_session(
            session_id=chat_session.id,
            limit=10,
        )
        chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in messages[:-1]
        ]

        # Generate response with module-specific system prompt
        system_prompt = config.system_prompt if config else None
        answer = await self.llm.generate_response(
            question=message,
            context=search_results,
            chat_history=chat_history if chat_history else None,
            system_prompt=system_prompt,
        )

        # Build sources
        sources = [
            Source(
                id=str(i),
                title=result.source,
                relevance_score=result.score,
            )
            for i, result in enumerate(search_results, 1)
        ]

        return {"answer": answer, "sources": sources}

    async def _get_or_create_session(
        self,
        user_id: int,
        session_id: str | None,
    ) -> ChatSession:
        """Get existing session or create new one.

        Args:
            user_id: User ID.
            session_id: Optional existing session ID.

        Returns:
            Chat session.
        """
        if session_id:
            chat_session = await self.chat_repo.get_session_by_id(session_id)
            if chat_session:
                return chat_session

        return await self.chat_repo.create_session(user_id)

    async def get_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
    ) -> ChatSessionsResponse:
        """Get user's chat sessions.

        Args:
            user_id: User ID.
            limit: Max sessions to return.
            offset: Pagination offset.

        Returns:
            ChatSessionsResponse with sessions list.
        """
        sessions, total = await self.chat_repo.get_sessions_by_user(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

        return ChatSessionsResponse(
            sessions=[self._session_to_response(s) for s in sessions],
            total=total,
            limit=limit,
            offset=offset,
        )

    def _session_to_response(self, session: ChatSession) -> ChatSessionResponse:
        """Convert ChatSession model to response schema."""
        return ChatSessionResponse(
            id=session.session_id,
            title=session.title,
            created_at=session.created_at,
            updated_at=session.updated_at,
            message_count=session.message_count,
        )
