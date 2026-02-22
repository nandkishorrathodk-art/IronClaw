"""
LLM Response Streaming
Stream AI responses token-by-token in real-time via WebSocket.
"""
import uuid
from typing import AsyncIterator, Optional
from datetime import datetime

from src.utils.logging import get_logger
from src.realtime.events import WSEvent, WSEventType, StreamToken
from src.realtime.manager import connection_manager

logger = get_logger(__name__)


class LLMStreamer:
    """
    Stream LLM responses to WebSocket clients.
    
    Usage:
        streamer = LLMStreamer(
            conversation_id=123,
            user_id=456,
            session_id="session-uuid"
        )
        
        async for token in ai_provider.stream_response(prompt):
            await streamer.send_token(token)
        
        await streamer.finish()
    """
    
    def __init__(
        self,
        conversation_id: int,
        user_id: int,
        session_id: Optional[str] = None,
        message_id: Optional[int] = None,
    ):
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.session_id = session_id
        self.message_id = message_id
        self.token_index = 0
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.total_tokens = 0
        self.accumulated_text = ""
    
    async def start(self):
        """Send stream start event."""
        self.started_at = datetime.utcnow()
        
        event = WSEvent(
            event_type=WSEventType.CHAT_STREAM_START,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data={
                "conversation_id": self.conversation_id,
                "message_id": self.message_id,
                "timestamp": self.started_at.isoformat(),
            },
        )
        
        await self._send_event(event)
    
    async def send_token(self, token: str, metadata: Optional[dict] = None):
        """
        Send a single token.
        
        Args:
            token: Token text
            metadata: Optional metadata (model info, etc.)
        """
        self.accumulated_text += token
        self.total_tokens += 1
        
        stream_token = StreamToken(
            event_id=str(uuid.uuid4()),
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            token=token,
            token_index=self.token_index,
            is_final=False,
            metadata=metadata or {},
        )
        
        event = WSEvent(
            event_type=WSEventType.CHAT_STREAM_TOKEN,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data=stream_token.model_dump(),
        )
        
        await self._send_event(event)
        
        self.token_index += 1
    
    async def finish(
        self,
        finish_reason: str = "stop",
        metadata: Optional[dict] = None
    ):
        """
        Send stream end event.
        
        Args:
            finish_reason: Reason for completion (stop, length, content_filter)
            metadata: Optional metadata
        """
        self.completed_at = datetime.utcnow()
        
        duration = (
            (self.completed_at - self.started_at).total_seconds()
            if self.started_at
            else 0
        )
        
        tokens_per_second = self.total_tokens / duration if duration > 0 else 0
        
        stream_token = StreamToken(
            event_id=str(uuid.uuid4()),
            conversation_id=self.conversation_id,
            message_id=self.message_id,
            token="",
            token_index=self.token_index,
            is_final=True,
            finish_reason=finish_reason,
            metadata={
                **(metadata or {}),
                "total_tokens": self.total_tokens,
                "duration_seconds": duration,
                "tokens_per_second": tokens_per_second,
                "complete_text": self.accumulated_text,
            },
        )
        
        event = WSEvent(
            event_type=WSEventType.CHAT_STREAM_END,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data=stream_token.model_dump(),
        )
        
        await self._send_event(event)
        
        logger.info(
            f"Stream completed: {self.total_tokens} tokens in {duration:.2f}s "
            f"({tokens_per_second:.1f} tokens/sec)"
        )
    
    async def error(self, error_message: str, metadata: Optional[dict] = None):
        """
        Send stream error event.
        
        Args:
            error_message: Error description
            metadata: Optional metadata
        """
        event = WSEvent(
            event_type=WSEventType.CHAT_STREAM_ERROR,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data={
                "conversation_id": self.conversation_id,
                "message_id": self.message_id,
                "error": error_message,
                "token_index": self.token_index,
                "partial_text": self.accumulated_text,
                **(metadata or {}),
            },
        )
        
        await self._send_event(event)
        
        logger.error(f"Stream error: {error_message}")
    
    async def _send_event(self, event: WSEvent):
        """Send event to user's WebSocket connections."""
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)


async def stream_ai_response(
    prompt: str,
    conversation_id: int,
    user_id: int,
    ai_provider: str = "openai",
    session_id: Optional[str] = None,
    message_id: Optional[int] = None,
    **kwargs
) -> AsyncIterator[str]:
    """
    Stream AI response and broadcast to WebSocket.
    
    Args:
        prompt: User prompt
        conversation_id: Conversation ID
        user_id: User ID
        ai_provider: AI provider name (openai, groq, etc.)
        session_id: Optional session ID
        message_id: Optional message ID
        **kwargs: Additional provider-specific parameters
    
    Yields:
        tokens: Individual response tokens
    """
    streamer = LLMStreamer(
        conversation_id=conversation_id,
        user_id=user_id,
        session_id=session_id,
        message_id=message_id,
    )
    
    await streamer.start()
    
    try:
        # Import providers
        from src.cognitive.llm.providers.openai_provider import OpenAIProvider
        from src.cognitive.llm.providers.groq_provider import GroqProvider
        
        # Select provider
        if ai_provider == "openai":
            provider = OpenAIProvider()
        elif ai_provider == "groq":
            provider = GroqProvider()
        else:
            raise ValueError(f"Unsupported streaming provider: {ai_provider}")
        
        # Stream response
        async for token in provider.stream(prompt, **kwargs):
            await streamer.send_token(token)
            yield token
        
        # Finish stream
        await streamer.finish()
        
    except Exception as e:
        await streamer.error(str(e))
        raise


class TypingIndicator:
    """
    Send typing indicator to show user that AI is thinking.
    
    Usage:
        async with TypingIndicator(user_id=123, conversation_id=456):
            # AI processing happens here
            response = await ai.generate(prompt)
    """
    
    def __init__(
        self,
        user_id: int,
        conversation_id: int,
        session_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.session_id = session_id
    
    async def __aenter__(self):
        """Start typing indicator."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Stop typing indicator."""
        await self.stop()
    
    async def start(self):
        """Send typing start event."""
        event = WSEvent(
            event_type=WSEventType.CHAT_TYPING,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data={
                "conversation_id": self.conversation_id,
                "typing": True,
            },
        )
        
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)
    
    async def stop(self):
        """Send typing stop event."""
        event = WSEvent(
            event_type=WSEventType.CHAT_TYPING,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data={
                "conversation_id": self.conversation_id,
                "typing": False,
            },
        )
        
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)
