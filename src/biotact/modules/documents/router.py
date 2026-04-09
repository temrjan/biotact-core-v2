"""Documents module REST API endpoints."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from biotact.core.config import get_settings
from biotact.core.dependencies import CurrentUserDep, SessionDep
from biotact.modules.documents import file_service
from biotact.modules.documents.chat_service import FilesChatService
from biotact.modules.documents.models import File, Folder
from biotact.modules.documents.repository import FileRepository
from biotact.modules.documents.schemas import (
    BreadcrumbItem,
    FilesChatRequest,
    FilesChatResponse,
    FileStatsResponse,
    FolderCreateRequest,
    FolderRenameRequest,
    FolderResponse,
)
from biotact.modules.documents.schemas import (
    FileResponse as FileResponseSchema,
)
from biotact.modules.documents.vector_store import FileVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_repo(session: SessionDep) -> FileRepository:
    """Shortcut to create FileRepository from session."""
    return FileRepository(session)


# ═══════════════════════════════════════════════════════════════════
# Folders
# ═══════════════════════════════════════════════════════════════════


@router.post("/folders", response_model=FolderResponse, status_code=201)
async def create_folder(
    request: FolderCreateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> FolderResponse:
    """Create a new folder."""
    repo = _get_repo(session)

    # Resolve parent
    parent_pk: int | None = None
    if request.parent_id:
        parent = await repo.get_folder_by_uuid(request.parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Родительская папка не найдена",
            )
        parent_pk = parent.id

    folder = await repo.create_folder(
        name=request.name,
        uploaded_by=current_user.id,
        parent_id=parent_pk,
    )

    return _folder_to_response(folder, current_user.full_name)


@router.get("/folders", response_model=list[FolderResponse])
async def list_folders(
    _current_user: CurrentUserDep,
    session: SessionDep,
    parent_id: str | None = Query(default=None, description="folder_id родителя"),
) -> list[FolderResponse]:
    """List folders at a given level. No parent_id = root."""
    repo = _get_repo(session)

    parent_pk: int | None = None
    if parent_id:
        parent = await repo.get_folder_by_uuid(parent_id)
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Папка не найдена",
            )
        parent_pk = parent.id

    folders = await repo.list_folders(parent_id=parent_pk)

    result = []
    for f in folders:
        count = await repo.get_folder_file_count(f.id)
        resp = _folder_to_response(f, f.creator.full_name if f.creator else "")
        resp.file_count = count
        result.append(resp)

    return result


@router.patch("/folders/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    folder_id: str,
    request: FolderRenameRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> FolderResponse:
    """Rename a folder. Only the creator can rename."""
    repo = _get_repo(session)
    folder = await _get_folder_or_404(repo, folder_id)
    _check_owner(folder.uploaded_by, current_user.id)

    folder = await repo.rename_folder(folder, request.name)
    return _folder_to_response(folder, current_user.full_name)


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Delete a folder and all contents. Only the creator can delete."""
    repo = _get_repo(session)
    folder = await _get_folder_or_404(repo, folder_id)
    _check_owner(folder.uploaded_by, current_user.id)

    # Collect file IDs and paths for cleanup
    file_ids = await repo.get_all_file_ids_in_folder(folder.id)
    storage_paths: list[str] = []
    for fid in file_ids:
        f = await repo.get_file_by_uuid(fid)
        if f:
            storage_paths.append(f.storage_path)

    # Delete from DB (CASCADE handles children + files)
    await repo.delete_folder(folder)

    # Cleanup Qdrant vectors
    settings = get_settings()
    vector_store = FileVectorStore(settings)
    await vector_store.delete_files_vectors(file_ids)

    # Cleanup disk
    file_service.delete_folder_from_disk(storage_paths)


# ═══════════════════════════════════════════════════════════════════
# Files
# ═══════════════════════════════════════════════════════════════════


@router.post("/upload", response_model=FileResponseSchema, status_code=201)
async def upload_file(
    file: UploadFile,
    current_user: CurrentUserDep,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    folder_id: str | None = Query(default=None, description="folder_id куда загрузить"),
) -> FileResponseSchema:
    """Upload a file. Optionally specify a folder. Indexing runs in background."""
    repo = _get_repo(session)

    # Validate
    safe_name, ext = file_service.validate_file(file)
    mime = file.content_type or file_service.ALLOWED_EXTENSIONS.get(
        ext, "application/octet-stream"
    )

    # Resolve folder
    folder_pk: int | None = None
    if folder_id:
        folder = await repo.get_folder_by_uuid(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Папка не найдена",
            )
        folder_pk = folder.id

    # Generate file_id for path isolation
    new_file_id = str(uuid.uuid4())

    # Save to disk
    storage_path, size = await file_service.save_file(file, new_file_id)

    # Save to DB
    db_file = await repo.create_file(
        name=safe_name,
        original_name=file.filename or safe_name,
        mime_type=mime,
        size=size,
        storage_path=storage_path,
        uploaded_by=current_user.id,
        folder_id=folder_pk,
    )

    # Schedule background indexing
    background_tasks.add_task(
        _index_file_background,
        file_id=db_file.file_id,
        file_name=db_file.name,
        storage_path=db_file.storage_path,
    )

    return _file_to_response(db_file, current_user.full_name)


@router.get("/", response_model=list[FileResponseSchema])
async def list_files(
    _current_user: CurrentUserDep,
    session: SessionDep,
    folder_id: str | None = Query(default=None, description="folder_id для фильтрации"),
) -> list[FileResponseSchema]:
    """List files in a folder. No folder_id = root files."""
    repo = _get_repo(session)

    folder_pk: int | None = None
    if folder_id:
        folder = await repo.get_folder_by_uuid(folder_id)
        if not folder:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Папка не найдена",
            )
        folder_pk = folder.id

    files = await repo.list_files(folder_id=folder_pk)
    return [
        _file_to_response(f, f.creator.full_name if f.creator else "") for f in files
    ]


@router.get("/{file_id}/download")
async def download_file(
    file_id: str,
    _current_user: CurrentUserDep,
    session: SessionDep,
) -> FileResponse:
    """Download a file by file_id."""
    repo = _get_repo(session)
    db_file = await _get_file_or_404(repo, file_id)
    path = file_service.get_file_path(db_file.storage_path)

    return FileResponse(
        path=str(path),
        filename=db_file.original_name,
        media_type=db_file.mime_type,
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file(
    file_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Delete a file. Only the creator can delete."""
    repo = _get_repo(session)
    db_file = await _get_file_or_404(repo, file_id)
    _check_owner(db_file.uploaded_by, current_user.id)

    storage_path = db_file.storage_path
    target_file_id = db_file.file_id
    await repo.delete_file(db_file)

    # Cleanup Qdrant vectors
    settings = get_settings()
    vector_store = FileVectorStore(settings)
    await vector_store.delete_file_vectors(target_file_id)

    # Cleanup disk
    file_service.delete_file_from_disk(storage_path)


# ═══════════════════════════════════════════════════════════════════
# Sharing
# ═══════════════════════════════════════════════════════════════════


@router.post("/{file_id}/share", response_model=FileResponseSchema)
async def share_file(
    file_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> FileResponseSchema:
    """Generate a share link for a file. Only the creator can share."""
    repo = _get_repo(session)
    db_file = await _get_file_or_404(repo, file_id)
    _check_owner(db_file.uploaded_by, current_user.id)

    token = file_service.generate_share_token()
    db_file = await repo.set_share_token(db_file, token)
    return _file_to_response(db_file, current_user.full_name)


@router.delete("/{file_id}/share", status_code=204)
async def unshare_file(
    file_id: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> None:
    """Revoke share link. Only the creator can unshare."""
    repo = _get_repo(session)
    db_file = await _get_file_or_404(repo, file_id)
    _check_owner(db_file.uploaded_by, current_user.id)

    await repo.set_share_token(db_file, None)


@router.get("/shared/{token}")
async def download_shared_file(
    token: str,
    session: SessionDep,
) -> FileResponse:
    """Download a file by share token (no auth required)."""
    repo = FileRepository(session)
    db_file = await repo.get_file_by_share_token(token)
    if not db_file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ссылка недействительна",
        )

    path = file_service.get_file_path(db_file.storage_path)
    return FileResponse(
        path=str(path),
        filename=db_file.original_name,
        media_type=db_file.mime_type,
    )


# ═══════════════════════════════════════════════════════════════════
# Navigation & Stats
# ═══════════════════════════════════════════════════════════════════


@router.get("/breadcrumbs/{folder_id}", response_model=list[BreadcrumbItem])
async def get_breadcrumbs(
    folder_id: str,
    _current_user: CurrentUserDep,
    session: SessionDep,
) -> list[BreadcrumbItem]:
    """Get breadcrumb trail from root to folder."""
    repo = _get_repo(session)
    folder = await _get_folder_or_404(repo, folder_id)
    chain = await repo.get_breadcrumbs(folder.id)

    # Prepend root
    crumbs = [BreadcrumbItem(folder_id=None, name="Все документы")]
    for f in chain:
        crumbs.append(BreadcrumbItem(folder_id=f.folder_id, name=f.name))
    return crumbs


@router.get("/stats", response_model=FileStatsResponse)
async def get_stats(
    _current_user: CurrentUserDep,
    session: SessionDep,
) -> FileStatsResponse:
    """Get storage statistics."""
    repo = _get_repo(session)
    data = await repo.get_stats()
    return FileStatsResponse(**data)


# ═══════════════════════════════════════════════════════════════════
# Chat (LLM + RAG over documents)
# ═══════════════════════════════════════════════════════════════════


@router.post("/chat", response_model=FilesChatResponse)
async def files_chat(
    request: FilesChatRequest,
    _current_user: CurrentUserDep,
    session: SessionDep,
) -> FilesChatResponse:
    """Chat with LLM about uploaded documents. Folder-aware + RAG search."""
    settings = get_settings()
    embedding_service = EmbeddingService(settings)
    vector_store = FileVectorStore(settings)
    chat_service = FilesChatService(
        settings, embedding_service, vector_store, db=session
    )

    history = None
    if request.history:
        history = [{"role": m.role, "content": m.content} for m in request.history]

    return await chat_service.query(
        message=request.message,
        history=history,
    )


# ═══════════════════════════════════════════════════════════════════
# Background tasks
# ═══════════════════════════════════════════════════════════════════


async def _index_file_background(
    file_id: str,
    file_name: str,
    storage_path: str,
) -> None:
    """Background task: index a file after upload."""
    from biotact.core.database import AsyncSessionLocal
    from biotact.modules.documents import indexing_service

    settings = get_settings()
    embedding_service = EmbeddingService(settings)
    vector_store = FileVectorStore(settings)

    async def update_callback(is_indexed: bool, chunk_count: int) -> None:
        """Update file index status in DB."""
        async with AsyncSessionLocal() as session:
            repo = FileRepository(session)
            file = await repo.get_file_by_uuid(file_id)
            if file:
                await repo.update_index_status(file, is_indexed, chunk_count)
                await session.commit()

    await indexing_service.index_file(
        file_id=file_id,
        file_name=file_name,
        storage_path=storage_path,
        embedding_service=embedding_service,
        vector_store=vector_store,
        update_callback=update_callback,
    )


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


async def _get_folder_or_404(repo: FileRepository, folder_id: str) -> Folder:
    """Get folder by UUID or raise 404."""
    folder = await repo.get_folder_by_uuid(folder_id)
    if not folder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Папка не найдена",
        )
    return folder


async def _get_file_or_404(repo: FileRepository, file_id: str) -> File:
    """Get file by UUID or raise 404."""
    file = await repo.get_file_by_uuid(file_id)
    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден",
        )
    return file


def _check_owner(resource_owner_id: int, current_user_id: int) -> None:
    """Check that current user is the resource owner."""
    if resource_owner_id != current_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только автор может выполнить это действие",
        )


def _folder_to_response(folder: Folder, author_name: str) -> FolderResponse:
    """Convert Folder model to response schema."""
    parent_uuid = None
    if folder.parent and hasattr(folder.parent, "folder_id"):
        parent_uuid = folder.parent.folder_id

    return FolderResponse(
        folder_id=folder.folder_id,
        name=folder.name,
        parent_id=parent_uuid,
        uploaded_by=folder.uploaded_by,
        uploaded_by_name=author_name,
        created_at=folder.created_at,
    )


def _file_to_response(file: File, author_name: str) -> FileResponseSchema:
    """Convert File model to response schema."""
    folder_uuid = None
    if file.folder and hasattr(file.folder, "folder_id"):
        folder_uuid = file.folder.folder_id

    return FileResponseSchema(
        file_id=file.file_id,
        name=file.name,
        original_name=file.original_name,
        mime_type=file.mime_type,
        size=file.size,
        folder_id=folder_uuid,
        uploaded_by=file.uploaded_by,
        uploaded_by_name=author_name,
        is_indexed=file.is_indexed,
        chunk_count=file.chunk_count,
        share_token=file.share_token,
        created_at=file.created_at,
    )
