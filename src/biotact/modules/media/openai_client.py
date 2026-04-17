"""OpenAI audio client: Whisper (STT) and TTS-1."""

from openai import AsyncOpenAI

from biotact.core.config import Settings

STT_LANGUAGE = "ru"
STT_MODEL = "whisper-1"
TTS_MODEL = "tts-1"


class AudioClient:
    """Thin wrapper over OpenAI audio endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def transcribe(
        self,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Transcribe audio to Russian text via Whisper.

        Args:
            filename: Original file name (used for MIME inference).
            content: Raw audio bytes.
            content_type: Audio MIME type (e.g. audio/mpeg).

        Returns:
            Transcribed text.
        """
        response = await self.client.audio.transcriptions.create(
            model=STT_MODEL,
            file=(filename, content, content_type),
            language=STT_LANGUAGE,
            response_format="text",
        )
        # response_format="text" returns a plain str
        return str(response).strip()

    async def synthesize(self, text: str, voice: str) -> bytes:
        """Synthesize speech via OpenAI TTS-1.

        Args:
            text: Source text (already validated and length-capped by schema).
            voice: OpenAI voice id (nova, alloy, echo, fable, onyx, shimmer).

        Returns:
            MP3 audio bytes.
        """
        response = await self.client.audio.speech.create(
            model=TTS_MODEL,
            voice=voice,
            input=text,
            response_format="mp3",
        )
        return response.content
