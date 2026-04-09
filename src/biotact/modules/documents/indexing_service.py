"""Indexing service — parse documents, chunk, embed, store in Qdrant.

Runs as BackgroundTask after file upload.
Uses asyncio.Semaphore(1) to limit concurrent indexing (RAM protection).
"""

import asyncio
import csv
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from biotact.modules.documents.vector_store import FileVectorStore
from biotact.services.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)

# Global semaphore — max 1 concurrent indexing to protect RAM
_indexing_semaphore = asyncio.Semaphore(1)

# Chunking parameters
CHUNK_SIZE = 1000  # characters
CHUNK_OVERLAP = 200  # characters


# ═══════════════════════════════════════════════════════════════════
# Document parsers
# ═══════════════════════════════════════════════════════════════════


def parse_txt(file_path: Path) -> str:
    """Parse plain text files (.txt, .md, .csv, .json)."""
    return file_path.read_text(encoding="utf-8", errors="replace")


def parse_csv_to_text(file_path: Path) -> str:
    """Parse CSV to readable text."""
    text_parts: list[str] = []
    with open(file_path, encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        for row in reader:
            text_parts.append(" | ".join(row))
    return "\n".join(text_parts)


def parse_json_to_text(file_path: Path) -> str:
    """Parse JSON to readable text."""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.warning("Failed to parse JSON %s: %s", file_path, e)
        return ""


def parse_pdf(file_path: Path) -> str:
    """Parse PDF using pymupdf (PyMuPDF)."""
    try:
        import pymupdf  # type: ignore[import-not-found]

        doc = pymupdf.open(str(file_path))
        text_parts: list[str] = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("pymupdf not installed, skipping PDF parsing")
        return ""
    except Exception as e:
        logger.error(f"Failed to parse PDF {file_path}: {e}")
        return ""


def parse_docx(file_path: Path) -> str:
    """Parse DOCX using python-docx."""
    try:
        from docx import Document

        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        logger.warning("python-docx not installed, skipping DOCX parsing")
        return ""
    except Exception as e:
        logger.error(f"Failed to parse DOCX {file_path}: {e}")
        return ""


def parse_xlsx(file_path: Path) -> str:
    """Parse XLSX using openpyxl."""
    try:
        from openpyxl import load_workbook  # type: ignore[import-untyped]

        wb = load_workbook(str(file_path), read_only=True, data_only=True)
        text_parts: list[str] = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            text_parts.append(f"--- {sheet} ---")
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(cells):
                    text_parts.append(" | ".join(cells))
        wb.close()
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("openpyxl not installed, skipping XLSX parsing")
        return ""
    except Exception as e:
        logger.error(f"Failed to parse XLSX {file_path}: {e}")
        return ""


# Parser dispatch by extension
PARSERS: dict[str, Callable[..., str]] = {
    ".txt": parse_txt,
    ".md": parse_txt,
    ".csv": parse_csv_to_text,
    ".json": parse_json_to_text,
    ".pdf": parse_pdf,
    ".docx": parse_docx,
    ".doc": parse_docx,
    ".xlsx": parse_xlsx,
    ".xls": parse_xlsx,
}


def parse_document(file_path: Path) -> str:
    """Parse document to text based on extension.

    Args:
        file_path: Path to the file.

    Returns:
        Extracted text, or empty string if unsupported.
    """
    ext = file_path.suffix.lower()
    parser = PARSERS.get(ext)
    if not parser:
        logger.warning(f"No parser for extension {ext}")
        return ""
    return parser(file_path)


# ═══════════════════════════════════════════════════════════════════
# Chunking
# ═══════════════════════════════════════════════════════════════════


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks by character count.

    Args:
        text: Full document text.
        chunk_size: Max characters per chunk.
        overlap: Characters to overlap between chunks.

    Returns:
        List of text chunks.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size

        # Try to break at a sentence boundary
        if end < len(text):
            # Look for sentence-ending punctuation near the end
            for sep in [". ", ".\n", "! ", "? ", "\n\n", "\n"]:
                last_sep = text.rfind(sep, start + chunk_size // 2, end)
                if last_sep != -1:
                    end = last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap
        if start <= (end - chunk_size):
            # Prevent infinite loop on very long lines
            start = end

    return chunks


# ═══════════════════════════════════════════════════════════════════
# Indexing pipeline
# ═══════════════════════════════════════════════════════════════════


async def index_file(
    file_id: str,
    file_name: str,
    storage_path: str,
    embedding_service: EmbeddingService,
    vector_store: FileVectorStore,
    update_callback: Callable[..., Any] | None = None,
) -> int:
    """Full indexing pipeline: parse → chunk → embed → upsert.

    Protected by semaphore — max 1 concurrent indexing.

    Args:
        file_id: UUID of the file.
        file_name: Display name.
        storage_path: Path to file on disk.
        embedding_service: For generating embeddings.
        vector_store: For Qdrant operations.
        update_callback: Optional async callback(is_indexed, chunk_count).

    Returns:
        Number of chunks indexed.
    """
    async with _indexing_semaphore:
        try:
            logger.info(f"Indexing file: {file_name} ({file_id})")

            # 1. Parse
            file_path = Path(storage_path)
            text = parse_document(file_path)
            if not text:
                logger.warning(f"No text extracted from {file_name}")
                if update_callback:
                    await update_callback(False, 0)
                return 0

            # 2. Chunk
            chunks = chunk_text(text)
            if not chunks:
                logger.warning(f"No chunks created for {file_name}")
                if update_callback:
                    await update_callback(False, 0)
                return 0

            logger.info(f"Created {len(chunks)} chunks for {file_name}")

            # 3. Embed (batch, max 2048 per OpenAI request)
            embeddings: list[list[float]] = []
            batch_size = 100
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                batch_embeddings = await embedding_service.embed_texts(batch)
                embeddings.extend(batch_embeddings)

            # 4. Upsert to Qdrant
            chunk_count = await vector_store.upsert_chunks(
                file_id=file_id,
                file_name=file_name,
                chunks=chunks,
                embeddings=embeddings,
            )

            # 5. Update DB status
            if update_callback:
                await update_callback(True, chunk_count)

            logger.info(f"Indexed {file_name}: {chunk_count} chunks")
            return chunk_count

        except Exception as e:
            logger.error(f"Failed to index {file_name}: {e}", exc_info=True)
            if update_callback:
                await update_callback(False, 0)
            return 0
