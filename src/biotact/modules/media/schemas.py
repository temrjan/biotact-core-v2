"""Pydantic schemas for media module."""

from pydantic import BaseModel, Field

OPENAI_TTS_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")
TTS_MAX_CHARS = 4096

_VOICE_PATTERN = f"^({'|'.join(OPENAI_TTS_VOICES)})$"


class TranscribeResponse(BaseModel):
    """STT result."""

    text: str


class SynthesizeRequest(BaseModel):
    """TTS request."""

    text: str = Field(min_length=1, max_length=TTS_MAX_CHARS)
    voice: str = Field(default="nova", pattern=_VOICE_PATTERN)
