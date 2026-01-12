"""Pydantic schemas for HR Digest."""

from datetime import datetime

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """Raw news item from scraper."""

    source: str = Field(..., description="Источник новости (lex.uz, @bhblaw, etc)")
    title: str | None = Field(None, description="Заголовок новости")
    content: str = Field(..., description="Полный текст новости")
    url: str | None = Field(None, description="Ссылка на новость")
    published_at: datetime | None = Field(None, description="Дата публикации")


class DigestItem(BaseModel):
    """Processed digest item with summary."""

    source: str = Field(..., description="Источник")
    text: str = Field(..., description="Краткое резюме (1-2 предложения)")
    url: str | None = Field(None, description="Ссылка на источник")


class DigestSection(BaseModel):
    """Section of digest (category with items)."""

    category: str = Field(..., description="Название категории")
    emoji: str = Field(..., description="Эмодзи категории")
    items: list[DigestItem] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Check if section has no items."""
        return len(self.items) == 0

    def to_markdown(self) -> str:
        """Convert section to Telegram-compatible markdown."""
        if self.is_empty:
            return ""

        lines = [f"\n*{self.category}*\n"]

        for item in self.items:
            lines.append(f"*{item.source}*")
            lines.append(item.text)
            if item.url:
                lines.append(f"🔗 {item.url}")
            lines.append("")

        return "\n".join(lines)


class Digest(BaseModel):
    """Complete HR Digest."""

    date: datetime = Field(default_factory=datetime.now)
    sections: list[DigestSection] = Field(default_factory=list)

    @property
    def news_count(self) -> int:
        """Total number of news items."""
        return sum(len(section.items) for section in self.sections)

    def to_markdown(self) -> str:
        """Convert digest to Telegram-compatible markdown."""
        from datetime import datetime

        today = datetime.now()
        header = f"""*📰 HR Дайджест*
_{today.strftime("%d.%m.%Y")} — Новости за последние 24 часа_
"""

        sections_md = "\n".join(
            section.to_markdown() for section in self.sections if not section.is_empty
        )

        footer = f"\n\n_Всего новостей: {self.news_count}_"

        return header + sections_md + footer


class DigestCreate(BaseModel):
    """Schema for creating a new digest."""

    date: datetime = Field(default_factory=datetime.now)
    content_markdown: str
    content_json: dict
    news_count: int
    generated_by: str = Field(default="auto", description="auto | manual")


class DigestResponse(BaseModel):
    """Schema for digest API response."""

    id: int
    date: datetime
    content_markdown: str
    news_count: int
    generated_by: str
    created_at: datetime

    class Config:
        from_attributes = True
