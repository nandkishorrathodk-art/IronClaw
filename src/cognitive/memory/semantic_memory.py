"""
Semantic memory system for conversation context retrieval
"""
from typing import List, Optional, Dict, Any, Tuple
from pydantic import BaseModel
from datetime import datetime

from src.cognitive.memory.vector_store import VectorStore, get_vector_store
from src.cognitive.memory.embeddings import EmbeddingService, get_embedding_service
from src.cognitive.llm.types import Message, MessageRole
from src.utils.logging import get_logger

logger = get_logger(__name__)


class MemoryMatch(BaseModel):
    """A match from semantic memory search."""
    text: str
    score: float
    conversation_id: Optional[int] = None
    message_id: Optional[int] = None
    created_at: Optional[str] = None
    role: Optional[str] = None


class MemoryContext(BaseModel):
    """Retrieved memory context for a query."""
    query: str
    matches: List[MemoryMatch]
    total_matches: int
    context_summary: str


class SemanticMemory:
    """
    Semantic memory system for intelligent context retrieval.
    
    Features:
    - Store conversations with vector embeddings
    - Retrieve relevant past context (top-k similarity)
    - Re-rank results by relevance
    - Automatic summarization of context
    - Deduplication
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        """
        Initialize semantic memory.
        
        Args:
            vector_store: Vector store instance
            embedding_service: Embedding service instance
        """
        self.vector_store = vector_store or get_vector_store()
        self.embedding_service = embedding_service or get_embedding_service()
    
    async def store_message(
        self,
        message: Message,
        conversation_id: int,
        message_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> str:
        """
        Store a message in semantic memory.
        
        Args:
            message: Message to store
            conversation_id: Conversation ID
            message_id: Message ID (optional)
            user_id: User ID (optional)
            
        Returns:
            Vector store point ID
        """
        # Generate embedding
        embedding = await self.embedding_service.embed_text(message.content)
        
        # Prepare metadata
        metadata = {
            "conversation_id": conversation_id,
            "role": message.role.value,
            "created_at": datetime.utcnow().isoformat(),
        }
        
        if message_id:
            metadata["message_id"] = message_id
        if user_id:
            metadata["user_id"] = user_id
        
        # Store in vector database
        point_id = self.vector_store.add_embedding(
            embedding=embedding,
            text=message.content,
            metadata=metadata
        )
        
        logger.debug(f"Stored message in memory: conv={conversation_id}, id={point_id}")
        return point_id
    
    async def store_messages_batch(
        self,
        messages: List[Message],
        conversation_id: int,
        message_ids: Optional[List[int]] = None,
        user_id: Optional[int] = None
    ) -> List[str]:
        """
        Store multiple messages in batch.
        
        Args:
            messages: Messages to store
            conversation_id: Conversation ID
            message_ids: Optional message IDs
            user_id: User ID (optional)
            
        Returns:
            List of vector store point IDs
        """
        # Generate embeddings in batch
        texts = [msg.content for msg in messages]
        embeddings = await self.embedding_service.embed_batch(texts)
        
        # Prepare metadata
        metadatas = []
        for i, message in enumerate(messages):
            metadata = {
                "conversation_id": conversation_id,
                "role": message.role.value,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            if message_ids and i < len(message_ids):
                metadata["message_id"] = message_ids[i]
            if user_id:
                metadata["user_id"] = user_id
            
            metadatas.append(metadata)
        
        # Store in vector database
        point_ids = self.vector_store.add_batch(
            embeddings=embeddings,
            texts=texts,
            metadatas=metadatas
        )
        
        logger.info(f"Stored {len(messages)} messages in memory (conv={conversation_id})")
        return point_ids
    
    async def retrieve_context(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
        user_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
        exclude_conversation: Optional[int] = None
    ) -> MemoryContext:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: Query text
            limit: Maximum matches to return (default: 5)
            score_threshold: Minimum similarity score (default: 0.7)
            user_id: Filter by user ID (optional)
            conversation_id: Filter by conversation ID (optional)
            exclude_conversation: Exclude this conversation ID (optional)
            
        Returns:
            MemoryContext with relevant matches
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_text(query)
        
        # Build filter
        filter_dict = {}
        if user_id:
            filter_dict["user_id"] = user_id
        if conversation_id:
            filter_dict["conversation_id"] = conversation_id
        
        # Search vector store
        results = self.vector_store.search(
            query_embedding=query_embedding,
            limit=limit * 2 if exclude_conversation else limit,  # Get extra for filtering
            score_threshold=score_threshold,
            filter_dict=filter_dict if filter_dict else None
        )
        
        # Parse results
        matches = []
        for text, score, metadata in results:
            # Skip excluded conversation
            if exclude_conversation and metadata.get("conversation_id") == exclude_conversation:
                continue
            
            match = MemoryMatch(
                text=text,
                score=score,
                conversation_id=metadata.get("conversation_id"),
                message_id=metadata.get("message_id"),
                created_at=metadata.get("created_at"),
                role=metadata.get("role")
            )
            matches.append(match)
            
            if len(matches) >= limit:
                break
        
        # Re-rank results (optional: could use cross-encoder here)
        matches = self._rerank_results(query, matches)
        
        # Generate context summary
        context_summary = self._summarize_context(matches)
        
        context = MemoryContext(
            query=query,
            matches=matches,
            total_matches=len(matches),
            context_summary=context_summary
        )
        
        logger.info(f"Retrieved {len(matches)} relevant memories for query: {query[:50]}...")
        return context
    
    def _rerank_results(
        self,
        query: str,
        matches: List[MemoryMatch]
    ) -> List[MemoryMatch]:
        """
        Re-rank results by relevance.
        
        Currently uses simple score-based ranking.
        Could be enhanced with cross-encoder model.
        
        Args:
            query: Original query
            matches: Initial matches
            
        Returns:
            Re-ranked matches
        """
        # For now, just sort by score (already done by vector store)
        # In future, could use cross-encoder for better re-ranking
        return sorted(matches, key=lambda m: m.score, reverse=True)
    
    def _summarize_context(self, matches: List[MemoryMatch]) -> str:
        """
        Create a summary of retrieved context.
        
        Args:
            matches: Memory matches
            
        Returns:
            Context summary string
        """
        if not matches:
            return "No relevant context found."
        
        # Group by conversation
        convs = {}
        for match in matches:
            conv_id = match.conversation_id or "unknown"
            if conv_id not in convs:
                convs[conv_id] = []
            convs[conv_id].append(match)
        
        # Build summary
        summary_parts = []
        summary_parts.append(f"Found {len(matches)} relevant memories from {len(convs)} conversations:")
        
        for conv_id, conv_matches in convs.items():
            avg_score = sum(m.score for m in conv_matches) / len(conv_matches)
            summary_parts.append(
                f"- Conversation {conv_id}: {len(conv_matches)} matches (avg score: {avg_score:.2f})"
            )
        
        return "\n".join(summary_parts)
    
    def inject_context_into_messages(
        self,
        messages: List[Message],
        context: MemoryContext,
        max_context_items: int = 3
    ) -> List[Message]:
        """
        Inject retrieved context into message history.
        
        Args:
            messages: Current conversation messages
            context: Retrieved memory context
            max_context_items: Maximum context items to inject (default: 3)
            
        Returns:
            Messages with injected context
        """
        if not context.matches:
            return messages
        
        # Build context injection message
        context_parts = ["Relevant context from past conversations:"]
        
        for i, match in enumerate(context.matches[:max_context_items]):
            context_parts.append(
                f"{i+1}. [{match.role or 'unknown'}] {match.text[:200]}... "
                f"(relevance: {match.score:.2f})"
            )
        
        context_message = Message(
            role=MessageRole.SYSTEM,
            content="\n".join(context_parts)
        )
        
        # Inject after system message (if exists) but before conversation
        if messages and messages[0].role == MessageRole.SYSTEM:
            return [messages[0], context_message] + messages[1:]
        else:
            return [context_message] + messages
    
    async def delete_conversation_memories(self, conversation_id: int) -> int:
        """
        Delete all memories for a conversation.
        
        Args:
            conversation_id: Conversation ID
            
        Returns:
            Number of memories deleted
        """
        deleted = self.vector_store.delete_by_metadata(
            {"conversation_id": conversation_id}
        )
        logger.info(f"Deleted {deleted} memories for conversation {conversation_id}")
        return deleted
    
    async def delete_user_memories(self, user_id: int) -> int:
        """
        Delete all memories for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Number of memories deleted
        """
        deleted = self.vector_store.delete_by_metadata(
            {"user_id": user_id}
        )
        logger.info(f"Deleted {deleted} memories for user {user_id}")
        return deleted


# Global instance
_semantic_memory: Optional[SemanticMemory] = None


def get_semantic_memory() -> SemanticMemory:
    """Get global semantic memory instance."""
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
    return _semantic_memory
