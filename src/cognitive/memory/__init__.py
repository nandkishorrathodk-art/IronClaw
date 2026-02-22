"""
Memory system for semantic search and context management
"""
from src.cognitive.memory.vector_store import VectorStore, get_vector_store
from src.cognitive.memory.embeddings import EmbeddingService, get_embedding_service
from src.cognitive.memory.semantic_memory import (
    SemanticMemory,
    MemoryMatch,
    MemoryContext,
    get_semantic_memory,
)
from src.cognitive.memory.context_manager import ContextManager, get_context_manager

__all__ = [
    "VectorStore",
    "get_vector_store",
    "EmbeddingService",
    "get_embedding_service",
    "SemanticMemory",
    "MemoryMatch",
    "MemoryContext",
    "get_semantic_memory",
    "ContextManager",
    "get_context_manager",
]
