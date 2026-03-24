"""Tests for EmbeddingService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.services.rag.embedding import EmbeddingService


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.openai_api_key = "test-api-key"
    settings.openai_embedding_model = "text-embedding-3-large"
    return settings


@pytest.fixture
def embedding_service(mock_settings: MagicMock) -> EmbeddingService:
    """Create EmbeddingService with mocked OpenAI client."""
    with patch("biotact.services.rag.embedding.AsyncOpenAI"):
        service = EmbeddingService(mock_settings)
        service.client = MagicMock()
        return service


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    @pytest.mark.unit
    async def test_embed_text_returns_vector(
        self, embedding_service: EmbeddingService
    ) -> None:
        """embed_text should return a list of floats."""
        # Arrange
        mock_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=mock_embedding)]
        embedding_service.client.embeddings.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        result = await embedding_service.embed_text("test query")

        # Assert
        assert result == mock_embedding
        embedding_service.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-large",
            input="test query",
        )

    @pytest.mark.unit
    async def test_embed_texts_returns_list_of_vectors(
        self, embedding_service: EmbeddingService
    ) -> None:
        """embed_texts should return a list of embeddings."""
        # Arrange
        mock_embeddings = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=emb) for emb in mock_embeddings]
        embedding_service.client.embeddings.create = AsyncMock(
            return_value=mock_response
        )

        # Act
        result = await embedding_service.embed_texts(["text1", "text2", "text3"])

        # Assert
        assert result == mock_embeddings
        embedding_service.client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-large",
            input=["text1", "text2", "text3"],
        )

    @pytest.mark.unit
    async def test_embed_texts_empty_list_returns_empty(
        self, embedding_service: EmbeddingService
    ) -> None:
        """embed_texts with empty list should return empty list."""
        result = await embedding_service.embed_texts([])
        assert result == []

    @pytest.mark.unit
    def test_service_uses_correct_model(self, mock_settings: MagicMock) -> None:
        """Service should use model from settings."""
        with patch("biotact.services.rag.embedding.AsyncOpenAI"):
            service = EmbeddingService(mock_settings)
            assert service.model == "text-embedding-3-large"

    @pytest.mark.unit
    def test_service_has_correct_dimensions(self, mock_settings: MagicMock) -> None:
        """Service should have 3072 dimensions for text-embedding-3-large."""
        with patch("biotact.services.rag.embedding.AsyncOpenAI"):
            service = EmbeddingService(mock_settings)
            assert service.dimensions == 3072
