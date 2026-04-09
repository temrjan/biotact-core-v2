"""Pydantic schemas for file storage module."""

from datetime import datetime

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════
# Folder schemas
# ═══════════════════════════════════════════════════════════════════


class FolderCreateRequest(BaseModel):
    """Create a new folder."""

    name: str = Field(min_length=1, max_length=255)
    parent_id: str | None = None  # folder_id of parent, None = root


class FolderRenameRequest(BaseModel):
    """Rename a folder."""

    name: str = Field(min_length=1, max_length=255)


class FolderResponse(BaseModel):
    """Folder in response."""

    folder_id: str
    name: str
    parent_id: str | None = None
    uploaded_by: int
    uploaded_by_name: str = ""
    file_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ═══════════════════════════════════════════════════════════════════
# File schemas
# ═══════════════════════════════════════════════════════════════════


class FileResponse(BaseModel):
    """File in response."""

    file_id: str
    name: str
    original_name: str
    mime_type: str
    size: int
    folder_id: str | None = None
    uploaded_by: int
    uploaded_by_name: str = ""
    is_indexed: bool
    chunk_count: int
    share_token: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FileStatsResponse(BaseModel):
    """Storage statistics."""

    total_files: int
    total_folders: int
    total_size: int  # bytes
    indexed_files: int


# ═══════════════════════════════════════════════════════════════════
# Breadcrumb
# ═══════════════════════════════════════════════════════════════════


class BreadcrumbItem(BaseModel):
    """Single breadcrumb item."""

    folder_id: str | None = None  # None = root
    name: str


# ═══════════════════════════════════════════════════════════════════
# Chat schemas
# ═══════════════════════════════════════════════════════════════════


class ChatMessage(BaseModel):
    """Single chat message."""

    role: str  # "user" or "assistant"
    content: str


class FilesChatRequest(BaseModel):
    """Chat request for document search."""

    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] | None = None


class FilesChatSource(BaseModel):
    """Source document in chat response."""

    file_name: str
    score: float


class FilesChatResponse(BaseModel):
    """Chat response with sources."""

    answer: str
    sources: list[FilesChatSource]
