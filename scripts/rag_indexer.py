#!/usr/bin/env python3
"""
Universal RAG Indexer for Qdrant.

A flexible tool for indexing documents into Qdrant vector database
with support for multiple formats, bilingual content, and incremental indexing.

Usage:
    rag-indexer index                      # Use ./rag_config.yaml
    rag-indexer index --config config.yaml
    rag-indexer index --dry-run
    rag-indexer stats
    rag-indexer search "query"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

logger = logging.getLogger("rag-indexer")


def setup_logging(*, verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class QdrantConfig:
    """Qdrant connection settings."""

    collection: str = "knowledge"
    host: str = field(default_factory=lambda: os.getenv("QDRANT_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("QDRANT_PORT", "6333")))
    auto_create: bool = True
    distance: str = "cosine"


@dataclass
class SourceConfig:
    """Source documents settings."""

    path: str = "./documents"
    patterns: list[str] = field(default_factory=lambda: ["*.txt"])
    encoding: str = "utf-8"


@dataclass
class LanguageConfig:
    """Single language configuration for bilingual mode."""

    code: str
    title_pattern: str = ""
    content_marker: str = ""
    primary: bool = False


@dataclass
class BilingualConfig:
    """Bilingual content settings."""

    enabled: bool = False
    languages: list[LanguageConfig] = field(default_factory=list)


@dataclass
class ParserConfig:
    """Document parser settings."""

    format: str = "plain"  # plain | sections | markdown
    section_start: str = "===SECTION==="
    section_end: str = "===/SECTION==="
    title_pattern: str = r"Title:\s*(.+)"
    heading_level: int = 2  # For markdown: split by ## headers


@dataclass
class ChunkingConfig:
    """Chunking settings."""

    max_chars: int = 8000
    min_chars: int = 50


@dataclass
class EmbeddingsConfig:
    """Embedding settings."""

    model: str = "text-embedding-3-large"
    dimensions: int = 3072
    batch_size: int = 20
    max_tokens_per_batch: int = 8000


@dataclass
class IndexingConfig:
    """Indexing behavior settings."""

    incremental: bool = True
    clean_orphaned: bool = False
    state_file: str = ".rag_state.json"


@dataclass
class IndexerConfig:
    """Root configuration combining all sections."""

    qdrant: QdrantConfig = field(default_factory=QdrantConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    bilingual: BilingualConfig = field(default_factory=BilingualConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embeddings: EmbeddingsConfig = field(default_factory=EmbeddingsConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> IndexerConfig:
        """Load configuration from YAML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> IndexerConfig:
        """Create config from dictionary."""
        config = cls()

        # Qdrant
        if "qdrant" in data:
            q = data["qdrant"]
            config.qdrant = QdrantConfig(
                collection=q.get("collection", config.qdrant.collection),
                host=q.get("host", config.qdrant.host),
                port=q.get("port", config.qdrant.port),
                auto_create=q.get("auto_create", config.qdrant.auto_create),
                distance=q.get("distance", config.qdrant.distance),
            )

        # Source
        if "source" in data:
            s = data["source"]
            config.source = SourceConfig(
                path=s.get("path", config.source.path),
                patterns=s.get("patterns", config.source.patterns),
                encoding=s.get("encoding", config.source.encoding),
            )

        # Parser
        if "parser" in data:
            p = data["parser"]
            config.parser = ParserConfig(
                format=p.get("format", config.parser.format),
                section_start=p.get("section_start", config.parser.section_start),
                section_end=p.get("section_end", config.parser.section_end),
                title_pattern=p.get("title_pattern", config.parser.title_pattern),
                heading_level=p.get("heading_level", config.parser.heading_level),
            )

        # Bilingual
        if "bilingual" in data:
            b = data["bilingual"]
            languages = []
            for lang in b.get("languages", []):
                languages.append(
                    LanguageConfig(
                        code=lang.get("code", ""),
                        title_pattern=lang.get("title_pattern", ""),
                        content_marker=lang.get("content_marker", ""),
                        primary=lang.get("primary", False),
                    )
                )
            config.bilingual = BilingualConfig(
                enabled=b.get("enabled", False),
                languages=languages,
            )

        # Chunking
        if "chunking" in data:
            c = data["chunking"]
            config.chunking = ChunkingConfig(
                max_chars=c.get("max_chars", config.chunking.max_chars),
                min_chars=c.get("min_chars", config.chunking.min_chars),
            )

        # Embeddings
        if "embeddings" in data:
            e = data["embeddings"]
            config.embeddings = EmbeddingsConfig(
                model=e.get("model", config.embeddings.model),
                dimensions=e.get("dimensions", config.embeddings.dimensions),
                batch_size=e.get("batch_size", config.embeddings.batch_size),
                max_tokens_per_batch=e.get(
                    "max_tokens_per_batch", config.embeddings.max_tokens_per_batch
                ),
            )

        # Indexing
        if "indexing" in data:
            i = data["indexing"]
            config.indexing = IndexingConfig(
                incremental=i.get("incremental", config.indexing.incremental),
                clean_orphaned=i.get("clean_orphaned", config.indexing.clean_orphaned),
                state_file=i.get("state_file", config.indexing.state_file),
            )

        # Metadata
        config.metadata = data.get("metadata", {})

        return config

    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []

        if not self.qdrant.collection:
            errors.append("qdrant.collection is required")

        if self.parser.format not in ("plain", "sections", "markdown"):
            errors.append(f"Invalid parser.format: {self.parser.format}")

        if self.bilingual.enabled and not self.bilingual.languages:
            errors.append("bilingual.languages required when bilingual.enabled=true")

        if self.embeddings.dimensions <= 0:
            errors.append("embeddings.dimensions must be positive")

        return errors


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS
# ═══════════════════════════════════════════════════════════════════════════════


def parse_plain(content: str, config: ParserConfig) -> list[dict[str, Any]]:
    """Parse plain text as single chunk."""
    return [{"index": 1, "content": content.strip(), "title": ""}]


def parse_sections(content: str, config: ParserConfig) -> list[dict[str, Any]]:
    """Parse document with section markers."""
    sections: list[dict[str, Any]] = []
    pattern = re.escape(config.section_start) + r"(.*?)" + re.escape(config.section_end)
    matches = re.findall(pattern, content, re.DOTALL)

    for idx, match in enumerate(matches, 1):
        section: dict[str, Any] = {"index": idx, "content": match.strip(), "title": ""}

        # Extract title if pattern provided
        if config.title_pattern:
            title_match = re.search(config.title_pattern, match)
            if title_match:
                section["title"] = title_match.group(1).strip()

        if section["content"]:
            sections.append(section)

    return sections


def parse_markdown(content: str, config: ParserConfig) -> list[dict[str, Any]]:
    """Parse markdown by heading level."""
    sections: list[dict[str, Any]] = []
    heading_prefix = "#" * config.heading_level + " "

    # Split by headings
    parts = re.split(rf"^({re.escape(heading_prefix)}.+)$", content, flags=re.MULTILINE)

    current_title = ""
    current_content = ""
    idx = 0

    for part in parts:
        if part.startswith(heading_prefix):
            # Save previous section
            if current_content.strip():
                idx += 1
                sections.append(
                    {
                        "index": idx,
                        "title": current_title,
                        "content": current_content.strip(),
                    }
                )
            current_title = part[len(heading_prefix) :].strip()
            current_content = ""
        else:
            current_content += part

    # Save last section
    if current_content.strip():
        idx += 1
        sections.append(
            {"index": idx, "title": current_title, "content": current_content.strip()}
        )

    return sections


def parse_document(
    content: str,
    config: ParserConfig,
) -> list[dict[str, Any]]:
    """Route to appropriate parser based on format."""
    parsers = {
        "plain": parse_plain,
        "sections": parse_sections,
        "markdown": parse_markdown,
    }
    parser_func = parsers.get(config.format, parse_plain)
    return parser_func(content, config)


# ═══════════════════════════════════════════════════════════════════════════════
# BILINGUAL PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════


def extract_bilingual_content(
    text: str,
    config: BilingualConfig,
) -> dict[str, Any]:
    """Extract content for each language from bilingual text."""
    result: dict[str, Any] = {"full_text": text}

    if not config.enabled:
        return result

    for lang in config.languages:
        code = lang.code

        # Extract title
        if lang.title_pattern:
            title_match = re.search(lang.title_pattern, text)
            result[f"title_{code}"] = title_match.group(1).strip() if title_match else ""

        # Extract content
        if lang.content_marker:
            # Find content between this marker and next marker (or end)
            markers = [l.content_marker for l in config.languages if l.content_marker]
            other_markers = [m for m in markers if m != lang.content_marker]

            if other_markers:
                pattern = (
                    re.escape(lang.content_marker)
                    + r"\n(.*?)(?:"
                    + "|".join(re.escape(m) for m in other_markers)
                    + r"|$)"
                )
            else:
                pattern = re.escape(lang.content_marker) + r"\n(.*?)$"

            content_match = re.search(pattern, text, re.DOTALL)
            result[f"content_{code}"] = (
                content_match.group(1).strip() if content_match else ""
            )

    return result


def build_embedding_text(
    chunk: dict[str, Any],
    bilingual_data: dict[str, Any],
    config: BilingualConfig,
) -> str:
    """Build text for embedding from chunk and bilingual data."""
    if not config.enabled:
        return chunk.get("content", "")

    # Concatenate all languages
    parts: list[str] = []

    for lang in config.languages:
        code = lang.code
        title = bilingual_data.get(f"title_{code}", "")
        content = bilingual_data.get(f"content_{code}", "")

        if title:
            parts.append(f"[{title}]")
        if content:
            parts.append(content)

    return "\n\n".join(parts) if parts else chunk.get("content", "")


# ═══════════════════════════════════════════════════════════════════════════════
# STATE MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class StateManager:
    """Manages index state for incremental indexing."""

    __slots__ = ("path", "state")

    def __init__(self, state_path: Path) -> None:
        """Initialize state manager."""
        self.path = state_path
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        """Load state from file."""
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load state: {e}")
                return {}
        return {}

    def save(self) -> None:
        """Save state to file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_file_hash(self, filepath: Path) -> str:
        """Calculate MD5 hash of file."""
        return hashlib.md5(filepath.read_bytes()).hexdigest()

    def needs_reindex(self, filepath: Path) -> bool:
        """Check if file needs reindexing."""
        current_hash = self.get_file_hash(filepath)
        stored = self.state.get(filepath.name, {})
        return stored.get("hash") != current_hash

    def update(self, filepath: Path, chunks_count: int) -> None:
        """Update state after indexing."""
        self.state[filepath.name] = {
            "hash": self.get_file_hash(filepath),
            "chunks": chunks_count,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_indexed_files(self) -> set[str]:
        """Return set of indexed filenames."""
        return set(self.state.keys())


# ═══════════════════════════════════════════════════════════════════════════════
# EMBEDDING MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class EmbeddingManager:
    """Manages OpenAI embeddings with batching and retry."""

    __slots__ = ("client", "config")

    def __init__(self, config: EmbeddingsConfig) -> None:
        """Initialize embedding manager."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.client = OpenAI(api_key=api_key)
        self.config = config

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (conservative for non-English)."""
        return len(text) // 2

    def create_batches(self, texts: list[str]) -> list[list[int]]:
        """Create batches respecting token limits."""
        batches: list[list[int]] = []
        current_batch: list[int] = []
        current_tokens = 0

        for i, text in enumerate(texts):
            tokens = self.estimate_tokens(text)

            if (
                current_tokens + tokens > self.config.max_tokens_per_batch
                and current_batch
            ):
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0

            current_batch.append(i)
            current_tokens += tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        before_sleep=lambda rs: logger.warning(f"Retry {rs.attempt_number}/3"),
    )
    def _get_batch(self, texts: list[str]) -> list[list[float]]:
        """Get embeddings for batch with retry."""
        response = self.client.embeddings.create(
            model=self.config.model,
            input=texts,
            dimensions=self.config.dimensions,
        )
        return [d.embedding for d in response.data]

    def get_embeddings(
        self,
        texts: list[str],
        *,
        show_progress: bool = True,
    ) -> list[list[float]]:
        """Get embeddings for all texts with batching."""
        if not texts:
            return []

        batches = self.create_batches(texts)
        all_embeddings: list[list[float] | None] = [None] * len(texts)

        iterator = tqdm(batches, desc="Embeddings", disable=not show_progress)

        for batch_indices in iterator:
            batch_texts = [texts[i] for i in batch_indices]
            embeddings = self._get_batch(batch_texts)

            for idx, emb in zip(batch_indices, embeddings, strict=True):
                all_embeddings[idx] = emb

        return all_embeddings  # type: ignore[return-value]


# ═══════════════════════════════════════════════════════════════════════════════
# QDRANT MANAGER
# ═══════════════════════════════════════════════════════════════════════════════


class QdrantManager:
    """Manages Qdrant operations."""

    __slots__ = ("client", "config")

    NAMESPACE = uuid.UUID("a3bb189e-8bf9-3888-9912-ace4e6543002")

    def __init__(self, config: QdrantConfig) -> None:
        """Initialize Qdrant manager."""
        self.client = QdrantClient(host=config.host, port=config.port)
        self.config = config

    def ensure_collection(self, dimensions: int) -> bool:
        """Ensure collection exists, create if needed. Returns True if created."""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.config.collection for c in collections)

        if exists:
            return False

        if not self.config.auto_create:
            raise RuntimeError(f"Collection {self.config.collection} not found")

        distance_map = {
            "cosine": Distance.COSINE,
            "euclidean": Distance.EUCLID,
            "dot": Distance.DOT,
        }

        self.client.create_collection(
            collection_name=self.config.collection,
            vectors_config=VectorParams(
                size=dimensions,
                distance=distance_map.get(self.config.distance, Distance.COSINE),
            ),
        )
        logger.info(f"Created collection: {self.config.collection}")
        return True

    def get_points_count(self) -> int:
        """Return total points in collection."""
        info = self.client.get_collection(self.config.collection)
        return info.points_count

    def generate_point_id(self, source_file: str, chunk_index: int) -> str:
        """Generate deterministic UUID for point."""
        key = f"{source_file}:{chunk_index}"
        return str(uuid.uuid5(self.NAMESPACE, key))

    def delete_by_source_file(self, filename: str) -> int:
        """Delete all points from source file."""
        result = self.client.scroll(
            collection_name=self.config.collection,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_file", match=MatchValue(value=filename)
                    )
                ]
            ),
            limit=10000,
            with_payload=False,
        )
        count = len(result[0])

        if count > 0:
            self.client.delete(
                collection_name=self.config.collection,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source_file", match=MatchValue(value=filename)
                        )
                    ]
                ),
            )

        return count

    def get_indexed_source_files(self) -> set[str]:
        """Return unique source files in collection."""
        files: set[str] = set()
        offset = None

        while True:
            result = self.client.scroll(
                collection_name=self.config.collection,
                limit=100,
                offset=offset,
                with_payload=["source_file"],
            )
            points, offset = result

            for point in points:
                if point.payload and "source_file" in point.payload:
                    files.add(point.payload["source_file"])

            if offset is None:
                break

        return files

    def upsert_points(self, points: list[PointStruct]) -> None:
        """Upsert points to collection."""
        if points:
            self.client.upsert(collection_name=self.config.collection, points=points)

    def search(
        self,
        vector: list[float],
        limit: int = 5,
    ) -> list[tuple[float, dict[str, Any]]]:
        """Search for similar vectors."""
        results = self.client.query_points(
            collection_name=self.config.collection,
            query=vector,
            limit=limit,
        )
        return [(r.score, r.payload or {}) for r in results.points]


# ═══════════════════════════════════════════════════════════════════════════════
# RAG INDEXER
# ═══════════════════════════════════════════════════════════════════════════════


class RagIndexer:
    """Main indexer orchestrating all components."""

    def __init__(self, config: IndexerConfig) -> None:
        """Initialize indexer."""
        self.config = config
        self.embedder = EmbeddingManager(config.embeddings)
        self.qdrant = QdrantManager(config.qdrant)
        self.state = StateManager(
            Path(config.source.path) / config.indexing.state_file
        )

    def _get_files(self) -> list[Path]:
        """Get list of files to process."""
        source_path = Path(self.config.source.path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source path not found: {source_path}")

        files: list[Path] = []
        for pattern in self.config.source.patterns:
            files.extend(source_path.glob(pattern))

        return sorted(set(files))

    def _process_file(
        self,
        filepath: Path,
        *,
        dry_run: bool = False,
    ) -> tuple[int, list[str]]:
        """Process single file. Returns (chunks_count, warnings)."""
        logger.info(f"Processing: {filepath.name}")
        warnings: list[str] = []

        # Read and parse
        content = filepath.read_text(encoding=self.config.source.encoding)
        chunks = parse_document(content, self.config.parser)
        logger.debug(f"  Parsed chunks: {len(chunks)}")

        if not chunks:
            warnings.append(f"{filepath.name}: no chunks found")
            return 0, warnings

        # Process bilingual content and build embedding texts
        processed_chunks: list[dict[str, Any]] = []
        embedding_texts: list[str] = []

        for chunk in chunks:
            bilingual_data = extract_bilingual_content(
                chunk["content"], self.config.bilingual
            )
            embedding_text = build_embedding_text(
                chunk, bilingual_data, self.config.bilingual
            )

            # Validate chunk size
            char_count = len(embedding_text)
            if char_count < self.config.chunking.min_chars:
                warnings.append(
                    f"{filepath.name}:{chunk['index']} — too small ({char_count} chars), skipped"
                )
                continue

            if char_count > self.config.chunking.max_chars:
                warnings.append(
                    f"{filepath.name}:{chunk['index']} — large chunk ({char_count} chars)"
                )

            processed_chunks.append(
                {
                    **chunk,
                    **bilingual_data,
                    "embedding_text": embedding_text,
                    "char_count": char_count,
                }
            )
            embedding_texts.append(embedding_text)

        if not processed_chunks:
            return 0, warnings

        if dry_run:
            logger.info(f"  [DRY-RUN] Would upload: {len(processed_chunks)} chunks")
            return len(processed_chunks), warnings

        # Delete old points
        deleted = self.qdrant.delete_by_source_file(filepath.name)
        if deleted > 0:
            logger.debug(f"  Deleted old: {deleted}")

        # Get embeddings
        embeddings = self.embedder.get_embeddings(embedding_texts, show_progress=False)

        # Build points
        points: list[PointStruct] = []
        for chunk, embedding in zip(processed_chunks, embeddings, strict=True):
            point_id = self.qdrant.generate_point_id(filepath.name, chunk["index"])

            payload: dict[str, Any] = {
                "content": chunk.get("embedding_text", ""),
                "title": chunk.get("title", ""),
                "source_file": filepath.name,
                "chunk_index": chunk["index"],
                "char_count": chunk["char_count"],
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            }

            # Add bilingual fields
            if self.config.bilingual.enabled:
                for lang in self.config.bilingual.languages:
                    code = lang.code
                    payload[f"title_{code}"] = chunk.get(f"title_{code}", "")
                    payload[f"content_{code}"] = chunk.get(f"content_{code}", "")

            # Add custom metadata
            payload.update(self.config.metadata)

            points.append(PointStruct(id=point_id, vector=embedding, payload=payload))

        # Upsert
        self.qdrant.upsert_points(points)
        logger.info(f"  Uploaded: {len(points)} chunks")

        return len(points), warnings

    def index(
        self,
        *,
        dry_run: bool = False,
        force: bool = False,
        single_file: str | None = None,
    ) -> dict[str, Any]:
        """Run indexing. Returns stats."""
        # Ensure collection exists
        self.qdrant.ensure_collection(self.config.embeddings.dimensions)

        # Get files
        if single_file:
            files = [Path(self.config.source.path) / single_file]
            if not files[0].exists():
                raise FileNotFoundError(f"File not found: {files[0]}")
        else:
            files = self._get_files()

        if not files:
            logger.warning("No files to index")
            return {"files": 0, "chunks": 0, "warnings": []}

        # Filter by changes
        if not force and self.config.indexing.incremental:
            files_to_process = [f for f in files if self.state.needs_reindex(f)]
            skipped = len(files) - len(files_to_process)
            if skipped > 0:
                logger.info(f"Skipped unchanged: {skipped}")
        else:
            files_to_process = files

        if not files_to_process:
            logger.info("No files to reindex")
            return {
                "files": 0,
                "chunks": 0,
                "total_in_collection": self.qdrant.get_points_count(),
                "warnings": [],
            }

        # Process files
        stats: dict[str, Any] = {"files": 0, "chunks": 0, "warnings": []}

        for filepath in files_to_process:
            count, warnings = self._process_file(filepath, dry_run=dry_run)
            stats["files"] += 1
            stats["chunks"] += count
            stats["warnings"].extend(warnings)

            if not dry_run:
                self.state.update(filepath, count)

        # Save state
        if not dry_run:
            self.state.save()

        # Clean orphaned
        if not dry_run and self.config.indexing.clean_orphaned:
            self.clean_orphaned()

        stats["total_in_collection"] = self.qdrant.get_points_count()
        return stats

    def clean_orphaned(self) -> int:
        """Delete points from removed files."""
        existing_files = {f.name for f in self._get_files()}
        indexed_files = self.qdrant.get_indexed_source_files()
        orphaned = indexed_files - existing_files

        total_deleted = 0
        for filename in orphaned:
            count = self.qdrant.delete_by_source_file(filename)
            logger.info(f"Deleted orphaned: {filename} ({count})")
            total_deleted += count

        return total_deleted

    def stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        return {
            "collection": self.config.qdrant.collection,
            "points_count": self.qdrant.get_points_count(),
            "indexed_files": list(self.qdrant.get_indexed_source_files()),
        }

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for similar content."""
        embeddings = self.embedder.get_embeddings([query], show_progress=False)
        results = self.qdrant.search(embeddings[0], limit=limit)

        output: list[dict[str, Any]] = []
        for score, p in results:
            # Try to get title: first plain, then bilingual
            title = p.get("title", "") or p.get("title_ru", "") or p.get("title_uz", "")
            output.append({
                "score": score,
                "title": title,
                "source_file": p.get("source_file", ""),
            })
        return output


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def cmd_index(args: argparse.Namespace, config: IndexerConfig) -> None:
    """Index command."""
    indexer = RagIndexer(config)
    stats = indexer.index(
        dry_run=args.dry_run,
        force=args.force,
        single_file=args.file,
    )

    logger.info("=" * 50)
    if args.dry_run:
        logger.info("DRY-RUN completed")
    else:
        logger.info("Indexing completed")
    logger.info(f"  Files: {stats['files']}")
    logger.info(f"  Chunks: {stats['chunks']}")
    logger.info(f"  Total in collection: {stats.get('total_in_collection', 'N/A')}")
    if stats["warnings"]:
        logger.info(f"  Warnings: {len(stats['warnings'])}")


def cmd_stats(args: argparse.Namespace, config: IndexerConfig) -> None:
    """Stats command."""
    indexer = RagIndexer(config)
    stats = indexer.stats()
    print(f"Collection: {stats['collection']}")
    print(f"Points: {stats['points_count']}")
    print(f"Files: {len(stats['indexed_files'])}")
    for f in stats["indexed_files"]:
        print(f"  - {f}")


def cmd_search(args: argparse.Namespace, config: IndexerConfig) -> None:
    """Search command."""
    indexer = RagIndexer(config)
    results = indexer.search(args.query, limit=args.limit)
    print(f"Query: {args.query}\n")
    for r in results:
        print(f"  {r['score']:.3f} | {r['source_file']} | {r['title'][:50]}")


def cmd_clean(args: argparse.Namespace, config: IndexerConfig) -> None:
    """Clean orphaned points."""
    indexer = RagIndexer(config)
    deleted = indexer.clean_orphaned()
    print(f"Deleted orphaned points: {deleted}")


def cmd_validate(args: argparse.Namespace, config: IndexerConfig) -> None:
    """Validate configuration."""
    errors = config.validate()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("Configuration is valid")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Universal RAG Indexer for Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config", "-c",
        default="rag_config.yaml",
        help="Config file (default: rag_config.yaml)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # index
    p_index = subparsers.add_parser("index", help="Index documents")
    p_index.add_argument("--dry-run", "-n", action="store_true", help="Show plan only")
    p_index.add_argument("--force", "-f", action="store_true", help="Force reindex all")
    p_index.add_argument("--file", help="Index single file")

    # stats
    subparsers.add_parser("stats", help="Show collection statistics")

    # search
    p_search = subparsers.add_parser("search", help="Search documents")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", "-l", type=int, default=5, help="Results limit")

    # clean
    subparsers.add_parser("clean", help="Clean orphaned points")

    # validate
    subparsers.add_parser("validate", help="Validate configuration")

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        config = IndexerConfig.from_yaml(config_path)
        logger.debug(f"Loaded config: {config_path}")
    else:
        if args.command and args.command != "validate":
            logger.warning(f"Config not found: {config_path}, using defaults")
        config = IndexerConfig()

    # Route command
    commands = {
        "index": cmd_index,
        "stats": cmd_stats,
        "search": cmd_search,
        "clean": cmd_clean,
        "validate": cmd_validate,
    }

    if args.command:
        commands[args.command](args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
