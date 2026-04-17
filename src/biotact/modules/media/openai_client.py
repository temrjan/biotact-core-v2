"""OpenAI audio client: Whisper (STT) and TTS-1."""

import asyncio
import logging

from openai import AsyncOpenAI

from biotact.core.config import Settings
from biotact.modules.media.audio_split import split_audio

logger = logging.getLogger(__name__)

STT_LANGUAGE = "ru"
STT_MODEL = "whisper-1"
TTS_MODEL = "tts-1"
STT_DIRECT_MAX_BYTES = 20_000_000  # OpenAI limit is 25 MB, keep a safety margin
STT_PARALLEL_LIMIT = 5


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

    async def transcribe_long(
        self,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Transcribe arbitrarily long audio, splitting into chunks if needed.

        Files up to ``STT_DIRECT_MAX_BYTES`` go straight to Whisper. Larger
        files are re-encoded to mp3 64k mono and split into 10-minute chunks
        that are transcribed in parallel (bounded by ``STT_PARALLEL_LIMIT``)
        and joined with blank-line separators.
        """
        if len(content) <= STT_DIRECT_MAX_BYTES:
            return await self.transcribe(filename, content, content_type)

        chunks = await split_audio(content, filename)
        logger.info("Transcribing %d chunks in parallel", len(chunks))

        semaphore = asyncio.Semaphore(STT_PARALLEL_LIMIT)

        async def _one(index: int, data: bytes) -> tuple[int, str]:
            async with semaphore:
                text = await self.transcribe(
                    filename=f"chunk_{index:03d}.mp3",
                    content=data,
                    content_type="audio/mpeg",
                )
            return index, text

        results = await asyncio.gather(*[_one(i, c) for i, c in enumerate(chunks)])
        results.sort(key=lambda pair: pair[0])
        return "\n\n".join(text for _, text in results if text)

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
