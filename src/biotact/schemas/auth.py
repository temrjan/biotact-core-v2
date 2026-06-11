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


class ChangePasswordRequest(BaseModel):
    """Schema for changing own password."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password", mode="after")
    @classmethod
    def fit_bcrypt_limit(cls, value: str) -> str:
        """bcrypt hashes only the first 72 bytes — reject longer input
        instead of silently truncating it (audit S5).
        """
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return value


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
