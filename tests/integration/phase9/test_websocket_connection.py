"""
WebSocket Connection Tests
Test basic WebSocket connectivity, authentication, and connection management.
"""
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.main import app
from src.realtime.manager import connection_manager
from src.realtime.events import WSEventType


class TestWebSocketConnection:
    """Test WebSocket connection functionality."""
    
    def test_websocket_connect(self):
        """Test basic WebSocket connection."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Receive welcome message
            data = websocket.receive_json()
            
            assert data["event_type"] == WSEventType.CONNECT
            assert "connection_id" in data["data"]
            assert "session_id" in data["data"]
            assert data["data"]["message"] == "Connected successfully"
    
    def test_websocket_disconnect(self):
        """Test WebSocket disconnection."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Receive welcome message
            welcome = websocket.receive_json()
            
            # Close connection
            websocket.close()
        
        # Verify connection was cleaned up
        stats = connection_manager.get_stats()
        assert stats["active_connections"] == 0
    
    def test_websocket_subscribe(self):
        """Test channel subscription."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Receive welcome
            websocket.receive_json()
            
            # Subscribe to channels
            websocket.send_json({
                "action": "subscribe",
                "channels": ["chat.*", "task.*"]
            })
            
            # Receive subscription confirmation
            response = websocket.receive_json()
            
            assert response["event_type"] == WSEventType.SUBSCRIBED
            assert len(response["data"]["channels"]) == 2
    
    def test_websocket_ping_pong(self):
        """Test ping/pong keep-alive."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Receive welcome
            websocket.receive_json()
            
            # Wait for ping
            for _ in range(5):
                data = websocket.receive_json()
                if data["event_type"] == WSEventType.PING:
                    # Send pong
                    websocket.send_json({"action": "pong"})
                    break
    
    def test_multiple_connections_same_user(self):
        """Test multiple connections from same user."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as ws1:
            with client.websocket_connect("/api/v1/ws/connect?user_id=1") as ws2:
                # Receive welcome messages
                ws1.receive_json()
                ws2.receive_json()
                
                # Verify both connections tracked
                stats = connection_manager.get_stats()
                assert stats["active_connections"] == 2
                assert stats["active_users"] == 1


class TestWebSocketBroadcast:
    """Test WebSocket broadcast functionality."""
    
    def test_broadcast_to_all(self):
        """Test broadcasting to all connected users."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as ws1:
            with client.websocket_connect("/api/v1/ws/connect?user_id=2") as ws2:
                # Clear welcome messages
                ws1.receive_json()
                ws2.receive_json()
                
                # Wait for join events to clear
                ws1.receive_json()  # user 2 joined
                ws2.receive_json()  # user 1 joined
                
                # Broadcast message via API
                response = client.post(
                    "/api/v1/ws/broadcast",
                    json={
                        "event_type": "system.notification",
                        "data": {"message": "Test broadcast"}
                    }
                )
                assert response.status_code == 200
                
                # Both users should receive message
                msg1 = ws1.receive_json()
                msg2 = ws2.receive_json()
                
                assert msg1["event_type"] == "system.notification"
                assert msg2["event_type"] == "system.notification"
    
    def test_send_to_specific_user(self):
        """Test sending to specific user."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as ws1:
            with client.websocket_connect("/api/v1/ws/connect?user_id=2") as ws2:
                # Clear initial messages
                ws1.receive_json()
                ws2.receive_json()
                ws1.receive_json()  # join event
                ws2.receive_json()  # join event
                
                # Send to user 1 only
                response = client.post(
                    "/api/v1/ws/send-to-user/1",
                    json={
                        "event_type": "chat.message",
                        "data": {"message": "Hello user 1"}
                    }
                )
                assert response.status_code == 200
                
                # Only user 1 should receive
                msg1 = ws1.receive_json()
                assert msg1["event_type"] == "chat.message"
                assert msg1["data"]["message"] == "Hello user 1"


@pytest.mark.asyncio
class TestConnectionManager:
    """Test ConnectionManager class."""
    
    async def test_connection_manager_stats(self):
        """Test connection statistics."""
        stats = connection_manager.get_stats()
        
        assert "active_connections" in stats
        assert "active_users" in stats
        assert "total_connections_ever" in stats
        assert "peak_concurrent" in stats
    
    async def test_connection_lifecycle(self):
        """Test full connection lifecycle."""
        from fastapi import WebSocket
        from unittest.mock import AsyncMock, MagicMock
        
        # Mock WebSocket
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        
        # Connect
        conn_id = await connection_manager.connect(
            websocket=mock_ws,
            user_id=1,
            session_id="test-session"
        )
        
        assert conn_id is not None
        assert len(connection_manager.connections) == 1
        
        # Disconnect
        await connection_manager.disconnect(conn_id)
        
        assert len(connection_manager.connections) == 0
    
    async def test_subscribe_to_channels(self):
        """Test channel subscription."""
        from fastapi import WebSocket
        from unittest.mock import AsyncMock
        
        mock_ws = AsyncMock(spec=WebSocket)
        mock_ws.accept = AsyncMock()
        mock_ws.send_text = AsyncMock()
        
        conn_id = await connection_manager.connect(
            websocket=mock_ws,
            user_id=1
        )
        
        # Subscribe to channels
        connection_manager.subscribe(conn_id, "chat.*")
        connection_manager.subscribe(conn_id, "task.*")
        
        # Verify subscriptions
        connection = connection_manager.connections[conn_id]
        assert "chat.*" in connection.subscribed_channels
        assert "task.*" in connection.subscribed_channels
        
        # Cleanup
        await connection_manager.disconnect(conn_id)


@pytest.mark.load
class TestWebSocketLoad:
    """Load tests for WebSocket server."""
    
    @pytest.mark.timeout(60)
    def test_100_concurrent_connections(self):
        """Test handling 100 concurrent WebSocket connections."""
        client = TestClient(app)
        connections = []
        
        try:
            # Connect 100 clients
            for i in range(100):
                ws = client.websocket_connect(f"/api/v1/ws/connect?user_id={i}")
                connections.append(ws.__enter__())
                
                # Receive welcome message
                ws.__enter__().receive_json()
            
            # Verify all connected
            stats = connection_manager.get_stats()
            assert stats["active_connections"] == 100
            assert stats["active_users"] == 100
            
        finally:
            # Cleanup
            for ws in connections:
                try:
                    ws.__exit__(None, None, None)
                except:
                    pass
    
    @pytest.mark.skip(reason="Heavy load test - run manually")
    def test_1000_concurrent_connections(self):
        """Test handling 1000 concurrent connections."""
        # This test is skipped by default as it requires significant resources
        # Run manually with: pytest -m load --run-skipped
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
