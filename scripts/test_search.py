#!/usr/bin/env python3
"""Test search in knowledge-evolution collection"""
import os
from openai import OpenAI
from qdrant_client import QdrantClient

openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
qdrant = QdrantClient(host=os.environ.get("QDRANT_HOST", "biotact-qdrant"), port=6333)

queries = [
    ("RU", "сколько стоит магний"),
    ("UZ", "magniy narxi qancha"),
    ("RU", "можно ли магний при беременности"),
    ("UZ", "homiladorlikda magniy"),
    ("RU", "судороги в ногах"),
    ("UZ", "oyoq tortishishi"),
    ("RU", "доставка по ташкенту"),
]

for lang, query in queries:
    emb = openai_client.embeddings.create(
        model="text-embedding-3-large",
        input=query,
        dimensions=3072
    ).data[0].embedding

    results = qdrant.query_points(
        collection_name="knowledge-evolution",
        query=emb,
        limit=2
    ).points

    print(f"\n{'='*60}")
    print(f"[{lang}] {query}")
    print(f"{'='*60}")
    for r in results:
        name = r.payload.get("name_ru", "")[:50]
        print(f"  Score: {r.score:.3f} | {name}")
