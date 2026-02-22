"""
LLM Streaming Tests
Test real-time LLM response streaming via WebSocket.
"""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.realtime.streaming import LLMStreamer, TypingIndicator
from src.realtime.events import WSEventType


class TestLLMStreaming:
    """Test LLM response streaming."""
    
    @pytest.mark.asyncio
    async def test_streamer_lifecycle(self):
        """Test LLMStreamer start, token, finish lifecycle."""
        streamer = LLMStreamer(
            conversation_id=1,
            user_id=1,
            session_id="test-session",
            message_id=1,
        )
        
        # Start stream
        await streamer.start()
        assert streamer.started_at is not None
        assert streamer.token_index == 0
        
        # Send tokens
        await streamer.send_token("Hello")
        await streamer.send_token(" ")
        await streamer.send_token("world")
        
        assert streamer.token_index == 3
        assert streamer.total_tokens == 3
        assert streamer.accumulated_text == "Hello world"
        
        # Finish stream
        await streamer.finish()
        assert streamer.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_streamer_error_handling(self):
        """Test error handling during streaming."""
        streamer = LLMStreamer(
            conversation_id=1,
            user_id=1,
        )
        
        await streamer.start()
        await streamer.send_token("Test")
        await streamer.error("Connection lost")
        
        # Should have partial text
        assert streamer.accumulated_text == "Test"
    
    def test_streaming_via_websocket(self):
        """Test streaming tokens via WebSocket."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Clear welcome message
            websocket.receive_json()
            
            # Subscribe to chat events
            websocket.send_json({
                "action": "subscribe",
                "channels": ["chat.stream.*"]
            })
            websocket.receive_json()  # subscription confirmation
            
            # Simulate streaming
            # In real scenario, this would come from AI provider
            # For test, we'll use the send_to_user API
            
            # Send stream start
            response = client.post(
                "/api/v1/ws/send-to-user/1",
                json={
                    "event_type": WSEventType.CHAT_STREAM_START,
                    "data": {
                        "conversation_id": 1,
                        "message_id": 1,
                    }
                }
            )
            
            # Receive stream start
            msg = websocket.receive_json()
            assert msg["event_type"] == WSEventType.CHAT_STREAM_START
    
    @pytest.mark.asyncio
    async def test_typing_indicator(self):
        """Test typing indicator context manager."""
        async with TypingIndicator(user_id=1, conversation_id=1):
            # Typing indicator should be active
            pass
        
        # Typing indicator should be stopped


class TestProgressStreaming:
    """Test task progress streaming."""
    
    @pytest.mark.asyncio
    async def test_progress_tracker(self):
        """Test ProgressTracker."""
        from src.realtime.progress import ProgressTracker
        
        async with ProgressTracker(
            task_name="Test task",
            user_id=1,
            total_steps=10,
            broadcast=False,  # Disable broadcast for unit test
        ) as tracker:
            # Update progress
            for i in range(10):
                await tracker.update(
                    completed_steps=i + 1,
                    current_step=f"Step {i+1}"
                )
            
            assert tracker.progress_percent == 100.0
            assert tracker.status == "completed"
    
    @pytest.mark.asyncio
    async def test_scan_progress_tracker(self):
        """Test ScanProgressTracker."""
        from src.realtime.progress import ScanProgressTracker
        
        tracker = ScanProgressTracker(
            task_name="Security scan",
            user_id=1,
            broadcast=False,
        )
        
        await tracker.start()
        
        # Report finding
        await tracker.finding({
            "type": "XSS",
            "severity": "high",
            "url": "https://example.com",
        })
        
        await tracker.update(progress_percent=50)
        await tracker.complete()
        
        assert tracker.status == "completed"
    
    def test_progress_via_websocket(self):
        """Test receiving progress updates via WebSocket."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Clear welcome
            websocket.receive_json()
            
            # Subscribe to task events
            websocket.send_json({
                "action": "subscribe",
                "channels": ["task.*"]
            })
            websocket.receive_json()  # confirmation
            
            # Send progress update
            client.post(
                "/api/v1/ws/send-to-user/1",
                json={
                    "event_type": WSEventType.TASK_PROGRESS,
                    "data": {
                        "task_id": "test-task",
                        "task_name": "Test Task",
                        "progress_percent": 50.0,
                        "status": "running",
                    }
                }
            )
            
            # Receive progress update
            msg = websocket.receive_json()
            assert msg["event_type"] == WSEventType.TASK_PROGRESS
            assert msg["data"]["progress_percent"] == 50.0


class TestSystemNotifications:
    """Test system notification streaming."""
    
    @pytest.mark.asyncio
    async def test_system_notification(self):
        """Test broadcasting system notifications."""
        from src.realtime.progress import broadcast_system_notification
        
        await broadcast_system_notification(
            user_id=1,
            title="Test Notification",
            message="This is a test",
            severity="info",
        )
    
    def test_system_notification_via_websocket(self):
        """Test receiving system notifications via WebSocket."""
        client = TestClient(app)
        
        with client.websocket_connect("/api/v1/ws/connect?user_id=1") as websocket:
            # Clear welcome
            websocket.receive_json()
            
            # Subscribe to system events
            websocket.send_json({
                "action": "subscribe",
                "channels": ["system.*"]
            })
            websocket.receive_json()
            
            # Send notification
            client.post(
                "/api/v1/ws/send-to-user/1",
                json={
                    "event_type": WSEventType.SYSTEM_NOTIFICATION,
                    "data": {
                        "severity": "warning",
                        "title": "Warning",
                        "message": "System maintenance in 1 hour",
                        "action_required": False,
                    }
                }
            )
            
            # Receive notification
            msg = websocket.receive_json()
            assert msg["event_type"] == WSEventType.SYSTEM_NOTIFICATION
            assert msg["data"]["severity"] == "warning"


@pytest.mark.performance
class TestStreamingPerformance:
    """Performance tests for streaming."""
    
    @pytest.mark.asyncio
    async def test_streaming_throughput(self):
        """Test streaming throughput (tokens/second)."""
        import time
        
        streamer = LLMStreamer(
            conversation_id=1,
            user_id=1,
        )
        
        await streamer.start()
        
        # Stream 1000 tokens
        start_time = time.time()
        for i in range(1000):
            await streamer.send_token(f"token{i} ")
        
        duration = time.time() - start_time
        tokens_per_second = 1000 / duration
        
        # Should handle at least 100 tokens/sec
        assert tokens_per_second > 100
        
        await streamer.finish()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
