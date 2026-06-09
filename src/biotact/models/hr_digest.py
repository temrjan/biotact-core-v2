"""SQLAlchemy models for HR Digest."""

from sqlalchemy import JSON, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from biotact.models.base import Base


class HRDigest(Base):
    """HR News Digest table."""

    # Legacy table name kept for migration stability.
    # Module moved to news_digest/ in PR-5.
    __tablename__ = "hr_digests"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    content_markdown = Column(Text, nullable=False)
    content_json = Column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    news_count = Column(Integer, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    generated_by = Column(String(50), default="auto", nullable=False)

    # Relationship
    news_items = relationship(
        "HRNewsItem", back_populates="digest", cascade="all, delete-orphan"
    )


class HRNewsItem(Base):
    """Individual news item in digest."""

    __tablename__ = "hr_news_items"

    id = Column(Integer, primary_key=True, index=True)
    digest_id = Column(
        Integer, ForeignKey("hr_digests.id", ondelete="CASCADE"), nullable=False
    )
    source = Column(String(100), nullable=False, index=True)
    title = Column(Text)
    content = Column(Text, nullable=False)
    url = Column(Text)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    digest = relationship("HRDigest", back_populates="news_items")
