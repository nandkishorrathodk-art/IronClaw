"""
Real-Time Progress Tracking
Utilities for tracking and broadcasting task progress.
"""
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Callable, Awaitable
from contextlib import asynccontextmanager

from src.utils.logging import get_logger
from src.realtime.events import WSEvent, WSEventType, ProgressEvent
from src.realtime.manager import connection_manager

logger = get_logger(__name__)


class ProgressTracker:
    """
    Track progress of a long-running task and broadcast updates.
    
    Usage:
        async with ProgressTracker(
            task_name="Scanning target.com",
            user_id=123,
            total_steps=100
        ) as tracker:
            for i in range(100):
                await tracker.update(i + 1, current_step=f"Processing item {i+1}")
    """
    
    def __init__(
        self,
        task_name: str,
        user_id: int,
        total_steps: Optional[int] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        broadcast: bool = True,
    ):
        self.task_id = task_id or str(uuid.uuid4())
        self.task_name = task_name
        self.user_id = user_id
        self.session_id = session_id
        self.total_steps = total_steps
        self.completed_steps = 0
        self.progress_percent = 0.0
        self.status = "pending"
        self.current_step = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.broadcast = broadcast
        self.metadata: Dict[str, Any] = {}
    
    async def __aenter__(self):
        """Start tracking."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Finish tracking."""
        if exc_type:
            await self.error(str(exc_val))
        else:
            await self.complete()
    
    async def start(self):
        """Mark task as started."""
        self.status = "running"
        self.started_at = datetime.utcnow()
        
        if self.broadcast:
            await self._broadcast_event(WSEventType.TASK_START)
        
        logger.info(f"Task started: {self.task_name} (ID: {self.task_id})")
    
    async def update(
        self,
        completed_steps: Optional[int] = None,
        progress_percent: Optional[float] = None,
        current_step: Optional[str] = None,
        **metadata
    ):
        """
        Update task progress.
        
        Args:
            completed_steps: Number of steps completed
            progress_percent: Progress percentage (0-100)
            current_step: Description of current step
            **metadata: Additional metadata to include
        """
        if completed_steps is not None:
            self.completed_steps = completed_steps
            if self.total_steps:
                self.progress_percent = (completed_steps / self.total_steps) * 100
        
        if progress_percent is not None:
            self.progress_percent = max(0, min(100, progress_percent))
        
        if current_step is not None:
            self.current_step = current_step
        
        if metadata:
            self.metadata.update(metadata)
        
        if self.broadcast:
            await self._broadcast_event(WSEventType.TASK_PROGRESS)
    
    async def complete(self, **metadata):
        """Mark task as completed."""
        self.status = "completed"
        self.progress_percent = 100.0
        self.completed_at = datetime.utcnow()
        
        if metadata:
            self.metadata.update(metadata)
        
        if self.broadcast:
            await self._broadcast_event(WSEventType.TASK_COMPLETE)
        
        duration = (self.completed_at - self.started_at).total_seconds() if self.started_at else 0
        logger.info(
            f"Task completed: {self.task_name} (ID: {self.task_id}, "
            f"duration: {duration:.1f}s)"
        )
    
    async def error(self, error_message: str, **metadata):
        """Mark task as failed."""
        self.status = "failed"
        self.metadata["error"] = error_message
        
        if metadata:
            self.metadata.update(metadata)
        
        if self.broadcast:
            await self._broadcast_event(WSEventType.TASK_ERROR)
        
        logger.error(f"Task failed: {self.task_name} (ID: {self.task_id}): {error_message}")
    
    async def _broadcast_event(self, event_type: WSEventType):
        """Broadcast progress event to user."""
        # Calculate ETA if applicable
        eta_seconds = None
        if (
            self.started_at
            and self.progress_percent > 0
            and self.progress_percent < 100
        ):
            elapsed = (datetime.utcnow() - self.started_at).total_seconds()
            eta_seconds = (elapsed / self.progress_percent) * (100 - self.progress_percent)
        
        # Create progress event
        progress_event = ProgressEvent(
            event_id=str(uuid.uuid4()),
            task_id=self.task_id,
            task_name=self.task_name,
            progress_percent=self.progress_percent,
            status=self.status,
            current_step=self.current_step,
            total_steps=self.total_steps,
            completed_steps=self.completed_steps,
            eta_seconds=eta_seconds,
            metadata=self.metadata,
        )
        
        # Wrap in WSEvent
        event = WSEvent(
            event_type=event_type,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data=progress_event.model_dump(),
        )
        
        # Broadcast
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)


class ScanProgressTracker(ProgressTracker):
    """
    Specialized progress tracker for security scans.
    Broadcasts SCAN_* events instead of TASK_*.
    """
    
    async def _broadcast_event(self, event_type: WSEventType):
        """Override to use scan event types."""
        # Map task events to scan events
        event_mapping = {
            WSEventType.TASK_START: WSEventType.SCAN_START,
            WSEventType.TASK_PROGRESS: WSEventType.SCAN_PROGRESS,
            WSEventType.TASK_COMPLETE: WSEventType.SCAN_COMPLETE,
            WSEventType.TASK_ERROR: WSEventType.SCAN_ERROR,
        }
        
        scan_event_type = event_mapping.get(event_type, event_type)
        
        # Create progress event
        progress_event = ProgressEvent(
            event_id=str(uuid.uuid4()),
            task_id=self.task_id,
            task_name=self.task_name,
            progress_percent=self.progress_percent,
            status=self.status,
            current_step=self.current_step,
            total_steps=self.total_steps,
            completed_steps=self.completed_steps,
            metadata=self.metadata,
        )
        
        # Wrap in WSEvent
        event = WSEvent(
            event_type=scan_event_type,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data=progress_event.model_dump(),
        )
        
        # Broadcast
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)
    
    async def finding(self, finding_data: Dict[str, Any]):
        """Broadcast a new finding."""
        event = WSEvent(
            event_type=WSEventType.SCAN_FINDING,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data={
                "task_id": self.task_id,
                "task_name": self.task_name,
                "finding": finding_data,
            },
        )
        
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)


class WorkflowProgressTracker(ProgressTracker):
    """
    Specialized progress tracker for workflow execution.
    Broadcasts WORKFLOW_* events.
    """
    
    async def _broadcast_event(self, event_type: WSEventType):
        """Override to use workflow event types."""
        # Map task events to workflow events
        event_mapping = {
            WSEventType.TASK_START: WSEventType.WORKFLOW_START,
            WSEventType.TASK_PROGRESS: WSEventType.WORKFLOW_STEP,
            WSEventType.TASK_COMPLETE: WSEventType.WORKFLOW_COMPLETE,
            WSEventType.TASK_ERROR: WSEventType.WORKFLOW_ERROR,
        }
        
        workflow_event_type = event_mapping.get(event_type, event_type)
        
        # Create progress event
        progress_event = ProgressEvent(
            event_id=str(uuid.uuid4()),
            task_id=self.task_id,
            task_name=self.task_name,
            progress_percent=self.progress_percent,
            status=self.status,
            current_step=self.current_step,
            total_steps=self.total_steps,
            completed_steps=self.completed_steps,
            metadata=self.metadata,
        )
        
        # Wrap in WSEvent
        event = WSEvent(
            event_type=workflow_event_type,
            event_id=str(uuid.uuid4()),
            user_id=self.user_id,
            session_id=self.session_id,
            data=progress_event.model_dump(),
        )
        
        # Broadcast
        if self.session_id:
            await connection_manager.send_to_session(self.session_id, event)
        else:
            await connection_manager.send_to_user(self.user_id, event)


async def broadcast_system_notification(
    user_id: int,
    title: str,
    message: str,
    severity: str = "info",
    action_required: bool = False,
    action_url: Optional[str] = None,
    session_id: Optional[str] = None,
):
    """
    Broadcast a system notification to a user.
    
    Args:
        user_id: Target user ID
        title: Notification title
        message: Notification message
        severity: info, warning, error, critical
        action_required: Whether user action is required
        action_url: Optional URL for action
        session_id: Optional specific session ID
    """
    from src.realtime.events import SystemEvent
    
    system_event = SystemEvent(
        event_id=str(uuid.uuid4()),
        severity=severity,
        title=title,
        message=message,
        action_required=action_required,
        action_url=action_url,
    )
    
    event = WSEvent(
        event_type=WSEventType.SYSTEM_NOTIFICATION,
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        session_id=session_id,
        data=system_event.model_dump(),
    )
    
    if session_id:
        await connection_manager.send_to_session(session_id, event)
    else:
        await connection_manager.send_to_user(user_id, event)
