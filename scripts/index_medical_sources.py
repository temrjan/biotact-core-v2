"""Index medical sources into Qdrant collection 'medical_sources'.

Reads curated .txt files with YAML frontmatter from specialties/,
chunks TITLE+AUTHORS+JOURNAL+ABSTRACT, embeds via OpenAI,
uploads to Qdrant with full metadata payload.
"""

import os
import re
import sys
import time
import uuid

import openai

# Deterministic namespace for idempotent upserts — same file+chunk always → same UUID
_NAMESPACE = uuid.UUID("7c9e6679-7425-40de-944b-e07fc1f90ae7")
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# --- Config ---
TEXT_DIR = "/app/medical_sources"
QDRANT_HOST = "biotact-qdrant"
QDRANT_PORT = 6333
COLLECTION = "medical_sources"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MIN_CHARS = 80
MAX_CHARS_PER_TEXT = 6000
BATCH_EMBED = 5
BATCH_UPSERT = 100


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter. Returns (metadata, body)."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---\n", 3)
    if end == -1:
        return {}, text

    yaml_str = text[4:end]
    body = text[end + 5:].strip()

    meta: dict = {}
    for line in yaml_str.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()

        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                meta[key] = [v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()]
        elif val.lower() == "true":
            meta[key] = True
        elif val.lower() == "false":
            meta[key] = False
        elif val.isdigit():
            meta[key] = int(val)
        elif val.startswith('"') and val.endswith('"'):
            meta[key] = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            meta[key] = val[1:-1]
        else:
            meta[key] = val

    return meta, body


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks at paragraph/sentence boundaries."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 > chunk_size and current:
            chunks.append(current.strip())
            if overlap > 0:
                words = current.split()
                overlap_text = ""
                for w in reversed(words):
                    if len(overlap_text) + len(w) + 1 > overlap:
                        break
                    overlap_text = w + " " + overlap_text
                current = overlap_text.strip() + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    # Handle chunks still > chunk_size (split at sentences)
    final = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            final.append(chunk)
        else:
            sentences = re.split(r"(?<=[.!?])\s+", chunk)
            sub = ""
            for sent in sentences:
                if len(sub) + len(sent) + 1 > chunk_size and sub:
                    final.append(sub.strip())
                    sub = sent
                else:
                    sub = sub + " " + sent if sub else sent
            if sub.strip():
                final.append(sub.strip())

    return final


def process_file(filepath: str) -> list[dict]:
    """Parse frontmatter + body, return chunks with metadata payload."""
    filename = os.path.basename(filepath)

    with open(filepath, encoding="utf-8") as f:
        raw = f.read()

    meta, body = parse_frontmatter(raw)

    if len(body) < MIN_CHARS:
        print(f"  SKIP {filename}: body too short ({len(body)} chars)")
        return []

    chunks = chunk_text(body)
    results = []
    for i, chunk in enumerate(chunks):
        if len(chunk) < MIN_CHARS:
            continue
        payload = {
            "content": chunk[:MAX_CHARS_PER_TEXT],
            "source_file": filename,
            "chunk_index": i,
            "source": meta.get("source", "PubMed"),
            "source_url": meta.get("source_url", ""),
            "source_tier": meta.get("source_tier", 1),
            "specialty": meta.get("specialty", ""),
            "age_group": meta.get("age_group", []),
            "nutrients": meta.get("nutrients", []),
            "strains": meta.get("strains", []),
            "symptoms": meta.get("symptoms", []),
            "year": meta.get("year", 0),
            "doi": meta.get("doi", ""),
            "pmc": meta.get("pmc", ""),
            "has_full_text": meta.get("has_full_text", False),
            "language": meta.get("language", "en"),
            "added_at": meta.get("added_at", ""),
        }
        results.append(payload)

    return results


def batch_embed(texts: list[str], oai_client: openai.OpenAI) -> list[list[float]]:
    """Embed texts in batches."""
    safe_texts = [t[:MAX_CHARS_PER_TEXT] for t in texts]
    all_vectors: list[list[float]] = []

    for i in range(0, len(safe_texts), BATCH_EMBED):
        batch = safe_texts[i : i + BATCH_EMBED]
        resp = oai_client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
        all_vectors.extend(d.embedding for d in resp.data)
        done = min(i + BATCH_EMBED, len(safe_texts))
        if done % 50 < BATCH_EMBED or done == len(safe_texts):
            print(f"  Embedded {done}/{len(safe_texts)}")

    return all_vectors


def main() -> None:
    if not os.path.isdir(TEXT_DIR):
        print(f"ERROR: {TEXT_DIR} not found")
        sys.exit(1)

    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    oai_client = openai.OpenAI()

    collections = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION not in collections:
        print(f"Creating collection '{COLLECTION}'...")
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIMS, distance=Distance.COSINE),
        )
    else:
        info = qdrant.get_collection(COLLECTION)
        print(f"Collection '{COLLECTION}': {info.points_count} existing points")

    print("\n=== Step 1: Parsing files ===")
    txt_files = sorted(
        os.path.join(TEXT_DIR, f)
        for f in os.listdir(TEXT_DIR)
        if f.endswith(".txt")
    )
    print(f"  Found {len(txt_files)} files")

    all_chunks: list[dict] = []
    for filepath in txt_files:
        chunks = process_file(filepath)
        print(f"  {os.path.basename(filepath)}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\n  Total chunks: {len(all_chunks)}")

    if not all_chunks:
        print("No chunks to index.")
        return

    print("\n=== Step 2: Embedding ===")
    texts = [c["content"] for c in all_chunks]
    t0 = time.time()
    vectors = batch_embed(texts, oai_client)
    print(f"  Done in {time.time() - t0:.1f}s")

    print("\n=== Step 3: Uploading to Qdrant ===")
    points = [
        PointStruct(
            id=str(uuid.uuid5(_NAMESPACE, f"{chunk['source_file']}:{chunk['chunk_index']}")),
            vector=vector,
            payload=chunk,
        )
        for chunk, vector in zip(all_chunks, vectors)
    ]

    for i in range(0, len(points), BATCH_UPSERT):
        batch = points[i : i + BATCH_UPSERT]
        qdrant.upsert(collection_name=COLLECTION, points=batch)
        print(f"  Uploaded {min(i + BATCH_UPSERT, len(points))}/{len(points)}")

    print("\n=== Step 4: Verification ===")
    info = qdrant.get_collection(COLLECTION)
    print(f"  Points in '{COLLECTION}': {info.points_count}")
    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
