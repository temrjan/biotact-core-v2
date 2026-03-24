"""Tests for LLMService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.services.rag.llm import LLMService
from biotact.services.rag.qdrant import SearchResult


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.openai_api_key = "test-api-key"
    settings.llm_model = "gpt-4o"
    settings.llm_provider = "openai"
    return settings


@pytest.fixture
def llm_service(mock_settings: MagicMock) -> LLMService:
    """Create LLMService with mocked OpenAI client."""
    with patch("biotact.services.rag.llm.AsyncOpenAI"):
        service = LLMService(mock_settings)
        service.client = MagicMock()
        return service


def create_search_result(
    content: str, source: str, score: float = 0.9
) -> SearchResult:
    """Create a SearchResult for testing."""
    return SearchResult(
        content=content,
        source=source,
        score=score,
        metadata={},
    )


class TestLLMService:
    """Tests for LLMService."""

    @pytest.mark.unit
    async def test_generate_response_returns_text(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should return response text."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Test answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        context = [create_search_result("Context content", "doc.pdf")]

        # Act
        result = await llm_service.generate_response(
            question="What is the answer?",
            context=context,
        )

        # Assert
        assert result == "Test answer"

    @pytest.mark.unit
    async def test_generate_response_uses_correct_model(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should use model from settings."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        await llm_service.generate_response(
            question="Question?",
            context=[],
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"

    @pytest.mark.unit
    async def test_generate_response_includes_system_prompt(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should include system prompt."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        await llm_service.generate_response(
            question="Question?",
            context=[],
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert "Biotact" in messages[0]["content"]

    @pytest.mark.unit
    async def test_generate_response_includes_context(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should include context in user message."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        context = [
            create_search_result("First doc content", "first.pdf"),
            create_search_result("Second doc content", "second.pdf"),
        ]

        # Act
        await llm_service.generate_response(
            question="What about docs?",
            context=context,
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        user_message = messages[-1]["content"]
        assert "First doc content" in user_message
        assert "Second doc content" in user_message
        assert "[Источник: first.pdf]" in user_message

    @pytest.mark.unit
    async def test_generate_response_includes_chat_history(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should include chat history."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        chat_history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]

        # Act
        await llm_service.generate_response(
            question="New question?",
            context=[],
            chat_history=chat_history,
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Should have: system, history (2), user
        assert len(messages) == 4
        assert messages[1]["content"] == "Previous question"
        assert messages[2]["content"] == "Previous answer"

    @pytest.mark.unit
    async def test_generate_response_limits_chat_history(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should limit chat history to last 10 messages."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Create 15 history messages
        chat_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(15)
        ]

        # Act
        await llm_service.generate_response(
            question="Question?",
            context=[],
            chat_history=chat_history,
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        # Should have: system + 10 history + user = 12
        assert len(messages) == 12

    @pytest.mark.unit
    async def test_generate_response_respects_max_tokens(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should pass max_tokens."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        await llm_service.generate_response(
            question="Question?",
            context=[],
            max_tokens=500,
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 500

    @pytest.mark.unit
    async def test_generate_response_respects_temperature(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should pass temperature."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Answer"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        await llm_service.generate_response(
            question="Question?",
            context=[],
            temperature=0.7,
        )

        # Assert
        call_kwargs = llm_service.client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7

    @pytest.mark.unit
    async def test_generate_response_handles_empty_content(
        self, llm_service: LLMService
    ) -> None:
        """generate_response should handle None content."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content=None))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        result = await llm_service.generate_response(
            question="Question?",
            context=[],
        )

        # Assert
        assert result == ""

    @pytest.mark.unit
    async def test_generate_title_returns_short_title(
        self, llm_service: LLMService
    ) -> None:
        """generate_title should return a short title."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Price inquiry"))]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        result = await llm_service.generate_title("What is the price of product X?")

        # Assert
        assert result == "Price inquiry"

    @pytest.mark.unit
    async def test_generate_title_strips_whitespace(
        self, llm_service: LLMService
    ) -> None:
        """generate_title should strip whitespace."""
        # Arrange
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="  Title with spaces  "))
        ]
        llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        result = await llm_service.generate_title("Some message")

        # Assert
        assert result == "Title with spaces"

    @pytest.mark.unit
    def test_build_context_formats_results(self, llm_service: LLMService) -> None:
        """_build_context should format search results."""
        context = [
            create_search_result("Content A", "doc_a.pdf"),
            create_search_result("Content B", "doc_b.pdf"),
        ]

        result = llm_service._build_context(context)

        assert "1. Content A" in result
        assert "[Источник: doc_a.pdf]" in result
        assert "2. Content B" in result
        assert "[Источник: doc_b.pdf]" in result

    @pytest.mark.unit
    def test_build_context_empty_returns_message(
        self, llm_service: LLMService
    ) -> None:
        """_build_context with empty list should return message."""
        result = llm_service._build_context([])
        assert "не найден" in result.lower()
