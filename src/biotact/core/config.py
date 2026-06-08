"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_name: str = "biotact"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_prefix: str = "/api/v1"

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT signing",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080  # 7 days (internal dashboard, 2 users)

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "biotact"
    postgres_password: str = "biotact_dev_password"
    postgres_db: str = "biotact"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Construct async database URL."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url_sync(self) -> str:
        """Construct sync database URL (for Alembic)."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg2",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )

    # -------------------------------------------------------------------------
    # Qdrant
    # -------------------------------------------------------------------------
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "biotact_knowledge"
    qdrant_api_key: str | None = None

    # -------------------------------------------------------------------------
    # OpenAI
    # -------------------------------------------------------------------------
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"

    # -------------------------------------------------------------------------
    # Voice Service (STT/TTS)
    # -------------------------------------------------------------------------
    voice_enabled: bool = False
    voice_service_url: str = "https://voice.biotact.uz"
    voice_api_key: str = ""

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # -------------------------------------------------------------------------
    # HR Digest Bot
    # -------------------------------------------------------------------------
    hr_digest_bot_token: SecretStr = SecretStr("")
    hr_digest_chat_id: str = ""
    allowed_users: str = ""
    digest_retention_days: int = 7

    # -------------------------------------------------------------------------
    # HR Module — Access Control
    # -------------------------------------------------------------------------
    hr_allowed_emails: str = Field(
        default="",
        description=(
            "Comma-separated list of emails allowed to access HR endpoints "
            "(templates library, chat, document generation). "
            "Empty = no one has HR access (fail-closed)."
        ),
    )

    # -------------------------------------------------------------------------
    # Firecrawl (Web Scraper)
    # -------------------------------------------------------------------------
    firecrawl_api_key: str = ""

    # -------------------------------------------------------------------------
    # Telegram Scraper (Telethon)
    # -------------------------------------------------------------------------
    telegram_api_id: int = 0
    telegram_api_hash: SecretStr = SecretStr("")
    telegram_phone: str = ""

    # -------------------------------------------------------------------------
    # Anthropic
    # -------------------------------------------------------------------------
    anthropic_api_key: str = ""

    # -------------------------------------------------------------------------
    # AskBiotact Public API
    # -------------------------------------------------------------------------
    askbiotact_api_key: str = ""

    # -------------------------------------------------------------------------
    # LLM Provider
    # -------------------------------------------------------------------------
    llm_provider: Literal["openai", "anthropic"] = "openai"
    llm_model: str = "gpt-4o"

    # Rate Limiting
    # -------------------------------------------------------------------------
    rate_limit_per_minute: int = 60

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
