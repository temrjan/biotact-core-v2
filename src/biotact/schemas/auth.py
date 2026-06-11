"""Authentication schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator

from biotact.schemas.user import UserResponse


class LoginRequest(BaseModel):
    """Schema for login request."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Lowercase email — stored emails are lowercase and the user
        lookup compares exactly (see UserBase.normalize_email).
        """
        return value.lower()


class LoginResponse(BaseModel):
    """Schema for login response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class TokenPayload(BaseModel):
    """Schema for JWT token payload."""

    sub: str  # user_id
    department_id: str
    exp: int | None = None
