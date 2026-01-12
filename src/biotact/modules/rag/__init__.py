"""RAG-based modules for BIOTACT.

RAG modules search the Qdrant knowledge base and generate
responses based on retrieved context.
"""

from biotact.modules.rag.base import BaseRAGService

__all__ = ["BaseRAGService"]
