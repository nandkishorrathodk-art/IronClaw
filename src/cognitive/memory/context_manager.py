"""
Long-context conversation management
Handles sliding windows, summarization, and context pruning
"""
from typing import List, Optional, Tuple
from pydantic import BaseModel

from src.cognitive.llm.types import Message, MessageRole, ChatRequest, TaskType
from src.cognitive.llm.router import AIRouter
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ConversationWindow(BaseModel):
    """A window of conversation messages."""
    messages: List[Message]
    token_count: int
    is_summarized: bool = False
    summary: Optional[str] = None


class ContextManager:
    """
    Manage long conversation contexts.
    
    Features:
    - Sliding window for recent messages
    - Automatic summarization of old messages (10:1 compression)
    - Intelligent context pruning
    - Token counting and budget management
    """
    
    def __init__(
        self,
        max_tokens: int = 16000,
        recent_window_size: int = 10,
        router: Optional[AIRouter] = None
    ):
        """
        Initialize context manager.
        
        Args:
            max_tokens: Maximum tokens to keep in context (default: 16000)
            recent_window_size: Number of recent messages to always keep (default: 10)
            router: AI router for summarization
        """
        self.max_tokens = max_tokens
        self.recent_window_size = recent_window_size
        self.router = router or AIRouter()
    
    def manage_context(
        self,
        messages: List[Message],
        preserve_system: bool = True
    ) -> List[Message]:
        """
        Manage conversation context to fit within token budget.
        
        Args:
            messages: Full conversation history
            preserve_system: Always keep system message (default: True)
            
        Returns:
            Pruned messages that fit within token budget
        """
        if not messages:
            return []
        
        # Count tokens
        total_tokens = self._count_tokens(messages)
        
        # If within budget, return as-is
        if total_tokens <= self.max_tokens:
            return messages
        
        logger.info(f"Context exceeds budget ({total_tokens} > {self.max_tokens}), pruning...")
        
        # Split into system, old, and recent
        system_msgs = []
        old_msgs = []
        recent_msgs = []
        
        # Extract system message
        if preserve_system and messages[0].role == MessageRole.SYSTEM:
            system_msgs = [messages[0]]
            remaining = messages[1:]
        else:
            remaining = messages
        
        # Split old and recent
        if len(remaining) > self.recent_window_size:
            old_msgs = remaining[:-self.recent_window_size]
            recent_msgs = remaining[-self.recent_window_size:]
        else:
            recent_msgs = remaining
        
        # Build pruned context
        pruned = system_msgs.copy()
        
        # Add summarized old messages (if any)
        if old_msgs:
            # For now, just drop old messages
            # TODO: Implement async summarization
            logger.debug(f"Dropped {len(old_msgs)} old messages")
        
        # Add recent messages
        pruned.extend(recent_msgs)
        
        # Verify we're within budget
        pruned_tokens = self._count_tokens(pruned)
        logger.info(f"Pruned context: {len(messages)} -> {len(pruned)} messages, {total_tokens} -> {pruned_tokens} tokens")
        
        return pruned
    
    async def manage_context_with_summary(
        self,
        messages: List[Message],
        preserve_system: bool = True
    ) -> List[Message]:
        """
        Manage conversation context with summarization of old messages.
        
        Args:
            messages: Full conversation history
            preserve_system: Always keep system message (default: True)
            
        Returns:
            Messages with summarized context
        """
        if not messages:
            return []
        
        # Count tokens
        total_tokens = self._count_tokens(messages)
        
        # If within budget, return as-is
        if total_tokens <= self.max_tokens:
            return messages
        
        logger.info(f"Context exceeds budget ({total_tokens} > {self.max_tokens}), summarizing...")
        
        # Split into system, old, and recent
        system_msgs = []
        old_msgs = []
        recent_msgs = []
        
        # Extract system message
        if preserve_system and messages[0].role == MessageRole.SYSTEM:
            system_msgs = [messages[0]]
            remaining = messages[1:]
        else:
            remaining = messages
        
        # Split old and recent
        if len(remaining) > self.recent_window_size:
            old_msgs = remaining[:-self.recent_window_size]
            recent_msgs = remaining[-self.recent_window_size:]
        else:
            recent_msgs = remaining
        
        # Summarize old messages
        summary_msg = None
        if old_msgs:
            summary = await self._summarize_messages(old_msgs)
            summary_msg = Message(
                role=MessageRole.SYSTEM,
                content=f"Previous conversation summary ({len(old_msgs)} messages):\n{summary}"
            )
        
        # Build context with summary
        pruned = system_msgs.copy()
        if summary_msg:
            pruned.append(summary_msg)
        pruned.extend(recent_msgs)
        
        # Verify we're within budget
        pruned_tokens = self._count_tokens(pruned)
        logger.info(
            f"Summarized context: {len(messages)} -> {len(pruned)} messages "
            f"({total_tokens} -> {pruned_tokens} tokens, "
            f"{(1 - pruned_tokens/total_tokens)*100:.1f}% compression)"
        )
        
        return pruned
    
    async def _summarize_messages(self, messages: List[Message]) -> str:
        """
        Summarize a list of messages using AI.
        
        Target: 10:1 compression ratio
        
        Args:
            messages: Messages to summarize
            
        Returns:
            Summary text
        """
        # Build conversation text
        conversation_text = "\n".join([
            f"{msg.role.value}: {msg.content}"
            for msg in messages
        ])
        
        # Create summarization prompt
        summary_prompt = (
            "Summarize the following conversation concisely. "
            "Focus on key points, decisions, and important information. "
            "Aim for a 10:1 compression ratio.\n\n"
            f"Conversation:\n{conversation_text}\n\n"
            "Summary:"
        )
        
        # Generate summary
        try:
            request = ChatRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are an expert at summarizing conversations."),
                    Message(role=MessageRole.USER, content=summary_prompt)
                ],
                task_type=TaskType.GENERAL,
                temperature=0.3,  # Low temperature for focused summarization
                max_tokens=500  # Limit summary length
            )
            
            response = await self.router.chat(request)
            summary = response.content.strip()
            
            logger.debug(f"Summarized {len(messages)} messages into {len(summary)} chars")
            return summary
        
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback: simple concatenation with truncation
            return conversation_text[:500] + "..."
    
    def _count_tokens(self, messages: List[Message]) -> int:
        """
        Estimate token count for messages.
        
        Uses rough approximation: 1 token ≈ 4 characters
        
        Args:
            messages: Messages to count
            
        Returns:
            Estimated token count
        """
        total_chars = sum(len(msg.content) for msg in messages)
        # Add overhead for role and formatting (~10 tokens per message)
        overhead = len(messages) * 10
        return (total_chars // 4) + overhead
    
    def prune_by_relevance(
        self,
        messages: List[Message],
        current_query: str,
        keep_count: int
    ) -> List[Message]:
        """
        Intelligently prune messages by relevance to current query.
        
        Args:
            messages: Messages to prune
            current_query: Current user query
            keep_count: Number of messages to keep
            
        Returns:
            Most relevant messages
        """
        if len(messages) <= keep_count:
            return messages
        
        # Simple heuristic: keep messages that share keywords with query
        query_keywords = set(current_query.lower().split())
        
        # Score each message by keyword overlap
        scored_messages = []
        for msg in messages:
            msg_keywords = set(msg.content.lower().split())
            overlap = len(query_keywords & msg_keywords)
            scored_messages.append((overlap, msg))
        
        # Sort by score and take top-k
        scored_messages.sort(key=lambda x: x[0], reverse=True)
        pruned = [msg for _, msg in scored_messages[:keep_count]]
        
        # Restore chronological order
        pruned_set = set(id(msg) for msg in pruned)
        chronological = [msg for msg in messages if id(msg) in pruned_set]
        
        logger.debug(f"Pruned by relevance: {len(messages)} -> {len(chronological)} messages")
        return chronological


# Global instance
_context_manager: Optional[ContextManager] = None


def get_context_manager(max_tokens: int = 16000) -> ContextManager:
    """Get global context manager instance."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(max_tokens=max_tokens)
    return _context_manager
