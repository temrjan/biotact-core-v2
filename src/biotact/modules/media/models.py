"""Media module SQLAlchemy models."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biotact.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from biotact.models.user import User


def _generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


class MediaTranscription(TimestampMixin, Base):
    """Stored audio transcription result (Whisper output).

    Visible to all authenticated users. Only the author (uploaded_by)
    may delete.
    """

    __tablename__ = "media_transcriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcription_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        default=_generate_uuid,
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[uploaded_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<MediaTranscription(id={self.id}, title='{self.title[:30]}')>"
