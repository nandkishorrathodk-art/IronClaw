"""
Locust load testing suite for Ironclaw API
Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000
"""
from locust import HttpUser, task, between
import json
import random


class IronclawUser(HttpUser):
    """Simulated user for load testing."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    def on_start(self):
        """Called when a simulated user starts."""
        # Login or setup if needed
        pass
    
    @task(5)  # Weight: 5 (most common)
    def health_check(self):
        """Test health endpoint."""
        self.client.get("/health")
    
    @task(3)
    def chat_request(self):
        """Test chat endpoint."""
        prompts = [
            "What is quantum computing?",
            "Explain async programming in Python",
            "What are best practices for API design?",
            "How does machine learning work?",
            "Explain Docker containers",
        ]
        
        with self.client.post(
            "/api/v1/chat",
            json={
                "prompt": random.choice(prompts),
                "task_type": "conversation",
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")
    
    @task(2)
    def get_providers(self):
        """Test providers endpoint."""
        self.client.get("/api/v1/chat/providers")
    
    @task(1)
    def cost_stats(self):
        """Test cost stats endpoint."""
        self.client.get("/api/v1/chat/cost-stats?hours=24")
    
    @task(2)
    def list_plugins(self):
        """Test plugin listing endpoint."""
        self.client.get("/api/v1/plugins")
    
    @task(1)
    def execute_plugin(self):
        """Test plugin execution."""
        self.client.post(
            "/api/v1/plugins/calculator/execute",
            json={"expression": "2 + 2 * 3"}
        )


class StressTestUser(HttpUser):
    """Heavy load user for stress testing."""
    
    wait_time = between(0.1, 0.5)  # Very short wait times
    
    @task
    def rapid_fire_requests(self):
        """Make rapid requests to stress test."""
        endpoints = [
            "/health",
            "/health/live",
            "/health/ready",
            "/api/v1/chat/providers",
        ]
        
        for endpoint in endpoints:
            self.client.get(endpoint)


class SpikeTestUser(HttpUser):
    """User for spike testing (sudden traffic bursts)."""
    
    wait_time = between(0, 0.1)  # Minimal wait time
    
    @task
    def spike_request(self):
        """Simulate traffic spike."""
        self.client.get("/health")
        self.client.get("/api/v1/chat/providers")
