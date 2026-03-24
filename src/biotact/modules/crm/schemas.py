"""Pydantic schemas for CRM module."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Family Member Schema
# =============================================================================


class FamilyMember(BaseModel):
    """Family member information."""

    name: str = Field(..., min_length=1, max_length=100)
    relation: str = Field(..., min_length=1, max_length=50)
    age: int | None = Field(None, ge=0, le=120)
    problems: list[str] = Field(default_factory=list)


# =============================================================================
# Request Schemas
# =============================================================================


class CustomerCreate(BaseModel):
    """Schema for creating/updating a customer."""

    telegram_id: int = Field(..., description="Telegram user ID")
    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    username: str | None = Field(None, max_length=100)
    language_code: str = Field(default="ru", max_length=5)
    phone: str | None = Field(None, max_length=20)


class CustomerUpdate(BaseModel):
    """Schema for partial customer update."""

    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    phone: str | None = None
    ai_notes: str | None = None


class ProblemsUpdate(BaseModel):
    """Schema for updating customer problems."""

    problems: list[str] = Field(..., description="List of problem tags to add")


class FamilyUpdate(BaseModel):
    """Schema for updating family member."""

    member: FamilyMember = Field(..., description="Family member to add/update")


class PurchaseUpdate(BaseModel):
    """Schema for adding purchased product."""

    product: str = Field(..., min_length=1, max_length=100)


# =============================================================================
# Response Schemas
# =============================================================================


class CustomerResponse(BaseModel):
    """Customer response schema."""

    model_config = ConfigDict(from_attributes=True)

    telegram_id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    language_code: str
    phone: str | None
    problems: list[str]
    family: list[dict[str, Any]]
    purchased_products: list[str]
    ai_notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerBriefResponse(BaseModel):
    """Brief customer info for RAG context."""

    model_config = ConfigDict(from_attributes=True)

    telegram_id: int
    first_name: str | None
    phone: str | None
    problems: list[str]
    family: list[dict[str, Any]]
    purchased_products: list[str]
    ai_notes: str | None


# =============================================================================
# List & Stats Schemas
# =============================================================================


class CustomersListResponse(BaseModel):
    """Paginated list of customers."""

    items: list[CustomerResponse]
    total: int
    page: int
    size: int
    pages: int


class CustomersStatsResponse(BaseModel):
    """CRM statistics."""

    total_customers: int
    new_today: int
    with_phone: int
    with_purchases: int
    by_problem: dict[str, int]  # {"immunity": 10, "gut": 5, ...}
