"""
Web Search Plugin
Searches the web using DuckDuckGo API with caching and rate limiting
"""
import asyncio
import hashlib
import time
from datetime import datetime
from typing import Any, Optional

from duckduckgo_search import DDGS

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class WebSearchPlugin(IPlugin):
    """
    Search the web using DuckDuckGo.

    Features:
    - DuckDuckGo API integration (no API key required)
    - Result caching (1 hour TTL)
    - Rate limiting (max 10 requests/minute)
    - Safe search enabled by default
    """

    def __init__(self) -> None:
        """Initialize web search plugin."""
        metadata = PluginMetadata(
            name="web_search",
            version="1.0.0",
            description="Search the web using DuckDuckGo API",
            author="Ironclaw Team",
            dependencies=[],
            max_execution_time_seconds=10,
            max_memory_mb=256,
            max_cpu_percent=30.0,
            requires_network=True,
            allowed_domains=["duckduckgo.com"],
            requires_permissions=["network.http"],
            enabled=True,
            tags=["search", "web", "duckduckgo"],
        )
        super().__init__(metadata)

        # Cache: query_hash -> (results, timestamp)
        self._cache: dict[str, tuple[list[dict[str, str]], float]] = {}

        # Rate limiting: timestamps of recent requests
        self._request_times: list[float] = []
        self._max_requests_per_minute = 10
        self._cache_ttl_seconds = 3600  # 1 hour

    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Execute web search.

        Args:
            query: Search query string (required)
            max_results: Maximum number of results (default: 5, max: 20)
            region: Region code (default: "wt-wt" for worldwide)
            safe_search: Enable safe search (default: True)

        Returns:
            PluginResult with search results
        """
        start_time = time.time()

        try:
            # Extract parameters
            query = kwargs.get("query", "").strip()
            max_results = min(int(kwargs.get("max_results", 5)), 20)
            region = kwargs.get("region", "wt-wt")
            safe_search = kwargs.get("safe_search", True)

            if not query:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="Query parameter is required",
                )

            # Check rate limit
            if not await self._check_rate_limit():
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="Rate limit exceeded. Max 10 requests per minute.",
                )

            # Check cache
            cache_key = self._get_cache_key(query, max_results, region)
            cached_results = self._get_cached_results(cache_key)

            if cached_results is not None:
                execution_time_ms = int((time.time() - start_time) * 1000)
                return PluginResult(
                    status=PluginStatus.SUCCESS,
                    data={
                        "query": query,
                        "results": cached_results,
                        "cached": True,
                        "result_count": len(cached_results),
                    },
                    execution_time_ms=execution_time_ms,
                    metadata={"source": "cache"},
                )

            # Perform search
            results = await self._search_duckduckgo(
                query=query,
                max_results=max_results,
                region=region,
                safe_search=safe_search,
            )

            # Cache results
            self._cache_results(cache_key, results)

            execution_time_ms = int((time.time() - start_time) * 1000)

            return PluginResult(
                status=PluginStatus.SUCCESS,
                data={
                    "query": query,
                    "results": results,
                    "cached": False,
                    "result_count": len(results),
                },
                execution_time_ms=execution_time_ms,
                metadata={"source": "duckduckgo"},
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Search failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate search parameters.

        Args:
            query: Search query (required)
            max_results: Maximum results (optional, 1-20)

        Returns:
            True if valid, False otherwise
        """
        query = kwargs.get("query", "").strip()
        if not query:
            return False

        if len(query) > 500:
            return False

        max_results = kwargs.get("max_results")
        if max_results is not None:
            try:
                max_results = int(max_results)
                if max_results < 1 or max_results > 20:
                    return False
            except (ValueError, TypeError):
                return False

        return True

    async def cleanup(self) -> None:
        """Cleanup cache and rate limit data."""
        self._cache.clear()
        self._request_times.clear()

    async def _search_duckduckgo(
        self,
        query: str,
        max_results: int = 5,
        region: str = "wt-wt",
        safe_search: bool = True,
    ) -> list[dict[str, str]]:
        """
        Search using DuckDuckGo API.

        Args:
            query: Search query
            max_results: Maximum number of results
            region: Region code
            safe_search: Enable safe search

        Returns:
            List of search results
        """
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: self._search_sync(query, max_results, region, safe_search),
        )

        return results

    def _search_sync(
        self,
        query: str,
        max_results: int,
        region: str,
        safe_search: bool,
    ) -> list[dict[str, str]]:
        """
        Synchronous search function (runs in executor).

        Args:
            query: Search query
            max_results: Maximum results
            region: Region code
            safe_search: Enable safe search

        Returns:
            List of search results
        """
        ddgs = DDGS()
        results = []

        safesearch = "on" if safe_search else "off"

        # Search with DuckDuckGo
        search_results = ddgs.text(
            keywords=query,
            region=region,
            safesearch=safesearch,
            max_results=max_results,
        )

        for result in search_results:
            results.append(
                {
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                }
            )

        return results

    async def _check_rate_limit(self) -> bool:
        """
        Check if rate limit allows new request.

        Returns:
            True if request allowed, False if rate limited
        """
        current_time = time.time()

        # Remove requests older than 1 minute
        self._request_times = [
            t for t in self._request_times if current_time - t < 60
        ]

        # Check if limit exceeded
        if len(self._request_times) >= self._max_requests_per_minute:
            return False

        # Add current request
        self._request_times.append(current_time)
        return True

    def _get_cache_key(self, query: str, max_results: int, region: str) -> str:
        """
        Generate cache key for query.

        Args:
            query: Search query
            max_results: Maximum results
            region: Region code

        Returns:
            Cache key (hash)
        """
        cache_input = f"{query}|{max_results}|{region}"
        return hashlib.md5(cache_input.encode()).hexdigest()

    def _get_cached_results(
        self, cache_key: str
    ) -> Optional[list[dict[str, str]]]:
        """
        Get results from cache if not expired.

        Args:
            cache_key: Cache key

        Returns:
            Cached results or None if expired/not found
        """
        if cache_key not in self._cache:
            return None

        results, timestamp = self._cache[cache_key]

        # Check if expired
        if time.time() - timestamp > self._cache_ttl_seconds:
            del self._cache[cache_key]
            return None

        return results

    def _cache_results(
        self, cache_key: str, results: list[dict[str, str]]
    ) -> None:
        """
        Cache search results.

        Args:
            cache_key: Cache key
            results: Search results to cache
        """
        self._cache[cache_key] = (results, time.time())
