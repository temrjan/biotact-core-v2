"""HR Library models — document templates and generated documents."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from biotact.models.base import Base, TimestampMixin


class HRDocument(TimestampMixin, Base):
    """Generated document — rendered from a template with employee data.

    Tracks every document created via chat or render API.
    Files stored in data/hr_rendered/{file_id}.docx.
    """

    __tablename__ = "hr_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
        index=True,
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("hr_templates.id", ondelete="SET NULL"),
    )
    template_name: Mapped[str] = mapped_column(String(300), nullable=False)
    employee_name: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HRDocument(id={self.id}, employee='{self.employee_name}')>"


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
    template_fields: Mapped[list[str] | None] = mapped_column(
        JSONB, default=list, doc="List of {{ PLACEHOLDER }} names found in DOCX"
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<HRTemplate(id={self.id}, name='{self.name}', category='{self.category}')>"
