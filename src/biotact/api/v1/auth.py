"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status

from biotact.core.dependencies import AuthServiceDep, CurrentUserDep
from biotact.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
)
from biotact.services.auth_service import AuthenticationError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    auth_service: AuthServiceDep,
) -> LoginResponse:
    """Authenticate user and return access token.

    - **email**: User's email address
    - **password**: User's password
    """
    try:
        return await auth_service.authenticate(
            email=request.email,
            password=request.password,
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        ) from e


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUserDep,
    auth_service: AuthServiceDep,
) -> None:
    """Change the current user's password.

    - **current_password**: Current password (verified before the change)
    - **new_password**: New password (min 8 chars, max 72 bytes)

    Wrong current password returns **400**, not 401 — the frontend
    treats 401 as an expired session and drops the auth token.
    """
    try:
        await auth_service.change_password(
            user=current_user,
            current_password=request.current_password,
            new_password=request.new_password,
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
