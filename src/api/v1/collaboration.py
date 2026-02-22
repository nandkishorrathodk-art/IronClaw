"""
Collaboration API Endpoints
Team collaboration, shared resources, and multi-user editing.
"""
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from sqlalchemy import select

from src.utils.logging import get_logger
from src.realtime.collaboration import collaboration_manager
from src.database.models import SharedResource
from src.database.connection import get_async_session

logger = get_logger(__name__)
router = APIRouter(prefix="/collaboration", tags=["Collaboration"])


class JoinSessionRequest(BaseModel):
    """Request to join a collaboration session."""
    resource_type: str
    resource_id: int
    username: str
    session_id: str


class LeaveSessionRequest(BaseModel):
    """Request to leave a collaboration session."""
    resource_type: str
    resource_id: int
    session_id: str


class CursorUpdateRequest(BaseModel):
    """Cursor position update."""
    resource_type: str
    resource_id: int
    cursor_pos: Dict
    session_id: str


class EditRequest(BaseModel):
    """Collaborative edit request."""
    resource_type: str
    resource_id: int
    edit_data: Dict
    session_id: str


class ShareResourceRequest(BaseModel):
    """Request to share a resource."""
    resource_type: str
    resource_id: int
    share_mode: str  # view_only, edit, admin
    user_ids: List[int]
    is_public: bool = False


@router.post("/join")
async def join_session(request: JoinSessionRequest, user_id: int):
    """
    Join a collaborative editing session.
    
    Args:
        request: Join session request
        user_id: Current user ID (from auth token)
    """
    # Verify user has access to resource
    async with get_async_session() as session:
        # Check if resource is shared
        stmt = (
            select(SharedResource)
            .where(SharedResource.resource_type == request.resource_type)
            .where(SharedResource.resource_id == request.resource_id)
        )
        result = await session.execute(stmt)
        shared_resource = result.scalar_one_or_none()
        
        if shared_resource:
            # Check access
            if not shared_resource.is_public:
                allowed_users = shared_resource.allowed_user_ids or []
                if (
                    user_id != shared_resource.owner_user_id
                    and user_id not in allowed_users
                ):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You don't have access to this resource"
                    )
    
    # Join collaboration session
    await collaboration_manager.join_session(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        user_id=user_id,
        username=request.username,
        session_id=request.session_id,
    )
    
    return {
        "success": True,
        "message": "Joined collaboration session",
        "resource_type": request.resource_type,
        "resource_id": request.resource_id,
    }


@router.post("/leave")
async def leave_session(request: LeaveSessionRequest, user_id: int):
    """Leave a collaborative editing session."""
    await collaboration_manager.leave_session(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        user_id=user_id,
        session_id=request.session_id,
    )
    
    return {
        "success": True,
        "message": "Left collaboration session",
    }


@router.post("/cursor")
async def update_cursor(request: CursorUpdateRequest, user_id: int):
    """Update cursor position in collaborative session."""
    await collaboration_manager.update_cursor(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        user_id=user_id,
        cursor_pos=request.cursor_pos,
        session_id=request.session_id,
    )
    
    return {"success": True}


@router.post("/edit")
async def apply_edit(request: EditRequest, user_id: int):
    """
    Apply an edit to a shared resource.
    Includes conflict detection and resolution.
    """
    result = await collaboration_manager.apply_edit(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        user_id=user_id,
        edit_data=request.edit_data,
        session_id=request.session_id,
    )
    
    return result


@router.post("/lock/{resource_type}/{resource_id}")
async def acquire_lock(resource_type: str, resource_id: int, user_id: int):
    """Acquire exclusive lock for editing."""
    success = await collaboration_manager.acquire_lock(
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resource is already locked by another user"
        )
    
    return {
        "success": True,
        "message": "Lock acquired",
    }


@router.delete("/lock/{resource_type}/{resource_id}")
async def release_lock(resource_type: str, resource_id: int, user_id: int):
    """Release exclusive lock."""
    await collaboration_manager.release_lock(
        resource_type=resource_type,
        resource_id=resource_id,
        user_id=user_id,
    )
    
    return {
        "success": True,
        "message": "Lock released",
    }


@router.get("/activity/{resource_type}/{resource_id}")
async def get_activity_feed(resource_type: str, resource_id: int, limit: int = 50):
    """Get activity feed for a resource."""
    events = await collaboration_manager.get_activity_feed(
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
    )
    
    return {
        "success": True,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "events": events,
    }


@router.post("/share")
async def share_resource(request: ShareResourceRequest, user_id: int):
    """
    Share a resource with other users.
    
    Args:
        request: Share request
        user_id: Owner user ID (from auth token)
    """
    async with get_async_session() as session:
        # Create or update shared resource
        stmt = (
            select(SharedResource)
            .where(SharedResource.resource_type == request.resource_type)
            .where(SharedResource.resource_id == request.resource_id)
            .where(SharedResource.owner_user_id == user_id)
        )
        result = await session.execute(stmt)
        shared = result.scalar_one_or_none()
        
        if shared:
            # Update existing
            shared.share_mode = request.share_mode
            shared.is_public = request.is_public
            shared.allowed_user_ids = request.user_ids
        else:
            # Create new
            shared = SharedResource(
                resource_type=request.resource_type,
                resource_id=request.resource_id,
                owner_user_id=user_id,
                share_mode=request.share_mode,
                is_public=request.is_public,
                allowed_user_ids=request.user_ids,
            )
            session.add(shared)
        
        await session.commit()
    
    return {
        "success": True,
        "message": f"Resource shared with {len(request.user_ids)} users",
        "share_mode": request.share_mode,
        "is_public": request.is_public,
    }


@router.get("/shared")
async def get_shared_resources(user_id: int):
    """Get all resources shared with the current user."""
    async with get_async_session() as session:
        stmt = (
            select(SharedResource)
            .where(
                (SharedResource.owner_user_id == user_id)
                | (SharedResource.is_public == True)
            )
        )
        result = await session.execute(stmt)
        resources = result.scalars().all()
        
        # Filter by allowed_user_ids
        filtered = [
            r for r in resources
            if r.owner_user_id == user_id
            or r.is_public
            or (r.allowed_user_ids and user_id in r.allowed_user_ids)
        ]
        
        return {
            "success": True,
            "resources": [
                {
                    "id": r.id,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "owner_user_id": r.owner_user_id,
                    "share_mode": r.share_mode,
                    "is_public": r.is_public,
                    "created_at": r.created_at.isoformat(),
                }
                for r in filtered
            ],
        }
