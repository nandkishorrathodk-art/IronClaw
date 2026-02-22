"""
WebSocket Event Schemas
Defines all event types and their payloads for real-time communication.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, Field


class WSEventType(str, Enum):
    """WebSocket event types."""
    
    # Connection events
    CONNECT = "connect"
    DISCONNECT = "disconnect"
    PING = "ping"
    PONG = "pong"
    
    # Chat events
    CHAT_MESSAGE = "chat.message"
    CHAT_TYPING = "chat.typing"
    CHAT_STREAM_START = "chat.stream.start"
    CHAT_STREAM_TOKEN = "chat.stream.token"
    CHAT_STREAM_END = "chat.stream.end"
    CHAT_STREAM_ERROR = "chat.stream.error"
    
    # Progress events
    TASK_START = "task.start"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETE = "task.complete"
    TASK_ERROR = "task.error"
    
    # Scan/Security events
    SCAN_START = "scan.start"
    SCAN_PROGRESS = "scan.progress"
    SCAN_FINDING = "scan.finding"
    SCAN_COMPLETE = "scan.complete"
    SCAN_ERROR = "scan.error"
    
    # Workflow events
    WORKFLOW_START = "workflow.start"
    WORKFLOW_STEP = "workflow.step"
    WORKFLOW_COMPLETE = "workflow.complete"
    WORKFLOW_ERROR = "workflow.error"
    
    # Presence events
    USER_JOIN = "user.join"
    USER_LEAVE = "user.leave"
    USER_STATUS = "user.status"
    
    # Collaboration events
    COLLAB_EDIT = "collab.edit"
    COLLAB_CURSOR = "collab.cursor"
    COLLAB_COMMENT = "collab.comment"
    COLLAB_CONFLICT = "collab.conflict"
    
    # System events
    SYSTEM_NOTIFICATION = "system.notification"
    SYSTEM_ERROR = "system.error"
    SYSTEM_MAINTENANCE = "system.maintenance"
    
    # Subscription events
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"


class WSEvent(BaseModel):
    """Base WebSocket event."""
    
    event_type: WSEventType = Field(..., description="Type of event")
    event_id: str = Field(..., description="Unique event ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: Optional[int] = Field(None, description="User who triggered the event")
    session_id: Optional[str] = Field(None, description="Session ID")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event payload")
    
    class Config:
        use_enum_values = True


class ChatEvent(BaseModel):
    """Chat-related events."""
    
    event_id: str
    conversation_id: int
    message_id: Optional[int] = None
    role: str  # user, assistant, system
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ProgressEvent(BaseModel):
    """Task progress events."""
    
    event_id: str
    task_id: str
    task_name: str
    progress_percent: float = Field(..., ge=0, le=100)
    status: str  # pending, running, completed, failed
    current_step: Optional[str] = None
    total_steps: Optional[int] = None
    completed_steps: Optional[int] = None
    eta_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PresenceEvent(BaseModel):
    """User presence events."""
    
    event_id: str
    user_id: int
    username: str
    status: str  # online, offline, away, busy
    session_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CollaborationEvent(BaseModel):
    """Collaborative editing events."""
    
    event_id: str
    resource_type: str  # conversation, workflow, document
    resource_id: int
    user_id: int
    username: str
    action: str  # edit, cursor_move, comment, highlight
    payload: Dict[str, Any]
    version: int = 1
    conflicts: bool = False


class SystemEvent(BaseModel):
    """System notifications and alerts."""
    
    event_id: str
    severity: str  # info, warning, error, critical
    title: str
    message: str
    action_required: bool = False
    action_url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StreamToken(BaseModel):
    """Streaming token event for LLM responses."""
    
    event_id: str
    conversation_id: int
    message_id: Optional[int] = None
    token: str
    token_index: int
    is_final: bool = False
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubscriptionMessage(BaseModel):
    """Subscribe/unsubscribe message."""
    
    action: str  # subscribe, unsubscribe
    channels: list[str]  # List of event types to subscribe to


class SubscriptionResponse(BaseModel):
    """Subscription confirmation."""
    
    success: bool
    channels: list[str]
    message: str
