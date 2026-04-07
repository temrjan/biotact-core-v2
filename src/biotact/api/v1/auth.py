"""Authentication endpoints."""

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from biotact.core.dependencies import AuthServiceDep
from biotact.core.security import hash_password
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


# --- Temporary setup endpoints (remove after use) ---

class SetupRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""
    department_id: str = "hr"


@router.post("/setup", status_code=status.HTTP_200_OK)
async def setup_user(
    request: SetupRequest,
    auth_service: AuthServiceDep,
    x_setup_key: str = Header(...),
) -> dict[str, str]:
    """Create or reset password for a user. Requires X-Setup-Key header."""
    if x_setup_key != "biotact-hr-setup-2026":
        raise HTTPException(status_code=403, detail="Invalid setup key")

    from biotact.models.user import User

    db = auth_service.user_repo.session
    result = await db.execute(select(User).where(User.email == request.email))
    existing = result.scalar_one_or_none()

    if existing:
        existing.hashed_password = hash_password(request.password)
        if request.full_name:
            existing.full_name = request.full_name
        await db.flush()
        return {"status": "password_reset", "email": request.email, "id": str(existing.id)}

    user = await auth_service.register(
        email=request.email,
        password=request.password,
        full_name=request.full_name or request.email,
        department_id=request.department_id,
    )
    return {"status": "created", "email": user.email, "id": str(user.id)}
