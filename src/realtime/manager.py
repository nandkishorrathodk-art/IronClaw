"""
WebSocket Connection Manager
Manages all active WebSocket connections with support for 1000+ concurrent clients.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from collections import defaultdict

from src.utils.logging import get_logger
from src.realtime.events import WSEvent, WSEventType
from src.database.models import WebSocketSession
from src.database.connection import get_async_session

logger = get_logger(__name__)


class Connection:
    """Represents a single WebSocket connection."""
    
    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        user_id: int,
        connection_id: str,
    ):
        self.websocket = websocket
        self.session_id = session_id
        self.user_id = user_id
        self.connection_id = connection_id
        self.subscribed_channels: Set[str] = set()
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()
        self.messages_sent = 0
        self.messages_received = 0
        self.bytes_sent = 0
        self.bytes_received = 0
    
    async def send_event(self, event: WSEvent) -> bool:
        """Send event to this connection."""
        try:
            data = event.model_dump(mode="json")
            message = json.dumps(data)
            await self.websocket.send_text(message)
            
            self.messages_sent += 1
            self.bytes_sent += len(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send event to {self.connection_id}: {e}")
            return False
    
    def is_subscribed(self, event_type: str) -> bool:
        """Check if connection is subscribed to event type."""
        return "*" in self.subscribed_channels or event_type in self.subscribed_channels
    
    def subscribe(self, channel: str):
        """Subscribe to a channel."""
        self.subscribed_channels.add(channel)
    
    def unsubscribe(self, channel: str):
        """Unsubscribe from a channel."""
        self.subscribed_channels.discard(channel)


class ConnectionManager:
    """
    Manages all WebSocket connections.
    Optimized for 1000+ concurrent connections.
    """
    
    def __init__(self):
        # Primary storage: connection_id -> Connection
        self.connections: Dict[str, Connection] = {}
        
        # Indexes for fast lookups
        self.user_connections: Dict[int, Set[str]] = defaultdict(set)  # user_id -> connection_ids
        self.session_connections: Dict[str, Set[str]] = defaultdict(set)  # session_id -> connection_ids
        self.channel_subscribers: Dict[str, Set[str]] = defaultdict(set)  # channel -> connection_ids
        
        # Statistics
        self.total_connections_ever = 0
        self.peak_concurrent_connections = 0
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
    
    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: FastAPI WebSocket instance
            user_id: ID of the connecting user
            session_id: Optional session ID (generated if not provided)
        
        Returns:
            connection_id: Unique identifier for this connection
        """
        await websocket.accept()
        
        # Generate IDs
        connection_id = str(uuid.uuid4())
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Create connection object
        connection = Connection(
            websocket=websocket,
            session_id=session_id,
            user_id=user_id,
            connection_id=connection_id,
        )
        
        # Store connection
        self.connections[connection_id] = connection
        self.user_connections[user_id].add(connection_id)
        self.session_connections[session_id].add(connection_id)
        
        # Update statistics
        self.total_connections_ever += 1
        current_count = len(self.connections)
        if current_count > self.peak_concurrent_connections:
            self.peak_concurrent_connections = current_count
        
        # Persist to database
        await self._persist_session(connection)
        
        logger.info(
            f"WebSocket connected: user={user_id}, "
            f"session={session_id}, connection={connection_id}, "
            f"total_active={current_count}"
        )
        
        # Send welcome event
        welcome_event = WSEvent(
            event_type=WSEventType.CONNECT,
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            data={
                "connection_id": connection_id,
                "session_id": session_id,
                "message": "Connected successfully",
            },
        )
        await connection.send_event(welcome_event)
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket connection."""
        connection = self.connections.get(connection_id)
        if not connection:
            return
        
        # Remove from indexes
        self.user_connections[connection.user_id].discard(connection_id)
        self.session_connections[connection.session_id].discard(connection_id)
        
        # Remove from all channel subscriptions
        for channel in connection.subscribed_channels:
            self.channel_subscribers[channel].discard(connection_id)
        
        # Update database
        await self._mark_session_disconnected(connection)
        
        # Remove from primary storage
        del self.connections[connection_id]
        
        logger.info(
            f"WebSocket disconnected: user={connection.user_id}, "
            f"connection={connection_id}, "
            f"duration={(datetime.utcnow() - connection.connected_at).total_seconds():.1f}s, "
            f"sent={connection.messages_sent}, received={connection.messages_received}"
        )
    
    async def broadcast(self, event: WSEvent, user_ids: Optional[List[int]] = None):
        """
        Broadcast event to all connections (or specific users).
        
        Args:
            event: Event to broadcast
            user_ids: If provided, only broadcast to these users
        """
        target_connections = []
        
        if user_ids:
            # Broadcast to specific users
            for user_id in user_ids:
                connection_ids = self.user_connections.get(user_id, set())
                for conn_id in connection_ids:
                    connection = self.connections.get(conn_id)
                    if connection and connection.is_subscribed(event.event_type):
                        target_connections.append(connection)
        else:
            # Broadcast to all connections subscribed to this event type
            for connection in self.connections.values():
                if connection.is_subscribed(event.event_type):
                    target_connections.append(connection)
        
        # Send to all targets concurrently
        if target_connections:
            await asyncio.gather(
                *[conn.send_event(event) for conn in target_connections],
                return_exceptions=True
            )
            logger.debug(f"Broadcasted {event.event_type} to {len(target_connections)} connections")
    
    async def send_to_user(self, user_id: int, event: WSEvent):
        """Send event to all connections of a specific user."""
        connection_ids = self.user_connections.get(user_id, set())
        connections = [
            self.connections[conn_id]
            for conn_id in connection_ids
            if conn_id in self.connections
        ]
        
        if connections:
            await asyncio.gather(
                *[conn.send_event(event) for conn in connections],
                return_exceptions=True
            )
    
    async def send_to_session(self, session_id: str, event: WSEvent):
        """Send event to all connections in a specific session."""
        connection_ids = self.session_connections.get(session_id, set())
        connections = [
            self.connections[conn_id]
            for conn_id in connection_ids
            if conn_id in self.connections
        ]
        
        if connections:
            await asyncio.gather(
                *[conn.send_event(event) for conn in connections],
                return_exceptions=True
            )
    
    async def send_to_channel(self, channel: str, event: WSEvent):
        """Send event to all connections subscribed to a channel."""
        connection_ids = self.channel_subscribers.get(channel, set())
        connections = [
            self.connections[conn_id]
            for conn_id in connection_ids
            if conn_id in self.connections
        ]
        
        if connections:
            await asyncio.gather(
                *[conn.send_event(event) for conn in connections],
                return_exceptions=True
            )
    
    def subscribe(self, connection_id: str, channel: str):
        """Subscribe a connection to a channel."""
        connection = self.connections.get(connection_id)
        if connection:
            connection.subscribe(channel)
            self.channel_subscribers[channel].add(connection_id)
            logger.debug(f"Connection {connection_id} subscribed to {channel}")
    
    def unsubscribe(self, connection_id: str, channel: str):
        """Unsubscribe a connection from a channel."""
        connection = self.connections.get(connection_id)
        if connection:
            connection.unsubscribe(channel)
            self.channel_subscribers[channel].discard(connection_id)
            logger.debug(f"Connection {connection_id} unsubscribed from {channel}")
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        return {
            "active_connections": len(self.connections),
            "active_users": len(self.user_connections),
            "active_sessions": len(self.session_connections),
            "total_connections_ever": self.total_connections_ever,
            "peak_concurrent": self.peak_concurrent_connections,
            "channels": {
                channel: len(subscribers)
                for channel, subscribers in self.channel_subscribers.items()
            },
        }
    
    async def _persist_session(self, connection: Connection):
        """Persist session to database."""
        try:
            async with get_async_session() as session:
                ws_session = WebSocketSession(
                    user_id=connection.user_id,
                    session_id=connection.session_id,
                    connection_id=connection.connection_id,
                    is_connected=True,
                    last_ping_at=datetime.utcnow(),
                    subscribed_channels=list(connection.subscribed_channels),
                )
                session.add(ws_session)
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to persist session: {e}")
    
    async def _mark_session_disconnected(self, connection: Connection):
        """Mark session as disconnected in database."""
        try:
            async with get_async_session() as session:
                result = await session.execute(
                    f"UPDATE websocket_sessions SET is_connected = false, "
                    f"disconnected_at = NOW(), messages_sent = {connection.messages_sent}, "
                    f"messages_received = {connection.messages_received}, "
                    f"bytes_sent = {connection.bytes_sent}, "
                    f"bytes_received = {connection.bytes_received} "
                    f"WHERE connection_id = '{connection.connection_id}'"
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to mark session disconnected: {e}")
    
    async def start_background_tasks(self):
        """Start background maintenance tasks."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_stale_connections())
        if not self._ping_task:
            self._ping_task = asyncio.create_task(self._ping_connections())
    
    async def stop_background_tasks(self):
        """Stop background maintenance tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
    
    async def _cleanup_stale_connections(self):
        """Cleanup stale connections (no activity for 5 minutes)."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                stale_threshold = datetime.utcnow() - timedelta(minutes=5)
                stale_connections = [
                    conn_id
                    for conn_id, conn in self.connections.items()
                    if conn.last_ping < stale_threshold
                ]
                
                for conn_id in stale_connections:
                    logger.warning(f"Disconnecting stale connection: {conn_id}")
                    await self.disconnect(conn_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
    async def _ping_connections(self):
        """Send ping to all connections every 30 seconds."""
        while True:
            try:
                await asyncio.sleep(30)
                
                ping_event = WSEvent(
                    event_type=WSEventType.PING,
                    event_id=str(uuid.uuid4()),
                    data={"timestamp": datetime.utcnow().isoformat()},
                )
                
                for connection in self.connections.values():
                    await connection.send_event(ping_event)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ping task: {e}")


# Global connection manager instance
connection_manager = ConnectionManager()
