"""Media module REST API endpoints."""

import logging
from functools import lru_cache

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.responses import Response

from biotact.core.config import get_settings
from biotact.core.dependencies import CurrentUserDep
from biotact.modules.media.openai_client import AudioClient
from biotact.modules.media.schemas import SynthesizeRequest, TranscribeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_BYTES = 25_000_000  # 25 MB — OpenAI Whisper limit
ALLOWED_AUDIO_EXT = (
    ".mp3",
    ".m4a",
    ".wav",
    ".ogg",
    ".oga",
    ".webm",
    ".mp4",
    ".mpeg",
    ".mpga",
)


@lru_cache
def _get_client() -> AudioClient:
    """Cached AudioClient instance (AsyncOpenAI is safe to reuse)."""
    return AudioClient(get_settings())


def _validate_audio(file: UploadFile) -> None:
    """Ensure uploaded file looks like a supported audio file."""
    name = (file.filename or "").lower()
    if not name.endswith(ALLOWED_AUDIO_EXT):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый формат. Разрешены: {', '.join(ALLOWED_AUDIO_EXT)}",
        )


@router.post("/audio/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile,
    _current_user: CurrentUserDep,
) -> TranscribeResponse:
    """Transcribe uploaded audio file to Russian text via Whisper."""
    _validate_audio(file)

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл пустой",
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Файл больше 25 МБ",
        )

    client = _get_client()
    try:
        text = await client.transcribe(
            filename=file.filename or "audio",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception:
        logger.exception("Whisper transcription failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось выполнить транскрибацию",
        ) from None

    return TranscribeResponse(text=text)


@router.post("/audio/synthesize")
async def synthesize_audio(
    request: SynthesizeRequest,
    _current_user: CurrentUserDep,
) -> Response:
    """Synthesize Russian text to MP3 audio via OpenAI TTS-1."""
    client = _get_client()
    try:
        audio_bytes = await client.synthesize(request.text, request.voice)
    except Exception:
        logger.exception("OpenAI TTS failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось синтезировать аудио",
        ) from None

    return Response(
        content=audio_bytes,
        media_type="audio/mpeg",
        headers={"Content-Disposition": 'attachment; filename="speech.mp3"'},
    )
