"""Index nutrition library PDFs into Qdrant collection 'nutrition_library'.

Reads extracted .txt files, chunks with overlap, embeds via OpenAI,
uploads to Qdrant. Designed for English-language reference books.
"""

import os
import re
import sys
import uuid
import time

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# --- Config ---
TEXT_DIR = "/app/nutrition_texts"  # Mounted or copied into container
QDRANT_HOST = "biotact-qdrant"
QDRANT_PORT = 6333
COLLECTION = "nutrition_library"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MIN_CHARS = 100
BATCH_EMBED = 5
BATCH_UPSERT = 100


def chunk_text(text, chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks at paragraph/sentence boundaries."""
    # Normalize whitespace
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
            # Keep overlap from end of current chunk
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

    # Handle single paragraphs > chunk_size
    final = []
    for chunk in chunks:
        if len(chunk) <= chunk_size:
            final.append(chunk)
        else:
            # Split at sentence boundaries
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


def process_file(filepath):
    """Read text file and split into chunks with metadata."""
    filename = os.path.basename(filepath)
    book_title = filename.replace(".txt", "").replace("_", " ")

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    if len(text) < MIN_CHARS:
        return []

    chunks = chunk_text(text)
    results = []
    for i, chunk in enumerate(chunks):
        if len(chunk) < MIN_CHARS:
            continue
        results.append({
            "content": chunk,
            "source_file": filename,
            "book_title": book_title,
            "chunk_index": i,
            "char_count": len(chunk),
        })
    return results


MAX_TOKENS_APPROX = 7000  # Safety margin under 8192 limit
MAX_CHARS_PER_TEXT = 6000  # ~7000 tokens max


def batch_embed(texts, oai_client):
    """Embed texts in batches, truncating oversized texts."""
    # Truncate any text that might exceed token limit
    safe_texts = []
    for t in texts:
        if len(t) > MAX_CHARS_PER_TEXT:
            t = t[:MAX_CHARS_PER_TEXT]
        safe_texts.append(t)

    all_vectors = []
    for i in range(0, len(safe_texts), BATCH_EMBED):
        batch = safe_texts[i:i + BATCH_EMBED]
        resp = oai_client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
        vectors = [d.embedding for d in resp.data]
        all_vectors.extend(vectors)
        if (i + BATCH_EMBED) % 100 < BATCH_EMBED:
            print(f"  Embedded {min(i + BATCH_EMBED, len(safe_texts))}/{len(safe_texts)}")
    return all_vectors


def main():
    # Check text dir
    if not os.path.isdir(TEXT_DIR):
        print(f"ERROR: {TEXT_DIR} not found")
        sys.exit(1)

    # Connect
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    oai_client = openai.OpenAI()

    # Create collection if not exists
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

    # Parse all files
    print("\n=== Step 1: Parsing files ===")
    txt_files = sorted([
        os.path.join(TEXT_DIR, f)
        for f in os.listdir(TEXT_DIR)
        if f.endswith(".txt")
    ])
    print(f"  Found {len(txt_files)} files")

    all_chunks = []
    for filepath in txt_files:
        chunks = process_file(filepath)
        fname = os.path.basename(filepath)
        print(f"  {fname}: {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\n  Total chunks: {len(all_chunks)}")

    if not all_chunks:
        print("No chunks to index.")
        return

    # Embed
    print("\n=== Step 2: Embedding ===")
    texts = [c["content"] for c in all_chunks]
    t0 = time.time()
    vectors = batch_embed(texts, oai_client)
    print(f"  Done in {time.time() - t0:.1f}s")

    # Upload
    print("\n=== Step 3: Uploading to Qdrant ===")
    points = []
    for chunk, vector in zip(all_chunks, vectors):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=chunk,
        ))

    for i in range(0, len(points), BATCH_UPSERT):
        batch = points[i:i + BATCH_UPSERT]
        qdrant.upsert(collection_name=COLLECTION, points=batch)
        print(f"  Uploaded {min(i + BATCH_UPSERT, len(points))}/{len(points)}")

    # Verify
    print("\n=== Step 4: Verification ===")
    info = qdrant.get_collection(COLLECTION)
    print(f"  Points: {info.points_count}")
    print(f"\n=== DONE ===")


if __name__ == "__main__":
    main()
