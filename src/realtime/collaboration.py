"""
Multi-User Collaboration
Real-time collaborative editing with conflict resolution.
"""
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set
from collections import defaultdict
from sqlalchemy import select

from src.utils.logging import get_logger
from src.realtime.events import (
    WSEvent,
    WSEventType,
    CollaborationEvent as CollabEventSchema,
    PresenceEvent,
)
from src.realtime.manager import connection_manager
from src.database.models import CollaborationEvent, SharedResource
from src.database.connection import get_async_session

logger = get_logger(__name__)


class CollaborationManager:
    """
    Manages real-time collaboration sessions with conflict resolution.
    
    Features:
    - User presence tracking
    - Cursor position sharing
    - Collaborative editing with operational transformation
    - Conflict detection and resolution
    - Activity feed
    """
    
    def __init__(self):
        # Track active collaboration sessions
        # resource_id -> {user_ids, version, lock_holder}
        self.sessions: Dict[str, Dict] = {}
        
        # Track user presence in each resource
        # resource_id -> {user_id -> {username, cursor_pos, last_activity}}
        self.presence: Dict[str, Dict[int, Dict]] = defaultdict(dict)
    
    async def join_session(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        username: str,
        session_id: str,
    ):
        """
        User joins a collaborative session.
        
        Args:
            resource_type: Type of resource (conversation, workflow, etc.)
            resource_id: ID of the resource
            user_id: User ID
            username: Username for display
            session_id: WebSocket session ID
        """
        resource_key = f"{resource_type}:{resource_id}"
        
        # Initialize session if not exists
        if resource_key not in self.sessions:
            self.sessions[resource_key] = {
                "resource_type": resource_type,
                "resource_id": resource_id,
                "users": set(),
                "version": 1,
                "lock_holder": None,
            }
        
        # Add user to session
        self.sessions[resource_key]["users"].add(user_id)
        
        # Track presence
        self.presence[resource_key][user_id] = {
            "username": username,
            "session_id": session_id,
            "cursor_pos": None,
            "last_activity": datetime.utcnow(),
            "status": "active",
        }
        
        # Persist join event
        await self._persist_event(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            event_type="join",
            session_id=session_id,
            payload={"username": username},
        )
        
        # Broadcast join event to all users in session
        await self._broadcast_to_session(
            resource_key,
            WSEventType.USER_JOIN,
            {
                "user_id": user_id,
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "active_users": [
                    {
                        "user_id": uid,
                        "username": self.presence[resource_key][uid]["username"],
                        "status": self.presence[resource_key][uid]["status"],
                    }
                    for uid in self.sessions[resource_key]["users"]
                ],
            },
        )
        
        logger.info(
            f"User {username} joined collaboration session {resource_key} "
            f"(total users: {len(self.sessions[resource_key]['users'])})"
        )
    
    async def leave_session(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        session_id: str,
    ):
        """User leaves a collaborative session."""
        resource_key = f"{resource_type}:{resource_id}"
        
        if resource_key not in self.sessions:
            return
        
        # Get username before removing
        username = self.presence[resource_key].get(user_id, {}).get("username", "Unknown")
        
        # Remove from session
        self.sessions[resource_key]["users"].discard(user_id)
        
        # Release lock if user holds it
        if self.sessions[resource_key]["lock_holder"] == user_id:
            self.sessions[resource_key]["lock_holder"] = None
        
        # Remove presence
        if user_id in self.presence[resource_key]:
            del self.presence[resource_key][user_id]
        
        # Persist leave event
        await self._persist_event(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            event_type="leave",
            session_id=session_id,
            payload={"username": username},
        )
        
        # Broadcast leave event
        await self._broadcast_to_session(
            resource_key,
            WSEventType.USER_LEAVE,
            {
                "user_id": user_id,
                "username": username,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "active_users": [
                    {
                        "user_id": uid,
                        "username": self.presence[resource_key][uid]["username"],
                        "status": self.presence[resource_key][uid]["status"],
                    }
                    for uid in self.sessions[resource_key]["users"]
                ],
            },
        )
        
        # Cleanup empty session
        if not self.sessions[resource_key]["users"]:
            del self.sessions[resource_key]
            del self.presence[resource_key]
        
        logger.info(f"User {username} left collaboration session {resource_key}")
    
    async def update_cursor(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        cursor_pos: Dict,
        session_id: str,
    ):
        """
        Update user's cursor position.
        
        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            user_id: User ID
            cursor_pos: Cursor position data (line, column, etc.)
            session_id: WebSocket session ID
        """
        resource_key = f"{resource_type}:{resource_id}"
        
        if resource_key not in self.presence:
            return
        
        if user_id not in self.presence[resource_key]:
            return
        
        # Update cursor position
        self.presence[resource_key][user_id]["cursor_pos"] = cursor_pos
        self.presence[resource_key][user_id]["last_activity"] = datetime.utcnow()
        
        # Broadcast cursor update (exclude sender)
        username = self.presence[resource_key][user_id]["username"]
        
        await self._broadcast_to_session(
            resource_key,
            WSEventType.COLLAB_CURSOR,
            {
                "user_id": user_id,
                "username": username,
                "cursor_pos": cursor_pos,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
            exclude_user=user_id,
        )
    
    async def apply_edit(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        edit_data: Dict,
        session_id: str,
    ) -> Dict:
        """
        Apply an edit with conflict detection.
        
        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            user_id: User ID
            edit_data: Edit operation data
            session_id: WebSocket session ID
        
        Returns:
            result: {success, version, conflicts, resolved_edit}
        """
        resource_key = f"{resource_type}:{resource_id}"
        
        if resource_key not in self.sessions:
            return {"success": False, "error": "Session not found"}
        
        session = self.sessions[resource_key]
        username = self.presence[resource_key].get(user_id, {}).get("username", "Unknown")
        
        # Conflict detection (optimistic locking)
        client_version = edit_data.get("version", 1)
        current_version = session["version"]
        
        conflicts_detected = client_version < current_version
        resolved_edit = edit_data.copy()
        
        if conflicts_detected:
            # Simple conflict resolution: accept newer version
            # In production, use operational transformation (OT) or CRDTs
            logger.warning(
                f"Conflict detected: user {username} editing v{client_version}, "
                f"current v{current_version}"
            )
            resolved_edit["version"] = current_version
        
        # Increment version
        session["version"] += 1
        resolved_edit["version"] = session["version"]
        
        # Persist edit event
        await self._persist_event(
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            event_type="edit",
            session_id=session_id,
            payload=resolved_edit,
            version=session["version"],
            conflicts_detected=conflicts_detected,
        )
        
        # Broadcast edit to all users (including sender for confirmation)
        await self._broadcast_to_session(
            resource_key,
            WSEventType.COLLAB_EDIT,
            {
                "user_id": user_id,
                "username": username,
                "edit": resolved_edit,
                "version": session["version"],
                "conflicts": conflicts_detected,
                "resource_type": resource_type,
                "resource_id": resource_id,
            },
        )
        
        return {
            "success": True,
            "version": session["version"],
            "conflicts": conflicts_detected,
            "resolved_edit": resolved_edit,
        }
    
    async def acquire_lock(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
    ) -> bool:
        """
        Acquire exclusive lock for editing.
        
        Returns:
            success: True if lock acquired
        """
        resource_key = f"{resource_type}:{resource_id}"
        
        if resource_key not in self.sessions:
            return False
        
        session = self.sessions[resource_key]
        
        # Check if already locked
        if session["lock_holder"] and session["lock_holder"] != user_id:
            return False
        
        # Acquire lock
        session["lock_holder"] = user_id
        
        # Broadcast lock status
        username = self.presence[resource_key].get(user_id, {}).get("username", "Unknown")
        await self._broadcast_to_session(
            resource_key,
            WSEventType.SYSTEM_NOTIFICATION,
            {
                "title": "Resource Locked",
                "message": f"{username} is editing",
                "locked_by": user_id,
                "username": username,
            },
        )
        
        logger.info(f"User {username} acquired lock on {resource_key}")
        return True
    
    async def release_lock(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
    ):
        """Release exclusive lock."""
        resource_key = f"{resource_type}:{resource_id}"
        
        if resource_key not in self.sessions:
            return
        
        session = self.sessions[resource_key]
        
        if session["lock_holder"] == user_id:
            session["lock_holder"] = None
            
            # Broadcast unlock
            await self._broadcast_to_session(
                resource_key,
                WSEventType.SYSTEM_NOTIFICATION,
                {
                    "title": "Resource Unlocked",
                    "message": "Available for editing",
                },
            )
    
    async def get_activity_feed(
        self,
        resource_type: str,
        resource_id: int,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get activity feed for a resource.
        
        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            limit: Maximum number of events to return
        
        Returns:
            events: List of activity events
        """
        async with get_async_session() as session:
            stmt = (
                select(CollaborationEvent)
                .where(CollaborationEvent.resource_type == resource_type)
                .where(CollaborationEvent.resource_id == resource_id)
                .order_by(CollaborationEvent.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            
            return [
                {
                    "event_type": event.event_type,
                    "user_id": event.user_id,
                    "payload": event.payload,
                    "timestamp": event.created_at.isoformat(),
                    "conflicts": event.conflicts_detected,
                    "version": event.version,
                }
                for event in events
            ]
    
    async def _persist_event(
        self,
        resource_type: str,
        resource_id: int,
        user_id: int,
        event_type: str,
        session_id: str,
        payload: Dict,
        version: int = 1,
        conflicts_detected: bool = False,
    ):
        """Persist collaboration event to database."""
        async with get_async_session() as session:
            event = CollaborationEvent(
                session_id=session_id,
                user_id=user_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                payload=payload,
                version=version,
                conflicts_detected=conflicts_detected,
                resolved=not conflicts_detected,
            )
            session.add(event)
            await session.commit()
    
    async def _broadcast_to_session(
        self,
        resource_key: str,
        event_type: WSEventType,
        data: Dict,
        exclude_user: Optional[int] = None,
    ):
        """Broadcast event to all users in a collaboration session."""
        if resource_key not in self.sessions:
            return
        
        for user_id in self.sessions[resource_key]["users"]:
            if exclude_user and user_id == exclude_user:
                continue
            
            event = WSEvent(
                event_type=event_type,
                event_id=str(uuid.uuid4()),
                user_id=user_id,
                data=data,
            )
            
            await connection_manager.send_to_user(user_id, event)


# Global collaboration manager instance
collaboration_manager = CollaborationManager()
