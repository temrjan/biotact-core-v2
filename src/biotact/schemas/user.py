"""User schemas."""

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserBase(BaseModel):
    """Base user schema."""

    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    department_id: str = Field(min_length=1, max_length=50)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Lowercase email — DB lookups compare exactly, and EmailStr
        preserves the local-part case, so unnormalized input breaks login.
        """
        return value.lower()


class UserCreate(UserBase):
    """Schema for creating a user."""

    password: str = Field(min_length=8, max_length=128)


class UserResponse(UserBase):
    """Schema for user response."""

    id: int
    is_active: bool

    model_config = {"from_attributes": True}


class UserInDB(UserResponse):
    """Schema for user with hashed password (internal use)."""

    hashed_password: str
