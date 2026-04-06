"""Tests for configuration module."""

import pytest

from biotact.core.config import Settings, get_settings


@pytest.mark.unit
class TestSettings:
    """Tests for Settings class."""

    def test_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings should have sensible defaults when env vars are not set."""
        # Clear relevant env vars to test defaults
        monkeypatch.delenv("DEBUG", raising=False)
        monkeypatch.delenv("APP_ENV", raising=False)

        # Disable .env file reading for this test
        settings = Settings(_env_file=None)

        assert settings.app_name == "biotact"
        assert settings.app_env == "development"
        assert settings.debug is False
        assert settings.api_port == 8000

    def test_database_url_construction(self) -> None:
        """Database URL should be constructed from components."""
        settings = Settings(
            postgres_user="testuser",
            postgres_password="testpass",
            postgres_host="testhost",
            postgres_port=5433,
            postgres_db="testdb",
        )

        assert "postgresql+asyncpg://" in settings.database_url
        assert "testuser" in settings.database_url
        assert "testhost" in settings.database_url
        assert "5433" in settings.database_url
        assert "testdb" in settings.database_url

    def test_database_url_sync_uses_psycopg2(self) -> None:
        """Sync database URL should use psycopg2 driver."""
        settings = Settings()

        assert "postgresql+psycopg2://" in settings.database_url_sync

    def test_is_development(self) -> None:
        """is_development should return True for development env."""
        settings = Settings(app_env="development")
        assert settings.is_development is True
        assert settings.is_production is False

    def test_is_production(self) -> None:
        """is_production should return True for production env."""
        settings = Settings(app_env="production")
        assert settings.is_production is True
        assert settings.is_development is False

    def test_cors_origins_default(self) -> None:
        """CORS origins should have default localhost values."""
        settings = Settings()

        assert "http://localhost:3000" in settings.cors_origins
        assert "http://localhost:8000" in settings.cors_origins

    def test_jwt_defaults(self) -> None:
        """JWT settings should have defaults."""
        settings = Settings()

        assert settings.jwt_algorithm == "HS256"
        assert settings.jwt_expire_minutes == 10080  # 7 days


@pytest.mark.unit
class TestGetSettings:
    """Tests for get_settings function."""

    def test_returns_settings_instance(self) -> None:
        """get_settings should return a Settings instance."""
        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_is_cached(self) -> None:
        """get_settings should return the same cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
