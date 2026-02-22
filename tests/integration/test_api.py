"""
Integration tests for API endpoints
"""
import pytest
from httpx import AsyncClient


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test basic health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "environment" in data
    
    @pytest.mark.asyncio
    async def test_liveness_probe(self, client: AsyncClient):
        """Test Kubernetes liveness probe."""
        response = await client.get("/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
    
    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint returns API info."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Ironclaw API"
        assert "version" in data
        assert "docs" in data


class TestChatEndpoints:
    """Test chat API endpoints."""
    
    @pytest.mark.asyncio
    async def test_list_providers(self, client: AsyncClient):
        """Test listing available AI providers."""
        response = await client.get("/api/v1/chat/providers")
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "default" in data
        assert isinstance(data["providers"], list)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(
        True,  # Skip by default - requires API keys
        reason="Requires AI provider API keys"
    )
    async def test_chat_completion(self, client: AsyncClient):
        """Test chat completion endpoint (requires API key)."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Say 'Hello World' and nothing else"}
            ],
            "task_type": "conversation",
            "max_tokens": 10
        }
        
        response = await client.post("/api/v1/chat/", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "content" in data
        assert "provider" in data
        assert "model" in data
        assert "usage" in data
        assert "cost_usd" in data
        assert "response_time_ms" in data
        
        # Verify usage
        usage = data["usage"]
        assert usage["total_tokens"] > 0
        assert usage["prompt_tokens"] > 0
        assert usage["completion_tokens"] > 0
    
    @pytest.mark.asyncio
    async def test_chat_without_api_key_fails(self, client: AsyncClient):
        """Test that chat fails gracefully without API key."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Test"}
            ],
            "task_type": "conversation"
        }
        
        response = await client.post("/api/v1/chat/", json=request_data)
        # Should fail if no API keys are configured
        # Status code will be 503 (Service Unavailable) or 500
        assert response.status_code in [500, 503]
    
    @pytest.mark.asyncio
    async def test_chat_validation(self, client: AsyncClient):
        """Test request validation."""
        # Missing required field 'messages'
        request_data = {
            "task_type": "conversation"
        }
        
        response = await client.post("/api/v1/chat/", json=request_data)
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_invalid_task_type(self, client: AsyncClient):
        """Test validation of task_type enum."""
        request_data = {
            "messages": [
                {"role": "user", "content": "Test"}
            ],
            "task_type": "invalid_task_type"
        }
        
        response = await client.post("/api/v1/chat/", json=request_data)
        assert response.status_code == 422  # Validation error
