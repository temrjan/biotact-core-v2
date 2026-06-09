"""SQLAlchemy models."""

from biotact.models.base import Base, TimestampMixin
from biotact.models.chat import ChatMessage, ChatSession
from biotact.models.dashboard import FinancialTransaction
from biotact.models.hr_digest import HRDigest, HRNewsItem
from biotact.models.user import User
from biotact.modules.documents.models import File, Folder
from biotact.modules.hr.events.models import HREvent
from biotact.modules.hr.gifts.models import (
    GiftBudgetPlan,
    GiftRequest,
    GiftStatusHistory,
)
from biotact.modules.hr.library.models import HRTemplate

__all__ = [
    "Base",
    "ChatMessage",
    "ChatSession",
    "File",
    "FinancialTransaction",
    "Folder",
    "GiftBudgetPlan",
    "GiftRequest",
    "GiftStatusHistory",
    "HRDigest",
    "HREvent",
    "HRNewsItem",
    "HRTemplate",
    "TimestampMixin",
    "User",
]
