"""
WebSocket API Endpoints
Real-time communication endpoints with streaming support.
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, status
from fastapi.responses import JSONResponse

from src.utils.logging import get_logger
from src.realtime.manager import connection_manager
from src.realtime.message_queue import message_queue_service
from src.realtime.events import (
    WSEvent,
    WSEventType,
    SubscriptionMessage,
    SubscriptionResponse,
    PresenceEvent,
    SystemEvent,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/ws", tags=["WebSocket"])


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int = Query(..., description="User ID for authentication"),
    session_id: Optional[str] = Query(None, description="Optional session ID"),
):
    """
    Main WebSocket endpoint.
    
    Protocol:
    1. Client connects with user_id (and optional session_id)
    2. Server sends CONNECT event with connection details
    3. Client can:
       - Subscribe to event channels
       - Send messages
       - Receive real-time updates
    4. Server sends PING every 30s, expects PONG
    5. Connection closed on disconnect or timeout
    
    Message Format (JSON):
    {
        "event_type": "chat.message",
        "event_id": "uuid",
        "timestamp": "ISO8601",
        "user_id": 123,
        "session_id": "session-uuid",
        "data": {...}
    }
    """
    connection_id = None
    
    try:
        # Accept connection
        connection_id = await connection_manager.connect(
            websocket=websocket,
            user_id=user_id,
            session_id=session_id,
        )
        
        # Broadcast user join
        join_event = WSEvent(
            event_type=WSEventType.USER_JOIN,
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            data={
                "user_id": user_id,
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        await connection_manager.broadcast(join_event)
        
        # Message handling loop
        while True:
            try:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                action = message.get("action")
                
                if action == "subscribe":
                    # Subscribe to channels
                    channels = message.get("channels", [])
                    for channel in channels:
                        connection_manager.subscribe(connection_id, channel)
                    
                    # Send confirmation
                    response = SubscriptionResponse(
                        success=True,
                        channels=channels,
                        message=f"Subscribed to {len(channels)} channels",
                    )
                    response_event = WSEvent(
                        event_type=WSEventType.SUBSCRIBED,
                        event_id=str(uuid.uuid4()),
                        user_id=user_id,
                        session_id=session_id,
                        data=response.model_dump(),
                    )
                    connection = connection_manager.connections.get(connection_id)
                    if connection:
                        await connection.send_event(response_event)
                
                elif action == "unsubscribe":
                    # Unsubscribe from channels
                    channels = message.get("channels", [])
                    for channel in channels:
                        connection_manager.unsubscribe(connection_id, channel)
                    
                    # Send confirmation
                    response = SubscriptionResponse(
                        success=True,
                        channels=channels,
                        message=f"Unsubscribed from {len(channels)} channels",
                    )
                    response_event = WSEvent(
                        event_type=WSEventType.UNSUBSCRIBED,
                        event_id=str(uuid.uuid4()),
                        user_id=user_id,
                        session_id=session_id,
                        data=response.model_dump(),
                    )
                    connection = connection_manager.connections.get(connection_id)
                    if connection:
                        await connection.send_event(response_event)
                
                elif action == "pong":
                    # Update last pong time
                    connection = connection_manager.connections.get(connection_id)
                    if connection:
                        connection.last_ping = datetime.utcnow()
                
                else:
                    # Forward other messages as events
                    event = WSEvent(**message)
                    
                    # Handle based on event type
                    if event.event_type.startswith("chat."):
                        # Chat events - might want to persist these
                        pass
                    
                    # Could add more event-specific handling here
                
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON from connection {connection_id}: {e}")
            except Exception as e:
                logger.error(f"Error processing message from {connection_id}: {e}")
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket {connection_id} disconnected normally")
    
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    
    finally:
        # Cleanup on disconnect
        if connection_id:
            # Broadcast user leave
            leave_event = WSEvent(
                event_type=WSEventType.USER_LEAVE,
                event_id=str(uuid.uuid4()),
                user_id=user_id,
                session_id=session_id,
                data={
                    "user_id": user_id,
                    "session_id": session_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
            await connection_manager.broadcast(leave_event)
            
            # Disconnect
            await connection_manager.disconnect(connection_id)


@router.get("/stats")
async def get_websocket_stats():
    """Get WebSocket connection statistics."""
    return connection_manager.get_stats()


@router.post("/broadcast")
async def broadcast_message(
    event_type: str,
    data: Dict,
    user_ids: Optional[list[int]] = None,
):
    """
    Broadcast a message to all connected users (or specific users).
    
    Args:
        event_type: Type of event (e.g., "system.notification")
        data: Event payload
        user_ids: Optional list of specific user IDs to broadcast to
    """
    event = WSEvent(
        event_type=event_type,
        event_id=str(uuid.uuid4()),
        data=data,
    )
    
    await connection_manager.broadcast(event, user_ids=user_ids)
    
    return {
        "success": True,
        "event_id": event.event_id,
        "recipients": len(user_ids) if user_ids else connection_manager.get_stats()["active_users"],
    }


@router.post("/send-to-user/{user_id}")
async def send_to_user(user_id: int, event_type: str, data: Dict):
    """
    Send a message to a specific user's all active connections.
    
    Args:
        user_id: Target user ID
        event_type: Type of event
        data: Event payload
    """
    event = WSEvent(
        event_type=event_type,
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        data=data,
    )
    
    await connection_manager.send_to_user(user_id, event)
    
    return {
        "success": True,
        "event_id": event.event_id,
        "user_id": user_id,
    }


@router.post("/send-to-session/{session_id}")
async def send_to_session(session_id: str, event_type: str, data: Dict):
    """
    Send a message to a specific session.
    
    Args:
        session_id: Target session ID
        event_type: Type of event
        data: Event payload
    """
    event = WSEvent(
        event_type=event_type,
        event_id=str(uuid.uuid4()),
        session_id=session_id,
        data=data,
    )
    
    await connection_manager.send_to_session(session_id, event)
    
    return {
        "success": True,
        "event_id": event.event_id,
        "session_id": session_id,
    }


@router.post("/send-to-channel/{channel}")
async def send_to_channel(channel: str, event_type: str, data: Dict):
    """
    Send a message to all connections subscribed to a channel.
    
    Args:
        channel: Target channel name
        event_type: Type of event
        data: Event payload
    """
    event = WSEvent(
        event_type=event_type,
        event_id=str(uuid.uuid4()),
        data=data,
    )
    
    await connection_manager.send_to_channel(channel, event)
    
    stats = connection_manager.get_stats()
    channel_stats = stats["channels"].get(channel, 0)
    
    return {
        "success": True,
        "event_id": event.event_id,
        "channel": channel,
        "recipients": channel_stats,
    }


@router.get("/message-queue/stats")
async def get_message_queue_stats():
    """Get message queue statistics."""
    pending = await message_queue_service.get_pending_messages(limit=1000)
    
    return {
        "pending_messages": len(pending),
        "by_status": {
            "pending": len([m for m in pending if m.status == "pending"]),
            "failed": len([m for m in pending if m.status == "failed"]),
        },
    }
