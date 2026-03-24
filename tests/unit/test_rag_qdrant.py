"""Tests for QdrantService."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from biotact.services.rag.qdrant import QdrantService, SearchResult


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()
    settings.qdrant_host = "localhost"
    settings.qdrant_port = 6333
    settings.qdrant_api_key = None
    settings.qdrant_collection = "test_collection"
    return settings


@pytest.fixture
def qdrant_service(mock_settings: MagicMock) -> QdrantService:
    """Create QdrantService with mocked client."""
    with patch("biotact.services.rag.qdrant.AsyncQdrantClient"):
        service = QdrantService(mock_settings)
        service.client = MagicMock()
        return service


def create_mock_scored_point(
    content: str, source: str, score: float, department_id: str = "marketing"
) -> MagicMock:
    """Create a mock ScoredPoint."""
    point = MagicMock()
    point.score = score
    point.payload = {
        "content": content,
        "source": source,
        "department_id": department_id,
    }
    return point


class TestQdrantService:
    """Tests for QdrantService."""

    @pytest.mark.unit
    async def test_search_returns_results(self, qdrant_service: QdrantService) -> None:
        """search should return SearchResult list."""
        # Arrange
        mock_points = [
            create_mock_scored_point("Content 1", "doc1.pdf", 0.95),
            create_mock_scored_point("Content 2", "doc2.pdf", 0.85),
        ]
        mock_response = MagicMock()
        mock_response.points = mock_points
        qdrant_service.client.query_points = AsyncMock(return_value=mock_response)

        # Act
        results = await qdrant_service.search(
            query_vector=[0.1, 0.2, 0.3],
            department_id="marketing",
            limit=5,
        )

        # Assert
        assert len(results) == 2
        assert isinstance(results[0], SearchResult)
        assert results[0].content == "Content 1"
        assert results[0].source == "doc1.pdf"
        assert results[0].score == 0.95
        assert results[1].content == "Content 2"

    @pytest.mark.unit
    async def test_search_applies_department_filter(
        self, qdrant_service: QdrantService
    ) -> None:
        """search should filter by department_id."""
        # Arrange
        mock_response = MagicMock()
        mock_response.points = []
        qdrant_service.client.query_points = AsyncMock(return_value=mock_response)

        # Act
        await qdrant_service.search(
            query_vector=[0.1, 0.2],
            department_id="sales",
            limit=5,
        )

        # Assert
        call_kwargs = qdrant_service.client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["query_filter"] is not None
        # Check filter has department_id condition
        filter_obj = call_kwargs["query_filter"]
        assert len(filter_obj.must) == 1
        assert filter_obj.must[0].key == "department_id"

    @pytest.mark.unit
    async def test_search_all_departments_no_filter(
        self, qdrant_service: QdrantService
    ) -> None:
        """search_all_departments should not apply department filter."""
        # Arrange
        mock_response = MagicMock()
        mock_response.points = []
        qdrant_service.client.query_points = AsyncMock(return_value=mock_response)

        # Act
        await qdrant_service.search_all_departments(
            query_vector=[0.1, 0.2],
            limit=5,
        )

        # Assert
        call_kwargs = qdrant_service.client.query_points.call_args.kwargs
        assert (
            "query_filter" not in call_kwargs or call_kwargs.get("query_filter") is None
        )

    @pytest.mark.unit
    async def test_search_respects_limit(self, qdrant_service: QdrantService) -> None:
        """search should pass limit to Qdrant."""
        # Arrange
        mock_response = MagicMock()
        mock_response.points = []
        qdrant_service.client.query_points = AsyncMock(return_value=mock_response)

        # Act
        await qdrant_service.search(
            query_vector=[0.1],
            department_id="marketing",
            limit=10,
        )

        # Assert
        call_kwargs = qdrant_service.client.query_points.call_args.kwargs
        assert call_kwargs["limit"] == 10

    @pytest.mark.unit
    async def test_search_respects_score_threshold(
        self, qdrant_service: QdrantService
    ) -> None:
        """search should pass score_threshold to Qdrant."""
        # Arrange
        mock_response = MagicMock()
        mock_response.points = []
        qdrant_service.client.query_points = AsyncMock(return_value=mock_response)

        # Act
        await qdrant_service.search(
            query_vector=[0.1],
            department_id="marketing",
            score_threshold=0.8,
        )

        # Assert
        call_kwargs = qdrant_service.client.query_points.call_args.kwargs
        assert call_kwargs["score_threshold"] == 0.8

    @pytest.mark.unit
    async def test_health_check_returns_true_when_healthy(
        self, qdrant_service: QdrantService
    ) -> None:
        """health_check should return True when Qdrant is accessible."""
        qdrant_service.client.get_collections = AsyncMock(return_value=[])

        result = await qdrant_service.health_check()

        assert result is True

    @pytest.mark.unit
    async def test_health_check_returns_false_on_error(
        self, qdrant_service: QdrantService
    ) -> None:
        """health_check should return False when Qdrant is not accessible."""
        qdrant_service.client.get_collections = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await qdrant_service.health_check()

        assert result is False

    @pytest.mark.unit
    def test_point_to_result_extracts_metadata(
        self, qdrant_service: QdrantService
    ) -> None:
        """_point_to_result should extract metadata correctly."""
        # Arrange
        point = MagicMock()
        point.score = 0.9
        point.payload = {
            "content": "Test content",
            "source": "test.pdf",
            "page": 5,
            "chapter": "Introduction",
        }

        # Act
        result = qdrant_service._point_to_result(point)

        # Assert
        assert result.content == "Test content"
        assert result.source == "test.pdf"
        assert result.score == 0.9
        assert result.metadata["page"] == 5
        assert result.metadata["chapter"] == "Introduction"
        # content and source should not be in metadata
        assert "content" not in result.metadata
        assert "source" not in result.metadata

    @pytest.mark.unit
    def test_point_to_result_handles_empty_payload(
        self, qdrant_service: QdrantService
    ) -> None:
        """_point_to_result should handle empty payload."""
        point = MagicMock()
        point.score = 0.5
        point.payload = None

        result = qdrant_service._point_to_result(point)

        assert result.content == ""
        assert result.source == "unknown"
        assert result.metadata == {}
