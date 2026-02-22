"""
Performance benchmark tests for Ironclaw API
"""
import asyncio
import time
import statistics
import httpx
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Run performance benchmarks."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results: List[Dict] = []
    
    async def benchmark_endpoint(
        self,
        endpoint: str,
        method: str = "GET",
        iterations: int = 100,
        concurrent: int = 10,
        **kwargs
    ) -> Dict:
        """
        Benchmark a single endpoint.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method
            iterations: Total number of requests
            concurrent: Concurrent requests
            **kwargs: Additional arguments for httpx
        
        Returns:
            Dictionary with benchmark results
        """
        url = f"{self.base_url}{endpoint}"
        latencies = []
        errors = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            async def single_request():
                nonlocal errors
                start = time.time()
                try:
                    if method == "GET":
                        response = await client.get(url, **kwargs)
                    elif method == "POST":
                        response = await client.post(url, **kwargs)
                    else:
                        raise ValueError(f"Unsupported method: {method}")
                    
                    latency = time.time() - start
                    if response.status_code < 400:
                        latencies.append(latency)
                    else:
                        errors += 1
                except Exception as e:
                    logger.error(f"Request failed: {e}")
                    errors += 1
            
            # Run requests in batches of concurrent requests
            start_time = time.time()
            for i in range(0, iterations, concurrent):
                batch_size = min(concurrent, iterations - i)
                tasks = [single_request() for _ in range(batch_size)]
                await asyncio.gather(*tasks)
            
            total_time = time.time() - start_time
        
        if latencies:
            return {
                "endpoint": endpoint,
                "method": method,
                "iterations": iterations,
                "concurrent": concurrent,
                "total_time": total_time,
                "requests_per_second": iterations / total_time,
                "errors": errors,
                "success_rate": (iterations - errors) / iterations * 100,
                "latency_min": min(latencies) * 1000,  # ms
                "latency_max": max(latencies) * 1000,  # ms
                "latency_mean": statistics.mean(latencies) * 1000,  # ms
                "latency_median": statistics.median(latencies) * 1000,  # ms
                "latency_p95": statistics.quantiles(latencies, n=20)[18] * 1000,  # 95th percentile
                "latency_p99": statistics.quantiles(latencies, n=100)[98] * 1000,  # 99th percentile
            }
        else:
            return {
                "endpoint": endpoint,
                "method": method,
                "errors": errors,
                "success_rate": 0.0,
            }
    
    async def run_benchmarks(self):
        """Run all benchmarks."""
        logger.info("Starting Ironclaw API benchmarks...")
        
        # Benchmark health endpoints
        logger.info("Benchmarking health endpoints...")
        health_results = await self.benchmark_endpoint(
            "/health",
            iterations=1000,
            concurrent=50
        )
        self.results.append(health_results)
        
        ready_results = await self.benchmark_endpoint(
            "/health/ready",
            iterations=1000,
            concurrent=50
        )
        self.results.append(ready_results)
        
        # Benchmark chat endpoint
        logger.info("Benchmarking chat endpoint...")
        chat_results = await self.benchmark_endpoint(
            "/api/v1/chat",
            method="POST",
            iterations=100,
            concurrent=10,
            json={"prompt": "Hello", "task_type": "conversation"}
        )
        self.results.append(chat_results)
        
        # Benchmark providers endpoint
        logger.info("Benchmarking providers endpoint...")
        providers_results = await self.benchmark_endpoint(
            "/api/v1/chat/providers",
            iterations=500,
            concurrent=25
        )
        self.results.append(providers_results)
        
        # Benchmark plugins endpoint
        logger.info("Benchmarking plugins endpoint...")
        plugins_results = await self.benchmark_endpoint(
            "/api/v1/plugins",
            iterations=500,
            concurrent=25
        )
        self.results.append(plugins_results)
        
        self.print_results()
    
    def print_results(self):
        """Print benchmark results."""
        print("\n" + "="*80)
        print("IRONCLAW API BENCHMARK RESULTS")
        print("="*80)
        
        for result in self.results:
            print(f"\n{result['endpoint']} ({result['method']})")
            print("-" * 80)
            if "latency_mean" in result:
                print(f"Requests:           {result['iterations']}")
                print(f"Concurrent:         {result['concurrent']}")
                print(f"Total Time:         {result['total_time']:.2f}s")
                print(f"Requests/sec:       {result['requests_per_second']:.2f}")
                print(f"Errors:             {result['errors']}")
                print(f"Success Rate:       {result['success_rate']:.2f}%")
                print(f"\nLatency (ms):")
                print(f"  Min:              {result['latency_min']:.2f}")
                print(f"  Max:              {result['latency_max']:.2f}")
                print(f"  Mean:             {result['latency_mean']:.2f}")
                print(f"  Median:           {result['latency_median']:.2f}")
                print(f"  p95:              {result['latency_p95']:.2f}")
                print(f"  p99:              {result['latency_p99']:.2f}")
                
                # Check if performance targets are met
                if result['latency_p99'] > 100:
                    print(f"  ⚠️  WARNING: p99 latency exceeds 100ms target!")
                else:
                    print(f"  ✅ p99 latency within 100ms target")
            else:
                print(f"❌ All requests failed")
        
        print("\n" + "="*80)


async def main():
    """Main function."""
    runner = BenchmarkRunner()
    await runner.run_benchmarks()


if __name__ == "__main__":
    asyncio.run(main())
