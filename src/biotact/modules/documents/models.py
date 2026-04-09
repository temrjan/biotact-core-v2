"""File storage models — folders and files for shared document platform."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from biotact.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from biotact.models.user import User


def _generate_uuid() -> str:
    """Generate a UUID4 string."""
    return str(uuid.uuid4())


class Folder(TimestampMixin, Base):
    """Folder for organizing documents.

    Supports nested hierarchy via parent_id (NULL = root).
    All folders are visible to all authenticated users.
    Only the creator (uploaded_by) can delete.
    """

    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint(
            "parent_id",
            "name",
            name="uq_folders_parent_name",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    folder_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        default=_generate_uuid,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    parent: Mapped["Folder | None"] = relationship(
        "Folder",
        remote_side="Folder.id",
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list["Folder"]] = relationship(
        "Folder",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    files: Mapped[list["File"]] = relationship(
        "File",
        back_populates="folder",
        cascade="all, delete-orphan",
    )
    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[uploaded_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Folder(id={self.id}, name='{self.name}')>"


class File(TimestampMixin, Base):
    """Uploaded file with optional Qdrant indexing.

    All files are visible to all authenticated users.
    Only the creator (uploaded_by) can delete.
    """

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        default=_generate_uuid,
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("folders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # RAG indexing state
    is_indexed: Mapped[bool] = mapped_column(default=False, nullable=False)
    chunk_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Sharing
    share_token: Mapped[str | None] = mapped_column(
        String(64),
        unique=True,
        nullable=True,
        index=True,
    )

    # Relationships
    folder: Mapped["Folder | None"] = relationship(
        "Folder",
        back_populates="files",
        lazy="selectin",
    )
    creator: Mapped["User"] = relationship(
        "User", foreign_keys=[uploaded_by], lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<File(id={self.id}, name='{self.name}')>"
