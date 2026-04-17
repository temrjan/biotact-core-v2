"""Media module REST API endpoints."""

import asyncio
import logging
import re
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from openai import AsyncOpenAI

from biotact.core.config import get_settings
from biotact.core.database import AsyncSessionLocal
from biotact.core.dependencies import CurrentUserDep, SessionDep
from biotact.models.user import User
from biotact.modules.media.chat_service import MediaChatService
from biotact.modules.media.indexing_service import index_transcription
from biotact.modules.media.models import MediaTranscription
from biotact.modules.media.openai_client import STT_DIRECT_MAX_BYTES, AudioClient
from biotact.modules.media.repository import MediaTranscriptionRepository
from biotact.modules.media.schemas import (
    MediaChatRequest,
    MediaChatResponse,
    SynthesizeRequest,
    TranscribeResponse,
    TranscriptionDetail,
    TranscriptionListItem,
    TranscriptionListResponse,
)
from biotact.modules.media.vector_store import MediaTranscriptionVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["media"])

MAX_UPLOAD_BYTES = 300_000_000  # 300 MB — backend accepts, splits if >20 MB
# Guard against OOM: only one split-transcription runs at a time.
_LONG_TRANSCRIBE_SEM = asyncio.Semaphore(1)
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

TITLE_MAX_CHARS = 252  # reserves room for the "…" suffix
PREVIEW_CHARS = 200


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


def _generate_mvp_title(text: str, created_at: datetime) -> str:
    """Derive a short title from the transcript, or fall back to date."""
    stripped = text.strip()
    if len(stripped) < 10:
        return created_at.strftime("%Y-%m-%d %H:%M")
    first_sentence = re.split(r"(?<=[.!?])\s+", stripped, maxsplit=1)[0]
    title = first_sentence[:100].strip() or stripped[:100]
    if len(title) > TITLE_MAX_CHARS:
        title = title[:TITLE_MAX_CHARS] + "…"
    return title


def _preview(text: str) -> str:
    """Short preview for list view."""
    stripped = text.strip()
    if len(stripped) <= PREVIEW_CHARS:
        return stripped
    return stripped[:PREVIEW_CHARS] + "…"


async def _cleanup_transcription_vectors(transcription_id: str) -> None:
    """Remove Qdrant vectors associated with a transcription."""
    store = MediaTranscriptionVectorStore(get_settings())
    try:
        await store.delete_transcription_vectors(transcription_id)
    except Exception:
        logger.exception(
            "Failed to delete vectors for transcription %s", transcription_id
        )


async def _get_or_404(
    repo: MediaTranscriptionRepository, transcription_id: str
) -> MediaTranscription:
    record = await repo.get_by_uuid(transcription_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Транскрипция не найдена",
        )
    return record


def _check_owner(record: MediaTranscription, current_user_id: int) -> None:
    if record.uploaded_by != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только автор может удалить запись",
        )


def _to_list_item(
    record: MediaTranscription, current_user: User
) -> TranscriptionListItem:
    return TranscriptionListItem(
        transcription_id=record.transcription_id,
        title=record.title,
        preview=_preview(record.text),
        summary=record.summary or "",
        uploaded_by=record.uploaded_by,
        uploaded_by_name=record.creator.full_name if record.creator else "",
        is_owner=record.uploaded_by == current_user.id,
        is_indexed=record.is_indexed,
        created_at=record.created_at,
    )


def _to_detail(record: MediaTranscription, current_user: User) -> TranscriptionDetail:
    return TranscriptionDetail(
        transcription_id=record.transcription_id,
        title=record.title,
        text=record.text,
        summary=record.summary or "",
        keywords=list(record.keywords or []),
        original_filename=record.original_filename,
        uploaded_by=record.uploaded_by,
        uploaded_by_name=record.creator.full_name if record.creator else "",
        is_owner=record.uploaded_by == current_user.id,
        is_indexed=record.is_indexed,
        created_at=record.created_at,
    )


@router.post("/audio/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile,
    current_user: CurrentUserDep,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> TranscribeResponse:
    """Transcribe uploaded audio via Whisper and persist the result."""
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
            detail="Файл больше 300 МБ",
        )

    client = _get_client()

    async def _run_transcribe() -> str:
        return await client.transcribe_long(
            filename=file.filename or "audio",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )

    try:
        if len(content) > STT_DIRECT_MAX_BYTES:
            async with _LONG_TRANSCRIBE_SEM:
                text = await _run_transcribe()
        else:
            text = await _run_transcribe()
    except Exception:
        logger.exception("Whisper transcription failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Не удалось выполнить транскрибацию",
        ) from None

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Транскрипция пустая — возможно, в записи нет речи",
        )

    repo = MediaTranscriptionRepository(session)
    title = _generate_mvp_title(text, datetime.utcnow())
    record = await repo.create(
        original_filename=file.filename or "audio",
        title=title,
        text=text,
        uploaded_by=current_user.id,
    )

    background_tasks.add_task(
        _index_transcription_background,
        transcription_id=record.transcription_id,
    )

    return TranscribeResponse(
        transcription_id=record.transcription_id,
        title=record.title,
        text=record.text,
    )


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


@router.get(
    "/audio/transcriptions",
    response_model=TranscriptionListResponse,
)
async def list_transcriptions(
    current_user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TranscriptionListResponse:
    """Paginated list of all transcriptions, newest first."""
    repo = MediaTranscriptionRepository(session)
    items, total = await repo.list_paginated(limit=limit, offset=offset)

    pages = (total + limit - 1) // limit if total else 0
    page = (offset // limit) + 1 if limit else 1

    return TranscriptionListResponse(
        items=[_to_list_item(r, current_user) for r in items],
        total=total,
        page=page,
        page_size=limit,
        pages=pages,
    )


@router.get(
    "/audio/transcriptions/{transcription_id}",
    response_model=TranscriptionDetail,
)
async def get_transcription(
    transcription_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> TranscriptionDetail:
    """Get full transcription detail."""
    repo = MediaTranscriptionRepository(session)
    record = await _get_or_404(repo, transcription_id)
    return _to_detail(record, current_user)


@router.delete(
    "/audio/transcriptions/{transcription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_transcription(
    transcription_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Delete transcription (owner only). Also removes vector index."""
    repo = MediaTranscriptionRepository(session)
    record = await _get_or_404(repo, transcription_id)
    _check_owner(record, current_user.id)

    await _cleanup_transcription_vectors(transcription_id)
    await repo.delete(record)


@router.post("/chat", response_model=MediaChatResponse)
async def media_chat(
    request: MediaChatRequest,
    _current_user: CurrentUserDep,
) -> MediaChatResponse:
    """Unified RAG chat across transcriptions + documents + knowledge bases."""
    settings = get_settings()
    embedding = EmbeddingService(settings)
    service = MediaChatService(settings=settings, embedding_service=embedding)
    return await service.query(
        message=request.message,
        history=request.history,
    )


async def _index_transcription_background(transcription_id: str) -> None:
    """Run the enrichment + Qdrant indexing pipeline out-of-band.

    Opens its own DB session (FastAPI BackgroundTask does not inherit the
    request scope). Failures are logged but do not raise — the record
    stays with MVP title and is_indexed=False; the user can retry.
    """
    settings = get_settings()
    llm_client = AsyncOpenAI(api_key=settings.openai_api_key)
    embedding_service = EmbeddingService(settings)
    vector_store = MediaTranscriptionVectorStore(settings)

    async with AsyncSessionLocal() as session:
        repo = MediaTranscriptionRepository(session)
        record = await repo.get_by_uuid(transcription_id)
        if not record:
            logger.warning(
                "Background indexing: transcription %s not found", transcription_id
            )
            return

        try:
            enrich, chunk_count = await index_transcription(
                transcription_id=record.transcription_id,
                user_id=record.uploaded_by,
                created_at=record.created_at,
                original_filename=record.original_filename,
                text=record.text,
                llm_client=llm_client,
                llm_model=settings.openai_model,
                embedding_service=embedding_service,
                vector_store=vector_store,
            )
        except Exception:
            logger.exception("Background indexing failed for %s", transcription_id)
            return

        new_title = enrich.title or record.title
        await repo.update_enrichment(
            record=record,
            title=new_title,
            summary=enrich.summary,
            keywords=enrich.keywords,
            chunk_count=chunk_count,
        )
        await session.commit()
