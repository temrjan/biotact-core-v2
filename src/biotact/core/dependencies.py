"""FastAPI dependencies for dependency injection."""

from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.core.config import Settings, get_settings
from biotact.core.database import get_session
from biotact.core.security import TokenError, decode_access_token
from biotact.models.user import User
from biotact.modules.dashboard.config import dashboard_config
from biotact.modules.dashboard.service import DashboardService
from biotact.repositories.chat_repo import ChatRepository
from biotact.repositories.dashboard_repo import DashboardRepository
from biotact.repositories.user_repo import UserRepository
from biotact.services.auth_service import AuthService
from biotact.services.chat_service import ChatService
from biotact.services.command_executor import CommandExecutor
from biotact.services.rag import EmbeddingService, LLMService, QdrantService

if TYPE_CHECKING:
    from biotact.modules.command.base import BaseCommandService

# Security scheme
security = HTTPBearer()


# Type aliases for cleaner signatures
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


# =============================================================================
# RAG Services (singleton pattern via lru_cache)
# =============================================================================


@lru_cache
def get_embedding_service() -> EmbeddingService:
    """Get cached EmbeddingService instance."""
    return EmbeddingService(get_settings())


@lru_cache
def get_qdrant_service() -> QdrantService:
    """Get cached QdrantService instance."""
    return QdrantService(get_settings())


@lru_cache
def get_llm_service() -> LLMService:
    """Get cached LLMService instance."""
    return LLMService(get_settings())


EmbeddingServiceDep = Annotated[EmbeddingService, Depends(get_embedding_service)]
QdrantServiceDep = Annotated[QdrantService, Depends(get_qdrant_service)]
LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]


# =============================================================================
# Repository dependencies
# =============================================================================


async def get_user_repo(session: SessionDep) -> UserRepository:
    """Get UserRepository instance."""
    return UserRepository(session)


async def get_chat_repo(session: SessionDep) -> ChatRepository:
    """Get ChatRepository instance."""
    return ChatRepository(session)


async def get_dashboard_repo(session: SessionDep) -> DashboardRepository:
    """Get DashboardRepository instance."""
    return DashboardRepository(session)


UserRepoDep = Annotated[UserRepository, Depends(get_user_repo)]
ChatRepoDep = Annotated[ChatRepository, Depends(get_chat_repo)]
DashboardRepoDep = Annotated[DashboardRepository, Depends(get_dashboard_repo)]


# =============================================================================
# Service dependencies
# =============================================================================


async def get_auth_service(user_repo: UserRepoDep) -> AuthService:
    """Get AuthService instance."""
    return AuthService(user_repo)


async def get_dashboard_service(
    dashboard_repo: DashboardRepoDep,
) -> DashboardService:
    """Get DashboardService instance."""
    return DashboardService(
        config=dashboard_config,
        repository=dashboard_repo,
    )


@lru_cache
def get_command_executor() -> CommandExecutor:
    """Get cached CommandExecutor instance."""
    return CommandExecutor(get_settings())


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
CommandExecutorDep = Annotated[CommandExecutor, Depends(get_command_executor)]


async def get_chat_service(
    chat_repo: ChatRepoDep,
    embedding_service: EmbeddingServiceDep,
    qdrant_service: QdrantServiceDep,
    llm_service: LLMServiceDep,
    command_executor: CommandExecutorDep,
    dashboard_service: DashboardServiceDep,
) -> ChatService:
    """Get ChatService instance with RAG and command dependencies."""
    # Register command services by department
    command_services: dict[str, BaseCommandService] = {
        "dashboard": dashboard_service,
    }

    return ChatService(
        chat_repo=chat_repo,
        embedding_service=embedding_service,
        qdrant_service=qdrant_service,
        llm_service=llm_service,
        command_executor=command_executor,
        command_services=command_services,
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]


# =============================================================================
# Authentication dependencies
# =============================================================================


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    auth_service: AuthServiceDep,
) -> User:
    """Get current authenticated user from JWT token.

    Raises:
        HTTPException: If token is invalid or user not found.
    """
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return await auth_service.get_current_user(user_id)
    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from e


CurrentUserDep = Annotated[User, Depends(get_current_user)]


# =============================================================================
# HR Authorization
# =============================================================================


def _parse_hr_allowlist(raw: str) -> frozenset[str]:
    """Parse CSV emails into a normalized frozenset (lowercased, trimmed)."""
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


async def require_hr_email(
    current_user: CurrentUserDep,
    settings: SettingsDep,
) -> User:
    """Require that current user's email is in HR_ALLOWED_EMAILS.

    Raises:
        HTTPException: 403 if user email is not in allowlist. Fail-closed:
            empty allowlist means nobody has HR access.
    """
    allowlist = _parse_hr_allowlist(settings.hr_allowed_emails)
    if current_user.email.lower() not in allowlist:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HR access required",
        )
    return current_user


RequireHREmailDep = Annotated[User, Depends(require_hr_email)]
