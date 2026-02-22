"""
Message Queue Service
Provides guaranteed message delivery using database persistence and Redis Streams.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy import select

from src.utils.logging import get_logger
from src.realtime.events import WSEvent
from src.database.models import MessageQueue
from src.database.connection import get_async_session
from src.database.redis_client import get_redis

logger = get_logger(__name__)


class MessageQueueService:
    """
    Persistent message queue with guaranteed delivery.
    Uses PostgreSQL for durability and Redis Streams for real-time delivery.
    """
    
    def __init__(self):
        self.redis_stream_key = "ironclaw:ws:messages"
        self._delivery_task: Optional[asyncio.Task] = None
        self._retry_task: Optional[asyncio.Task] = None
    
    async def enqueue(
        self,
        user_id: int,
        event: WSEvent,
        session_id: Optional[str] = None,
        ttl_minutes: int = 60,
        max_attempts: int = 3,
    ) -> str:
        """
        Enqueue a message for guaranteed delivery.
        
        Args:
            user_id: Target user ID
            event: Event to deliver
            session_id: Optional specific session ID
            ttl_minutes: Time-to-live in minutes
            max_attempts: Maximum delivery attempts
        
        Returns:
            message_id: Unique message identifier
        """
        message_id = str(uuid.uuid4())
        
        # Persist to database
        async with get_async_session() as session:
            queue_entry = MessageQueue(
                message_id=message_id,
                user_id=user_id,
                session_id=session_id,
                event_type=event.event_type,
                event_data=event.model_dump(mode="json"),
                status="pending",
                max_attempts=max_attempts,
                expires_at=datetime.utcnow() + timedelta(minutes=ttl_minutes),
                next_retry_at=datetime.utcnow(),
            )
            session.add(queue_entry)
            await session.commit()
        
        # Add to Redis Stream for real-time delivery
        redis = await get_redis()
        await redis.xadd(
            self.redis_stream_key,
            {
                "message_id": message_id,
                "user_id": str(user_id),
                "session_id": session_id or "",
                "event_data": json.dumps(event.model_dump(mode="json")),
            }
        )
        
        logger.debug(f"Enqueued message {message_id} for user {user_id}")
        return message_id
    
    async def mark_delivered(self, message_id: str):
        """Mark a message as successfully delivered."""
        async with get_async_session() as session:
            stmt = (
                select(MessageQueue)
                .where(MessageQueue.message_id == message_id)
            )
            result = await session.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                message.status = "delivered"
                message.delivered_at = datetime.utcnow()
                await session.commit()
                logger.debug(f"Marked message {message_id} as delivered")
    
    async def mark_failed(self, message_id: str, error: str):
        """Mark a message delivery as failed."""
        async with get_async_session() as session:
            stmt = (
                select(MessageQueue)
                .where(MessageQueue.message_id == message_id)
            )
            result = await session.execute(stmt)
            message = result.scalar_one_or_none()
            
            if message:
                message.attempts += 1
                message.last_error = error
                
                if message.attempts >= message.max_attempts:
                    message.status = "failed"
                    logger.warning(
                        f"Message {message_id} failed after {message.attempts} attempts: {error}"
                    )
                else:
                    # Exponential backoff: 1min, 2min, 4min...
                    backoff_minutes = 2 ** (message.attempts - 1)
                    message.next_retry_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
                    logger.info(
                        f"Message {message_id} failed, will retry in {backoff_minutes}min "
                        f"(attempt {message.attempts}/{message.max_attempts})"
                    )
                
                await session.commit()
    
    async def get_pending_messages(
        self,
        user_id: Optional[int] = None,
        limit: int = 100
    ) -> List[MessageQueue]:
        """Get pending messages for delivery."""
        async with get_async_session() as session:
            stmt = (
                select(MessageQueue)
                .where(MessageQueue.status == "pending")
                .where(MessageQueue.next_retry_at <= datetime.utcnow())
                .where(MessageQueue.expires_at > datetime.utcnow())
                .order_by(MessageQueue.created_at.asc())
                .limit(limit)
            )
            
            if user_id:
                stmt = stmt.where(MessageQueue.user_id == user_id)
            
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def cleanup_expired(self):
        """Remove expired messages from queue."""
        async with get_async_session() as session:
            # Mark expired as failed
            stmt = (
                select(MessageQueue)
                .where(MessageQueue.status == "pending")
                .where(MessageQueue.expires_at <= datetime.utcnow())
            )
            result = await session.execute(stmt)
            expired = result.scalars().all()
            
            for message in expired:
                message.status = "expired"
                logger.warning(f"Message {message.message_id} expired")
            
            if expired:
                await session.commit()
                logger.info(f"Cleaned up {len(expired)} expired messages")
            
            # Delete old delivered/failed messages (older than 7 days)
            cutoff = datetime.utcnow() - timedelta(days=7)
            delete_stmt = (
                select(MessageQueue)
                .where(MessageQueue.status.in_(["delivered", "failed", "expired"]))
                .where(MessageQueue.created_at < cutoff)
            )
            result = await session.execute(delete_stmt)
            old_messages = result.scalars().all()
            
            for message in old_messages:
                await session.delete(message)
            
            if old_messages:
                await session.commit()
                logger.info(f"Deleted {len(old_messages)} old messages")
    
    async def start_delivery_worker(self):
        """Start background delivery worker."""
        if not self._delivery_task:
            self._delivery_task = asyncio.create_task(self._delivery_loop())
        if not self._retry_task:
            self._retry_task = asyncio.create_task(self._retry_loop())
        logger.info("Message queue delivery worker started")
    
    async def stop_delivery_worker(self):
        """Stop background delivery worker."""
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass
        
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Message queue delivery worker stopped")
    
    async def _delivery_loop(self):
        """Continuously process Redis Stream for real-time delivery."""
        redis = await get_redis()
        consumer_group = "ironclaw-ws-delivery"
        consumer_name = f"worker-{uuid.uuid4().hex[:8]}"
        
        # Create consumer group if not exists
        try:
            await redis.xgroup_create(
                self.redis_stream_key,
                consumer_group,
                id="0",
                mkstream=True
            )
        except Exception:
            pass  # Group already exists
        
        logger.info(f"Delivery worker {consumer_name} started")
        
        while True:
            try:
                # Read from stream
                messages = await redis.xreadgroup(
                    consumer_group,
                    consumer_name,
                    {self.redis_stream_key: ">"},
                    count=10,
                    block=1000,  # 1 second
                )
                
                if not messages:
                    continue
                
                for stream_name, stream_messages in messages:
                    for message_id, data in stream_messages:
                        try:
                            # Process message
                            msg_id = data[b"message_id"].decode()
                            user_id = int(data[b"user_id"].decode())
                            event_data = json.loads(data[b"event_data"].decode())
                            
                            # Import here to avoid circular dependency
                            from src.realtime.manager import connection_manager
                            
                            # Send to user's connections
                            event = WSEvent(**event_data)
                            await connection_manager.send_to_user(user_id, event)
                            
                            # Mark as delivered
                            await self.mark_delivered(msg_id)
                            
                            # Acknowledge message in stream
                            await redis.xack(self.redis_stream_key, consumer_group, message_id)
                            
                        except Exception as e:
                            logger.error(f"Failed to process stream message: {e}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in delivery loop: {e}")
                await asyncio.sleep(5)  # Backoff on error
    
    async def _retry_loop(self):
        """Retry failed deliveries from database."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Get pending messages
                pending = await self.get_pending_messages(limit=50)
                
                if pending:
                    logger.info(f"Retrying {len(pending)} pending messages")
                    
                    from src.realtime.manager import connection_manager
                    
                    for message in pending:
                        try:
                            event = WSEvent(**message.event_data)
                            
                            if message.session_id:
                                await connection_manager.send_to_session(message.session_id, event)
                            else:
                                await connection_manager.send_to_user(message.user_id, event)
                            
                            await self.mark_delivered(message.message_id)
                            
                        except Exception as e:
                            await self.mark_failed(message.message_id, str(e))
                
                # Cleanup expired messages
                await self.cleanup_expired()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in retry loop: {e}")


# Global message queue service instance
message_queue_service = MessageQueueService()
