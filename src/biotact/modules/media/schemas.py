"""Pydantic schemas for media module."""

from datetime import datetime

from pydantic import BaseModel, Field

OPENAI_TTS_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
TTS_MAX_CHARS = 4096

_VOICE_PATTERN = f"^({'|'.join(OPENAI_TTS_VOICES)})$"


class TranscribeResponse(BaseModel):
    """STT result with stored record reference."""

    transcription_id: str
    title: str
    text: str


class SynthesizeRequest(BaseModel):
    """TTS request."""

    text: str = Field(min_length=1, max_length=TTS_MAX_CHARS)
    voice: str = Field(default="nova", pattern=_VOICE_PATTERN)


class TranscriptionListItem(BaseModel):
    """Compact transcription entry for list view."""

    transcription_id: str
    title: str
    preview: str
    summary: str
    uploaded_by: int
    uploaded_by_name: str
    is_owner: bool
    is_indexed: bool
    created_at: datetime


class TranscriptionListResponse(BaseModel):
    """Paginated list of transcriptions."""

    items: list[TranscriptionListItem]
    total: int
    page: int
    page_size: int
    pages: int


class TranscriptionDetail(BaseModel):
    """Full transcription payload."""

    transcription_id: str
    title: str
    text: str
    summary: str
    keywords: list[str]
    original_filename: str
    uploaded_by: int
    uploaded_by_name: str
    is_owner: bool
    is_indexed: bool
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════
# Chat schemas
# ═══════════════════════════════════════════════════════════════════


class ChatMessage(BaseModel):
    """Single chat message in history."""

    role: str  # "user" | "assistant"
    content: str


class MediaChatRequest(BaseModel):
    """Chat request to unified media search."""

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] | None = None


class MediaChatSource(BaseModel):
    """One retrieved source cited in the answer."""

    source_type: str  # "media" | "files" | "biotact" | "dr_berg" | "nutrition"
    title: str
    snippet: str
    score: float
    ref_id: str | None = None  # transcription_id for media, else None


class MediaChatResponse(BaseModel):
    """Unified chat response with cited sources."""

    answer: str
    sources: list[MediaChatSource]
