"""Copy Qdrant collection data from production to local."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


# Configuration
PROD_HOST = "localhost"  # Via SSH tunnel
PROD_PORT = 16333  # Tunneled port
LOCAL_HOST = "localhost"
LOCAL_PORT = 6333
COLLECTION_NAME = "biotact_knowledge_v3"
VECTOR_SIZE = 3072  # text-embedding-3-large


def copy_collection():
    """Copy collection from prod to local Qdrant."""
    print("=" * 60)
    print("Copying Qdrant collection from production")
    print("=" * 60)

    # Connect to production (via SSH tunnel)
    print(f"\n1. Connecting to production Qdrant ({PROD_HOST}:{PROD_PORT})...")
    try:
        prod_client = QdrantClient(host=PROD_HOST, port=PROD_PORT)
        prod_collections = prod_client.get_collections().collections
        print(f"   Connected. Collections: {[c.name for c in prod_collections]}")
    except Exception as e:
        print(f"   ERROR: Cannot connect to production Qdrant: {e}")
        print(f"\n   Make sure SSH tunnel is running:")
        print(f"   ssh -L {PROD_PORT}:localhost:6333 biotact-core")
        return

    # Connect to local
    print(f"\n2. Connecting to local Qdrant ({LOCAL_HOST}:{LOCAL_PORT})...")
    local_client = QdrantClient(host=LOCAL_HOST, port=LOCAL_PORT)
    local_collections = local_client.get_collections().collections
    print(f"   Connected. Collections: {[c.name for c in local_collections]}")

    # Check prod collection exists
    if COLLECTION_NAME not in [c.name for c in prod_collections]:
        print(f"\n   ERROR: Collection '{COLLECTION_NAME}' not found in production")
        return

    # Get prod collection info
    prod_info = prod_client.get_collection(COLLECTION_NAME)
    prod_points = prod_info.points_count
    print(f"\n3. Production collection info:")
    print(f"   Name: {COLLECTION_NAME}")
    print(f"   Points: {prod_points}")

    # Create local collection if needed
    if COLLECTION_NAME in [c.name for c in local_collections]:
        print(f"\n4. Local collection exists, deleting...")
        local_client.delete_collection(COLLECTION_NAME)

    print(f"\n4. Creating local collection...")
    local_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    print(f"   Created collection with {VECTOR_SIZE} dimensions")

    # Copy points in batches
    print(f"\n5. Copying points...")
    batch_size = 100
    offset = None
    total_copied = 0

    while True:
        # Scroll through prod points
        points, next_offset = prod_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        if not points:
            break

        # Convert to PointStruct for upsert
        point_structs = [
            PointStruct(
                id=point.id,
                vector=point.vector,
                payload=point.payload,
            )
            for point in points
        ]

        # Upsert to local
        local_client.upsert(
            collection_name=COLLECTION_NAME,
            points=point_structs,
        )

        total_copied += len(points)
        print(f"   Copied {total_copied} points...")

        if next_offset is None:
            break
        offset = next_offset

    # Verify
    print(f"\n6. Verifying...")
    local_info = local_client.get_collection(COLLECTION_NAME)
    local_points = local_info.points_count
    print(f"   Local points: {local_points}")

    if local_points == prod_points:
        print(f"\n{'=' * 60}")
        print(f"SUCCESS! Copied {total_copied} points")
        print(f"{'=' * 60}")
    else:
        print(f"\n   WARNING: Point counts don't match!")
        print(f"   Prod: {prod_points}, Local: {local_points}")


if __name__ == "__main__":
    copy_collection()
