"""SQLAlchemy models for CRM module."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from biotact.core.database import Base


class TelegramCustomer(Base):
    """Telegram customer profile for CRM.
    
    Stores customer information collected during bot interactions:
    - Basic info from Telegram (name, username)
    - Phone collected during orders
    - Health problems/tags (immunity, gut, stress, skin)
    - Family members with their health needs
    - Purchase history
    - AI notes for personalization
    """

    __tablename__ = "telegram_customers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        nullable=False,
        index=True,
    )
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    username: Mapped[str | None] = mapped_column(String(100))
    language_code: Mapped[str] = mapped_column(
        String(5),
        default="ru",
        server_default="ru",
    )
    phone: Mapped[str | None] = mapped_column(String(20))
    
    # Health problems/tags: ["immunity", "gut", "stress", "skin"]
    problems: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default="{}",
    )
    
    # Family members: [{"name": "Алия", "relation": "дочь", "age": 5, "problems": ["immunity"]}]
    family: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default="[]",
    )
    
    # Purchased products: ["IMMUNOCOMPLEX KIDS", "BIFOLAK ACTIVE"]
    purchased_products: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        default=list,
        server_default="{}",
    )
    
    # Free-form AI notes about the customer
    ai_notes: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TelegramCustomer(telegram_id={self.telegram_id}, name={self.first_name})>"
