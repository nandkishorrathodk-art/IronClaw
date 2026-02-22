"""
Chaos engineering tests for Ironclaw
Test system resilience under failure conditions
"""
import asyncio
import httpx
import logging
import random
import time
from typing import Callable, List
import psutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChaosTest:
    """Base class for chaos tests."""
    
    def __init__(self, name: str, base_url: str = "http://localhost:8000"):
        self.name = name
        self.base_url = base_url
        self.results = []
    
    async def run(self) -> bool:
        """Run the chaos test."""
        raise NotImplementedError
    
    async def verify_health(self) -> bool:
        """Verify system is healthy."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.base_url}/health/ready")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class NetworkLatencyChaos(ChaosTest):
    """Test system behavior under network latency."""
    
    async def run(self) -> bool:
        """Simulate network latency and test response."""
        logger.info(f"Running {self.name}...")
        
        # Make requests with artificial delays
        delays = [0, 0.1, 0.5, 1.0, 2.0]
        
        for delay in delays:
            logger.info(f"Testing with {delay}s artificial delay...")
            await asyncio.sleep(delay)
            
            is_healthy = await self.verify_health()
            self.results.append({
                "delay": delay,
                "healthy": is_healthy
            })
            
            if not is_healthy:
                logger.error(f"System unhealthy with {delay}s delay!")
                return False
        
        logger.info(f"✅ {self.name} passed")
        return True


class HighLoadChaos(ChaosTest):
    """Test system under high load."""
    
    async def run(self) -> bool:
        """Generate high load and monitor system."""
        logger.info(f"Running {self.name}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Generate 1000 concurrent requests
            tasks = []
            for i in range(1000):
                task = client.get(f"{self.base_url}/health")
                tasks.append(task)
            
            start = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            duration = time.time() - start
            
            # Count successful responses
            successful = sum(
                1 for r in responses
                if isinstance(r, httpx.Response) and r.status_code == 200
            )
            
            success_rate = successful / len(responses) * 100
            logger.info(f"Success rate: {success_rate:.2f}%")
            logger.info(f"Duration: {duration:.2f}s")
            logger.info(f"Requests/sec: {len(responses)/duration:.2f}")
            
            # System should handle at least 90% of requests
            if success_rate < 90:
                logger.error(f"❌ Success rate below 90%!")
                return False
        
        logger.info(f"✅ {self.name} passed")
        return True


class MemoryPressureChaos(ChaosTest):
    """Test system under memory pressure."""
    
    async def run(self) -> bool:
        """Monitor system under memory pressure."""
        logger.info(f"Running {self.name}...")
        
        # Monitor memory usage before load
        initial_memory = psutil.virtual_memory().percent
        logger.info(f"Initial memory usage: {initial_memory:.2f}%")
        
        # Generate load
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for i in range(100):
                # Make requests that might allocate memory
                task = client.post(
                    f"{self.base_url}/api/v1/chat",
                    json={
                        "prompt": "Explain quantum computing in detail",
                        "task_type": "conversation"
                    }
                )
                tasks.append(task)
            
            await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check memory usage after load
        final_memory = psutil.virtual_memory().percent
        logger.info(f"Final memory usage: {final_memory:.2f}%")
        
        # Memory should not increase more than 20%
        memory_increase = final_memory - initial_memory
        if memory_increase > 20:
            logger.error(f"❌ Memory increased by {memory_increase:.2f}%!")
            return False
        
        logger.info(f"✅ {self.name} passed")
        return True


class DatabaseConnectionChaos(ChaosTest):
    """Test system when database connections are stressed."""
    
    async def run(self) -> bool:
        """Stress database connections."""
        logger.info(f"Running {self.name}...")
        
        # Make many concurrent requests that hit the database
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            for i in range(200):
                task = client.get(f"{self.base_url}/api/v1/chat/cost-stats?hours=1")
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count successful responses
            successful = sum(
                1 for r in responses
                if isinstance(r, httpx.Response) and r.status_code == 200
            )
            
            success_rate = successful / len(responses) * 100
            logger.info(f"Success rate: {success_rate:.2f}%")
            
            # Should handle at least 95% of requests
            if success_rate < 95:
                logger.error(f"❌ Success rate below 95%!")
                return False
        
        logger.info(f"✅ {self.name} passed")
        return True


class RandomFailureChaos(ChaosTest):
    """Test system resilience to random failures."""
    
    async def run(self) -> bool:
        """Simulate random failures and check recovery."""
        logger.info(f"Running {self.name}...")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            endpoints = [
                "/health",
                "/api/v1/chat/providers",
                "/api/v1/plugins",
            ]
            
            failures = 0
            successes = 0
            
            for i in range(100):
                endpoint = random.choice(endpoints)
                
                try:
                    # Randomly timeout some requests
                    timeout = 0.1 if random.random() < 0.1 else 5.0
                    
                    response = await client.get(
                        f"{self.base_url}{endpoint}",
                        timeout=timeout
                    )
                    
                    if response.status_code == 200:
                        successes += 1
                    else:
                        failures += 1
                
                except Exception as e:
                    failures += 1
                
                # Small delay between requests
                await asyncio.sleep(0.01)
            
            success_rate = successes / (successes + failures) * 100
            logger.info(f"Success rate: {success_rate:.2f}%")
            
            # Should handle at least 80% under random failures
            if success_rate < 80:
                logger.error(f"❌ Success rate below 80%!")
                return False
        
        logger.info(f"✅ {self.name} passed")
        return True


async def run_all_chaos_tests():
    """Run all chaos engineering tests."""
    tests = [
        NetworkLatencyChaos("Network Latency Test"),
        HighLoadChaos("High Load Test"),
        MemoryPressureChaos("Memory Pressure Test"),
        DatabaseConnectionChaos("Database Connection Test"),
        RandomFailureChaos("Random Failure Test"),
    ]
    
    print("\n" + "="*80)
    print("IRONCLAW CHAOS ENGINEERING TESTS")
    print("="*80 + "\n")
    
    results = []
    for test in tests:
        try:
            result = await test.run()
            results.append((test.name, result))
        except Exception as e:
            logger.error(f"Test {test.name} crashed: {e}")
            results.append((test.name, False))
        
        # Give system time to recover between tests
        await asyncio.sleep(2)
    
    # Print summary
    print("\n" + "="*80)
    print("CHAOS TEST SUMMARY")
    print("="*80)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nTotal: {total_passed}/{len(results)} passed")
    print("="*80 + "\n")
    
    return all(passed for _, passed in results)


if __name__ == "__main__":
    success = asyncio.run(run_all_chaos_tests())
    exit(0 if success else 1)
