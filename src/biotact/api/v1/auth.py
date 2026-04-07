"""Authentication endpoints."""

from fastapi import APIRouter, HTTPException, status

from biotact.core.dependencies import AuthServiceDep
from biotact.schemas.auth import LoginRequest, LoginResponse
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
