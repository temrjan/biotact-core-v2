"""HR Library models — document templates/samples."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from biotact.models.base import Base, TimestampMixin


class HRTemplate(TimestampMixin, Base):
    """Document template uploaded by HR user.

    Stores the original file + extracted text for LLM access.
    Categories: трудовой_договор, приказ, должностная_инструкция, etc.
    """

    __tablename__ = "hr_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)  # docx/pdf/txt
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_styles: Mapped[dict | None] = mapped_column(JSONB)
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HRTemplate(id={self.id}, name='{self.name}', category='{self.category}')>"
