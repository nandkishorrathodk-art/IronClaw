"""
Collaboration Tests
Test multi-user collaboration, presence, and conflict resolution.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.realtime.collaboration import collaboration_manager
from src.realtime.events import WSEventType


class TestCollaboration:
    """Test collaboration functionality."""
    
    @pytest.mark.asyncio
    async def test_join_leave_session(self):
        """Test joining and leaving collaboration sessions."""
        # Join session
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        resource_key = "conversation:1"
        assert resource_key in collaboration_manager.sessions
        assert 1 in collaboration_manager.sessions[resource_key]["users"]
        
        # Leave session
        await collaboration_manager.leave_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            session_id="session1",
        )
        
        # Session should be cleaned up
        assert resource_key not in collaboration_manager.sessions
    
    @pytest.mark.asyncio
    async def test_multi_user_session(self):
        """Test multiple users in same session."""
        # User 1 joins
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        # User 2 joins
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=2,
            username="user2",
            session_id="session2",
        )
        
        resource_key = "conversation:1"
        assert len(collaboration_manager.sessions[resource_key]["users"]) == 2
        
        # Cleanup
        await collaboration_manager.leave_session("conversation", 1, 1, "session1")
        await collaboration_manager.leave_session("conversation", 1, 2, "session2")
    
    @pytest.mark.asyncio
    async def test_cursor_tracking(self):
        """Test cursor position tracking."""
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        # Update cursor
        await collaboration_manager.update_cursor(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            cursor_pos={"line": 10, "column": 5},
            session_id="session1",
        )
        
        resource_key = "conversation:1"
        cursor = collaboration_manager.presence[resource_key][1]["cursor_pos"]
        assert cursor["line"] == 10
        assert cursor["column"] == 5
        
        # Cleanup
        await collaboration_manager.leave_session("conversation", 1, 1, "session1")
    
    @pytest.mark.asyncio
    async def test_conflict_detection(self):
        """Test edit conflict detection."""
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        # Apply edit at version 1
        result1 = await collaboration_manager.apply_edit(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            edit_data={
                "version": 1,
                "operation": "insert",
                "text": "Hello",
            },
            session_id="session1",
        )
        
        assert result1["success"]
        assert result1["version"] == 2
        assert not result1["conflicts"]
        
        # Apply edit at old version (should detect conflict)
        result2 = await collaboration_manager.apply_edit(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            edit_data={
                "version": 1,  # Old version
                "operation": "insert",
                "text": "World",
            },
            session_id="session1",
        )
        
        assert result2["success"]
        assert result2["conflicts"]  # Conflict detected
        
        # Cleanup
        await collaboration_manager.leave_session("conversation", 1, 1, "session1")
    
    @pytest.mark.asyncio
    async def test_exclusive_lock(self):
        """Test acquiring and releasing exclusive locks."""
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        # Acquire lock
        success1 = await collaboration_manager.acquire_lock(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
        )
        assert success1
        
        # Try to acquire again (should fail)
        success2 = await collaboration_manager.acquire_lock(
            resource_type="conversation",
            resource_id=1,
            user_id=2,
        )
        assert not success2
        
        # Release lock
        await collaboration_manager.release_lock(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
        )
        
        # Now user 2 should be able to acquire
        success3 = await collaboration_manager.acquire_lock(
            resource_type="conversation",
            resource_id=1,
            user_id=2,
        )
        assert success3
        
        # Cleanup
        await collaboration_manager.release_lock("conversation", 1, 2)
        await collaboration_manager.leave_session("conversation", 1, 1, "session1")
    
    @pytest.mark.asyncio
    async def test_activity_feed(self):
        """Test activity feed tracking."""
        await collaboration_manager.join_session(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            username="user1",
            session_id="session1",
        )
        
        # Apply some edits
        await collaboration_manager.apply_edit(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            edit_data={"version": 1, "text": "Test 1"},
            session_id="session1",
        )
        
        await collaboration_manager.apply_edit(
            resource_type="conversation",
            resource_id=1,
            user_id=1,
            edit_data={"version": 2, "text": "Test 2"},
            session_id="session1",
        )
        
        # Get activity feed
        feed = await collaboration_manager.get_activity_feed(
            resource_type="conversation",
            resource_id=1,
            limit=10,
        )
        
        assert len(feed) >= 2  # At least join + 2 edits
        
        # Cleanup
        await collaboration_manager.leave_session("conversation", 1, 1, "session1")


class TestCollaborationAPI:
    """Test collaboration API endpoints."""
    
    def test_share_resource(self):
        """Test sharing a resource with users."""
        client = TestClient(app)
        
        response = client.post(
            "/api/v1/collaboration/share",
            params={"user_id": 1},
            json={
                "resource_type": "conversation",
                "resource_id": 1,
                "share_mode": "edit",
                "user_ids": [2, 3],
                "is_public": False,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        assert data["share_mode"] == "edit"
    
    def test_get_shared_resources(self):
        """Test getting shared resources."""
        client = TestClient(app)
        
        response = client.get(
            "/api/v1/collaboration/shared",
            params={"user_id": 1}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
    
    def test_collaboration_endpoints_integration(self):
        """Test full collaboration flow via API."""
        client = TestClient(app)
        
        # Share resource
        share_response = client.post(
            "/api/v1/collaboration/share",
            params={"user_id": 1},
            json={
                "resource_type": "conversation",
                "resource_id": 1,
                "share_mode": "edit",
                "user_ids": [2],
                "is_public": False,
            }
        )
        assert share_response.status_code == 200
        
        # Join session
        join_response = client.post(
            "/api/v1/collaboration/join",
            params={"user_id": 2},
            json={
                "resource_type": "conversation",
                "resource_id": 1,
                "username": "user2",
                "session_id": "test-session",
            }
        )
        assert join_response.status_code == 200
        
        # Apply edit
        edit_response = client.post(
            "/api/v1/collaboration/edit",
            params={"user_id": 2},
            json={
                "resource_type": "conversation",
                "resource_id": 1,
                "edit_data": {
                    "version": 1,
                    "text": "Test edit",
                },
                "session_id": "test-session",
            }
        )
        assert edit_response.status_code == 200
        
        # Get activity
        activity_response = client.get(
            "/api/v1/collaboration/activity/conversation/1"
        )
        assert activity_response.status_code == 200
        
        # Leave session
        leave_response = client.post(
            "/api/v1/collaboration/leave",
            params={"user_id": 2},
            json={
                "resource_type": "conversation",
                "resource_id": 1,
                "session_id": "test-session",
            }
        )
        assert leave_response.status_code == 200


class TestCollaborationViaWebSocket:
    """Test collaboration via WebSocket."""
    
    def test_collaborative_editing_websocket(self):
        """Test collaborative editing via WebSocket."""
        client = TestClient(app)
        
        # User 1 connects
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as ws1:
            # User 2 connects
            with client.websocket_connect("/api/v1/ws/connect?user_id=2") as ws2:
                # Clear welcome messages
                ws1.receive_json()
                ws2.receive_json()
                
                # Clear join events
                ws1.receive_json()  # user 2 joined
                ws2.receive_json()  # user 1 joined
                
                # Both subscribe to collaboration events
                ws1.send_json({
                    "action": "subscribe",
                    "channels": ["collab.*", "user.*"]
                })
                ws2.send_json({
                    "action": "subscribe",
                    "channels": ["collab.*", "user.*"]
                })
                
                # Clear subscription confirmations
                ws1.receive_json()
                ws2.receive_json()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
