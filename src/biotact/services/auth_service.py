"""Authentication service."""

from biotact.core.config import get_settings
from biotact.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from biotact.models.user import User
from biotact.repositories.user_repo import UserRepository
from biotact.schemas.auth import LoginResponse
from biotact.schemas.user import UserResponse


class AuthenticationError(Exception):
    """Raised when authentication fails."""

    pass


class AuthService:
    """Service for authentication operations."""

    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo
        self.settings = get_settings()

    async def authenticate(self, email: str, password: str) -> LoginResponse:
        """Authenticate user and return tokens.

        Args:
            email: User email.
            password: Plain text password.

        Returns:
            LoginResponse with access token and user info.

        Raises:
            AuthenticationError: If credentials are invalid.
        """
        user = await self.user_repo.get_by_email(email)

        if not user:
            raise AuthenticationError("Invalid email or password")

        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("User account is disabled")

        token = create_access_token(
            data={
                "sub": str(user.id),
                "department_id": user.department_id,
            }
        )

        return LoginResponse(
            access_token=token,
            token_type="bearer",
            expires_in=self.settings.jwt_expire_minutes * 60,
            user=UserResponse.model_validate(user),
        )

    async def register(
        self,
        email: str,
        password: str,
        full_name: str,
        department_id: str,
    ) -> User:
        """Register a new user.

        Args:
            email: User email.
            password: Plain text password.
            full_name: User's full name.
            department_id: Department identifier.

        Returns:
            Created User.

        Raises:
            AuthenticationError: If email already exists.
        """
        existing = await self.user_repo.get_by_email(email)
        if existing:
            raise AuthenticationError("Email already registered")

        hashed = hash_password(password)
        return await self.user_repo.create(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            department_id=department_id,
        )

    async def get_current_user(self, user_id: int) -> User:
        """Get current user by ID.

        Args:
            user_id: User ID from token.

        Returns:
            User instance.

        Raises:
            AuthenticationError: If user not found or inactive.
        """
        user = await self.user_repo.get_by_id(user_id)

        if not user:
            raise AuthenticationError("User not found")

        if not user.is_active:
            raise AuthenticationError("User account is disabled")

        return user
