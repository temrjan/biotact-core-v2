"""Tests for ChatService with RAG integration."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from biotact.modules import module_registry
from biotact.modules.callcenter.config import callcenter_config
from biotact.modules.marketing.config import marketing_config
from biotact.services.chat_service import ChatService
from biotact.services.rag.qdrant import SearchResult

# Register modules for tests if not already registered
if "callcenter" not in module_registry:
    module_registry.register(callcenter_config)
if "marketing" not in module_registry:
    module_registry.register(marketing_config)


@pytest.fixture
def mock_chat_repo() -> MagicMock:
    """Create mock ChatRepository."""
    repo = MagicMock()

    # Mock session
    mock_session = MagicMock()
    mock_session.id = 1
    mock_session.session_id = "sess_abc123"
    mock_session.title = "New Chat"
    mock_session.message_count = 0

    repo.get_session_by_id = AsyncMock(return_value=mock_session)
    repo.create_session = AsyncMock(return_value=mock_session)
    repo.update_session_title = AsyncMock(return_value=mock_session)
    repo.get_messages_by_session = AsyncMock(return_value=[])

    # Mock message
    mock_message = MagicMock()
    mock_message.message_id = "msg_xyz789"
    mock_message.role = "assistant"
    mock_message.content = "Test answer"
    repo.add_message = AsyncMock(return_value=mock_message)

    return repo


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock EmbeddingService."""
    service = MagicMock()
    service.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return service


@pytest.fixture
def mock_qdrant_service() -> MagicMock:
    """Create mock QdrantService."""
    service = MagicMock()
    search_results = [
        SearchResult(
            content="Relevant content",
            source="doc.pdf",
            score=0.95,
            metadata={"page": 1},
        )
    ]
    service.search = AsyncMock(return_value=search_results)
    service.search_all_departments = AsyncMock(return_value=search_results)
    return service


@pytest.fixture
def mock_llm_service() -> MagicMock:
    """Create mock LLMService."""
    service = MagicMock()
    service.generate_response = AsyncMock(return_value="Generated answer")
    service.generate_title = AsyncMock(return_value="Chat Title")
    return service


@pytest.fixture
def chat_service(
    mock_chat_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_qdrant_service: MagicMock,
    mock_llm_service: MagicMock,
) -> ChatService:
    """Create ChatService with all mocked dependencies."""
    return ChatService(
        chat_repo=mock_chat_repo,
        embedding_service=mock_embedding_service,
        qdrant_service=mock_qdrant_service,
        llm_service=mock_llm_service,
    )


class TestChatServiceQuery:
    """Tests for ChatService.query method."""

    @pytest.mark.unit
    async def test_query_creates_session_when_none_provided(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """query should create new session when session_id is None."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="Hello",
            session_id=None,
        )

        mock_chat_repo.create_session.assert_called_once_with(1)

    @pytest.mark.unit
    async def test_query_uses_existing_session(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """query should use existing session when session_id provided."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="Hello",
            session_id="sess_existing",
        )

        mock_chat_repo.get_session_by_id.assert_called_once_with("sess_existing")

    @pytest.mark.unit
    async def test_query_saves_user_message(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """query should save user message to database."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="Test question",
        )

        # Check add_message was called with user message
        calls = mock_chat_repo.add_message.call_args_list
        user_call = calls[0]
        assert user_call.kwargs["role"] == "user"
        assert user_call.kwargs["content"] == "Test question"

    @pytest.mark.unit
    async def test_query_generates_embedding(
        self,
        chat_service: ChatService,
        mock_embedding_service: MagicMock,
    ) -> None:
        """query should generate embedding for the question."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="What is X?",
        )

        mock_embedding_service.embed_text.assert_called_once_with("What is X?")

    @pytest.mark.unit
    async def test_query_searches_qdrant_with_department(
        self,
        chat_service: ChatService,
        mock_qdrant_service: MagicMock,
    ) -> None:
        """query should search Qdrant with department filter for registered modules."""
        # Use 'callcenter' which has a registered module with department_filter
        await chat_service.query(
            user_id=1,
            department_id="callcenter",
            message="Question?",
        )

        mock_qdrant_service.search.assert_called_once()
        call_kwargs = mock_qdrant_service.search.call_args.kwargs
        assert call_kwargs["department_id"] == "callcenter"

    @pytest.mark.unit
    async def test_query_searches_all_departments_for_admin(
        self,
        chat_service: ChatService,
        mock_qdrant_service: MagicMock,
    ) -> None:
        """query should search all departments for admin users."""
        await chat_service.query(
            user_id=1,
            department_id="admin",
            message="Question?",
        )

        mock_qdrant_service.search_all_departments.assert_called_once()
        mock_qdrant_service.search.assert_not_called()

    @pytest.mark.unit
    async def test_query_calls_llm_with_context(
        self,
        chat_service: ChatService,
        mock_llm_service: MagicMock,
    ) -> None:
        """query should call LLM with question and context."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="What is X?",
        )

        mock_llm_service.generate_response.assert_called_once()
        call_kwargs = mock_llm_service.generate_response.call_args.kwargs
        assert call_kwargs["question"] == "What is X?"
        assert len(call_kwargs["context"]) > 0

    @pytest.mark.unit
    async def test_query_saves_assistant_message(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """query should save assistant response to database."""
        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="Question?",
        )

        # Second add_message call should be assistant
        calls = mock_chat_repo.add_message.call_args_list
        assert len(calls) == 2
        assistant_call = calls[1]
        assert assistant_call.kwargs["role"] == "assistant"
        assert assistant_call.kwargs["content"] == "Generated answer"

    @pytest.mark.unit
    async def test_query_returns_response(self, chat_service: ChatService) -> None:
        """query should return ChatQueryResponse."""
        result = await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="Question?",
        )

        assert result.answer == "Generated answer"
        assert result.session_id == "sess_abc123"
        assert result.message_id == "msg_xyz789"
        assert len(result.sources) == 1
        assert result.sources[0].title == "doc.pdf"

    @pytest.mark.unit
    async def test_query_generates_title_for_new_session(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
        mock_llm_service: MagicMock,
    ) -> None:
        """query should generate title for new session."""
        # Session has message_count <= 2 (new session)
        mock_session = mock_chat_repo.create_session.return_value
        mock_session.message_count = 1

        await chat_service.query(
            user_id=1,
            department_id="marketing",
            message="First message",
        )

        mock_llm_service.generate_title.assert_called_once_with("First message")
        mock_chat_repo.update_session_title.assert_called_once()


class TestChatServiceGetSessions:
    """Tests for ChatService.get_sessions method."""

    @pytest.mark.unit
    async def test_get_sessions_returns_sessions(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """get_sessions should return user sessions."""
        # Arrange
        mock_session = MagicMock()
        mock_session.session_id = "sess_123"
        mock_session.title = "Test Session"
        mock_session.created_at = datetime.now(UTC)
        mock_session.updated_at = datetime.now(UTC)
        mock_session.message_count = 5

        mock_chat_repo.get_sessions_by_user = AsyncMock(
            return_value=([mock_session], 1)
        )

        # Act
        result = await chat_service.get_sessions(user_id=1)

        # Assert
        assert result.total == 1
        assert len(result.sessions) == 1
        assert result.sessions[0].id == "sess_123"
        assert result.sessions[0].title == "Test Session"

    @pytest.mark.unit
    async def test_get_sessions_respects_pagination(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """get_sessions should pass pagination params."""
        mock_chat_repo.get_sessions_by_user = AsyncMock(return_value=([], 0))

        await chat_service.get_sessions(
            user_id=1,
            limit=10,
            offset=20,
        )

        mock_chat_repo.get_sessions_by_user.assert_called_once_with(
            user_id=1,
            limit=10,
            offset=20,
        )

    @pytest.mark.unit
    async def test_get_sessions_returns_pagination_info(
        self,
        chat_service: ChatService,
        mock_chat_repo: MagicMock,
    ) -> None:
        """get_sessions should include pagination in response."""
        mock_chat_repo.get_sessions_by_user = AsyncMock(return_value=([], 50))

        result = await chat_service.get_sessions(
            user_id=1,
            limit=10,
            offset=20,
        )

        assert result.total == 50
        assert result.limit == 10
        assert result.offset == 20
