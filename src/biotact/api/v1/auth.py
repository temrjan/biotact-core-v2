"""Authentication endpoints."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

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


# --- Temporary registration endpoint (remove after setup) ---
class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    department_id: str = "hr"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    auth_service: AuthServiceDep,
    x_setup_key: str = Header(...),
) -> dict[str, str]:
    """One-time user registration. Requires X-Setup-Key header."""
    if x_setup_key != "biotact-hr-setup-2026":
        raise HTTPException(status_code=403, detail="Invalid setup key")
    try:
        user = await auth_service.register(
            email=request.email,
            password=request.password,
            full_name=request.full_name,
            department_id=request.department_id,
        )
        return {"status": "created", "email": user.email, "id": str(user.id)}
    except AuthenticationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
