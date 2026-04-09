"""Repository for file storage operations."""

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from biotact.modules.documents.models import File, Folder

logger = logging.getLogger(__name__)


class FileRepository:
    """Repository for folders and files CRUD."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ═══════════════════════════════════════════════════════════════
    # Folders
    # ═══════════════════════════════════════════════════════════════

    async def create_folder(
        self,
        name: str,
        uploaded_by: int,
        parent_id: int | None = None,
    ) -> Folder:
        """Create a new folder."""
        folder = Folder(
            name=name,
            parent_id=parent_id,
            uploaded_by=uploaded_by,
        )
        self.session.add(folder)
        await self.session.flush()
        await self.session.refresh(folder)
        await self.session.refresh(folder, ["parent"])
        return folder

    async def get_folder_by_uuid(self, folder_id: str) -> Folder | None:
        """Get folder by its UUID (folder_id)."""
        result = await self.session.execute(
            select(Folder).where(Folder.folder_id == folder_id)
        )
        return result.scalar_one_or_none()

    async def get_folder_by_id(self, folder_pk: int) -> Folder | None:
        """Get folder by primary key."""
        result = await self.session.execute(
            select(Folder).where(Folder.id == folder_pk)
        )
        return result.scalar_one_or_none()

    async def list_folders(
        self,
        parent_id: int | None = None,
    ) -> list[Folder]:
        """List folders at a given level (None = root)."""
        query = (
            select(Folder).where(Folder.parent_id == parent_id).order_by(Folder.name)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def rename_folder(self, folder: Folder, name: str) -> Folder:
        """Rename a folder."""
        folder.name = name
        await self.session.flush()
        await self.session.refresh(folder)
        await self.session.refresh(folder, ["parent"])
        return folder

    async def delete_folder(self, folder: Folder) -> None:
        """Delete a folder (CASCADE deletes children and files in DB)."""
        await self.session.delete(folder)
        await self.session.flush()

    async def get_folder_file_count(self, folder_pk: int) -> int:
        """Count files directly in a folder."""
        result = await self.session.execute(
            select(func.count(File.id)).where(File.folder_id == folder_pk)
        )
        return result.scalar_one()

    async def get_folder_file_counts(self, folder_ids: list[int]) -> dict[int, int]:
        """Batch count files for multiple folders in one query."""
        if not folder_ids:
            return {}
        result = await self.session.execute(
            select(File.folder_id, func.count(File.id))
            .where(File.folder_id.in_(folder_ids))
            .group_by(File.folder_id)
        )
        counts = {row[0]: row[1] for row in result.all()}
        return {fid: counts.get(fid, 0) for fid in folder_ids}

    async def get_breadcrumbs(self, folder_pk: int) -> list[Folder]:
        """Get folder chain from root to given folder."""
        chain: list[Folder] = []
        current = await self.get_folder_by_id(folder_pk)
        while current:
            chain.append(current)
            if current.parent_id:
                current = await self.get_folder_by_id(current.parent_id)
            else:
                current = None
        chain.reverse()
        return chain

    # ═══════════════════════════════════════════════════════════════
    # Files
    # ═══════════════════════════════════════════════════════════════

    async def create_file(
        self,
        name: str,
        original_name: str,
        mime_type: str,
        size: int,
        storage_path: str,
        uploaded_by: int,
        folder_id: int | None = None,
    ) -> File:
        """Create a new file record."""
        file = File(
            name=name,
            original_name=original_name,
            mime_type=mime_type,
            size=size,
            storage_path=storage_path,
            folder_id=folder_id,
            uploaded_by=uploaded_by,
        )
        self.session.add(file)
        await self.session.flush()
        await self.session.refresh(file)
        await self.session.refresh(file, ["folder"])
        return file

    async def get_file_by_uuid(self, file_id: str) -> File | None:
        """Get file by its UUID (file_id)."""
        result = await self.session.execute(select(File).where(File.file_id == file_id))
        return result.scalar_one_or_none()

    async def get_file_by_share_token(self, token: str) -> File | None:
        """Get file by share token (public download)."""
        result = await self.session.execute(
            select(File).where(File.share_token == token)
        )
        return result.scalar_one_or_none()

    async def list_files(
        self,
        folder_id: int | None = None,
    ) -> list[File]:
        """List files in a folder (None = root)."""
        query = (
            select(File)
            .where(File.folder_id == folder_id)
            .order_by(File.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_file(self, file: File) -> None:
        """Delete a file record."""
        await self.session.delete(file)
        await self.session.flush()

    async def update_index_status(
        self,
        file: File,
        is_indexed: bool,
        chunk_count: int,
    ) -> File:
        """Update file indexing status after RAG processing."""
        file.is_indexed = is_indexed
        file.chunk_count = chunk_count
        await self.session.flush()
        await self.session.refresh(file)
        return file

    async def set_share_token(self, file: File, token: str | None) -> File:
        """Set or clear share token."""
        file.share_token = token
        await self.session.flush()
        await self.session.refresh(file)
        await self.session.refresh(file, ["folder"])
        return file

    async def get_all_file_ids_in_folder(self, folder_pk: int) -> list[str]:
        """Get all file_ids (UUIDs) in a folder tree recursively.

        Used for cleaning up Qdrant vectors before folder deletion.
        """
        file_ids: list[str] = []

        # Direct files
        result = await self.session.execute(
            select(File.file_id).where(File.folder_id == folder_pk)
        )
        file_ids.extend(list(result.scalars().all()))

        # Recurse into subfolders
        result = await self.session.execute(
            select(Folder.id).where(Folder.parent_id == folder_pk)
        )
        child_ids: list[int] = list(result.scalars().all())  # type: ignore[arg-type]
        for child_id in child_ids:
            file_ids.extend(await self.get_all_file_ids_in_folder(child_id))

        return file_ids

    async def get_unindexed_files(self) -> list[File]:
        """Get files that need (re)indexing."""
        result = await self.session.execute(
            select(File).where(File.is_indexed == False)  # noqa: E712
        )
        return list(result.scalars().all())

    # ═══════════════════════════════════════════════════════════════
    # Tree & Stats
    # ═══════════════════════════════════════════════════════════════

    async def get_folder_tree_summary(self) -> list[dict[str, Any]]:
        """Get flat list of all folders with file counts for chat context.

        Single query with LEFT JOIN + GROUP BY to avoid N+1.
        """
        file_count_sub = (
            select(File.folder_id, func.count(File.id).label("file_count"))
            .group_by(File.folder_id)
            .subquery()
        )

        query = (
            select(
                Folder.id,
                Folder.folder_id,
                Folder.name,
                Folder.parent_id,
                func.coalesce(file_count_sub.c.file_count, 0).label("file_count"),
            )
            .outerjoin(file_count_sub, Folder.id == file_count_sub.c.folder_id)
            .order_by(Folder.name)
        )

        result = await self.session.execute(query)
        return [
            {
                "id": row.id,
                "folder_id": row.folder_id,
                "name": row.name,
                "parent_id": row.parent_id,
                "file_count": row.file_count,
            }
            for row in result.all()
        ]

    async def get_stats(self) -> dict[str, int]:
        """Get storage statistics (all users, shared platform)."""
        total_files_r = await self.session.execute(select(func.count(File.id)))
        total_folders_r = await self.session.execute(select(func.count(Folder.id)))
        total_size_r = await self.session.execute(
            select(func.coalesce(func.sum(File.size), 0))
        )
        indexed_r = await self.session.execute(
            select(func.count(File.id)).where(File.is_indexed == True)  # noqa: E712
        )

        return {
            "total_files": total_files_r.scalar_one(),
            "total_folders": total_folders_r.scalar_one(),
            "total_size": total_size_r.scalar_one(),
            "indexed_files": indexed_r.scalar_one(),
        }
