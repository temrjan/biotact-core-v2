"""File service — upload, download, delete operations on filesystem."""

import logging
import os
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

logger = logging.getLogger(__name__)

# Allowed extensions and their MIME types
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB
UPLOAD_BASE_DIR = Path("/data/uploads")


def get_upload_dir() -> Path:
    """Get base upload directory, create if not exists."""
    UPLOAD_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_BASE_DIR


def validate_file(file: UploadFile) -> tuple[str, str]:
    """Validate uploaded file: extension, MIME type, size.

    Args:
        file: FastAPI UploadFile.

    Returns:
        Tuple of (sanitized_name, extension).

    Raises:
        HTTPException: If file is invalid.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Имя файла не указано",
        )

    # Extract and validate extension
    _, ext = os.path.splitext(file.filename)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Формат {ext} не поддерживается. Допустимые: {allowed}",
        )

    # Sanitize filename — keep only safe characters
    safe_name = "".join(
        c for c in file.filename if c.isalnum() or c in "._- "
    ).strip()
    if not safe_name:
        safe_name = f"file{ext}"

    return safe_name, ext


async def save_file(file: UploadFile, file_id: str) -> tuple[str, int]:
    """Save uploaded file to disk.

    Args:
        file: FastAPI UploadFile.
        file_id: UUID for directory isolation.

    Returns:
        Tuple of (storage_path, file_size_bytes).

    Raises:
        HTTPException: If file exceeds size limit.
    """
    upload_dir = get_upload_dir() / file_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name, _ = validate_file(file)
    file_path = upload_dir / safe_name

    # Stream file to disk, checking size
    total_size = 0
    try:
        with open(file_path, "wb") as f:
            while chunk := await file.read(64 * 1024):  # 64KB chunks
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE_BYTES:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    upload_dir.rmdir()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Файл превышает лимит {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB",
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file {safe_name}: {e}")
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при сохранении файла",
        ) from e

    return str(file_path), total_size


def delete_file_from_disk(storage_path: str) -> None:
    """Delete file and its parent directory from disk.

    Args:
        storage_path: Full path to the file.
    """
    try:
        path = Path(storage_path)
        if path.exists():
            path.unlink()
        # Remove parent dir if empty (the file_id directory)
        parent = path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    except Exception as e:
        logger.warning(f"Failed to delete file from disk: {storage_path}: {e}")


def delete_folder_from_disk(folder_file_paths: list[str]) -> None:
    """Delete multiple files from disk (used when deleting a folder).

    Args:
        folder_file_paths: List of storage paths to delete.
    """
    for path in folder_file_paths:
        delete_file_from_disk(path)


def generate_share_token() -> str:
    """Generate a secure random share token."""
    return secrets.token_urlsafe(48)


def get_file_path(storage_path: str) -> Path:
    """Get Path object for a stored file, verify existence.

    Args:
        storage_path: Full path to file.

    Returns:
        Path object.

    Raises:
        HTTPException: If file not found on disk.
    """
    path = Path(storage_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Файл не найден на диске",
        )
    return path
