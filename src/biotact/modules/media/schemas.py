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
    uploaded_by: int
    uploaded_by_name: str
    is_owner: bool
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
    original_filename: str
    uploaded_by: int
    uploaded_by_name: str
    is_owner: bool
    created_at: datetime
