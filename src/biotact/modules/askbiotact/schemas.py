"""AskBiotact Pydantic schemas for API and internal use."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """Incoming question from external bot integration."""

    user_id: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=4000)
    first_name: str | None = Field(
        None, max_length=100, description="User's first name from Telegram"
    )
    username: str | None = Field(
        None, max_length=100, description="User's @username from Telegram"
    )


class AskResponse(BaseModel):
    """Response from AskBiotact service."""

    answer: str
    user_id: str
    order_sent: bool = False


class ParsedOrder(BaseModel):
    """LLM-parsed order data."""

    name: str | None = None
    phone: str | None = None
    address: str | None = None
    products: list[OrderProduct] = Field(default_factory=list)
    raw_text: str = ""


class OrderProduct(BaseModel):
    """Single product in an order."""

    name: str
    qty: int = 1


class UserInfo(BaseModel):
    """User info for order formatting."""

    user_id: str
    first_name: str = ""
    username: str = "нет"
