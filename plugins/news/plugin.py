"""
News Plugin
Fetches latest news articles using NewsAPI (free tier)
"""
import os
import time
from typing import Any

import httpx

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class NewsPlugin(IPlugin):
    """
    News articles plugin using NewsAPI.

    Features:
    - Top headlines by country/category
    - Search news by keyword
    - Multiple languages supported
    - Free tier: 100 requests/day
    """

    def __init__(self) -> None:
        """Initialize news plugin."""
        metadata = PluginMetadata(
            name="news",
            version="1.0.0",
            description="Get latest news articles using NewsAPI",
            author="Ironclaw Team",
            dependencies=[],
            max_execution_time_seconds=10,
            max_memory_mb=128,
            max_cpu_percent=20.0,
            requires_network=True,
            allowed_domains=["newsapi.org"],
            requires_permissions=["network.http"],
            enabled=True,
            tags=["news", "api", "utility"],
        )
        super().__init__(metadata)

        # API configuration
        self.api_key = os.getenv("NEWSAPI_KEY", "")
        self.base_url = "https://newsapi.org/v2"

    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Get news articles.

        Args:
            mode: "headlines" or "search" (default: "headlines")
            query: Search query (required for search mode)
            category: Category for headlines - business, entertainment, general,
                     health, science, sports, technology (default: "general")
            country: Country code - us, gb, ca, au, etc. (default: "us")
            language: Language code - en, es, fr, de, etc. (default: "en")
            max_results: Maximum articles to return (default: 10, max: 100)

        Returns:
            PluginResult with news articles
        """
        start_time = time.time()

        try:
            # Check API key
            if not self.api_key:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error="NewsAPI key not configured. "
                    "Set NEWSAPI_KEY environment variable. "
                    "Get free key at: https://newsapi.org/register",
                )

            # Extract parameters
            mode = kwargs.get("mode", "headlines").lower()
            query = kwargs.get("query", "").strip()
            category = kwargs.get("category", "general")
            country = kwargs.get("country", "us")
            language = kwargs.get("language", "en")
            max_results = min(int(kwargs.get("max_results", 10)), 100)

            # Fetch news
            if mode == "search":
                if not query:
                    return PluginResult(
                        status=PluginStatus.FAILED,
                        error="Query parameter is required for search mode",
                    )
                data = await self._search_news(query, language, max_results)
            else:
                data = await self._get_headlines(
                    category, country, max_results
                )

            execution_time_ms = int((time.time() - start_time) * 1000)

            return PluginResult(
                status=PluginStatus.SUCCESS,
                data=data,
                execution_time_ms=execution_time_ms,
            )

        except httpx.HTTPStatusError as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"API error: {e.response.status_code} - {e.response.text}",
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"News fetch failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate news request parameters.

        Args:
            mode: Mode (headlines or search)
            query: Search query (if mode is search)

        Returns:
            True if valid, False otherwise
        """
        mode = kwargs.get("mode", "headlines").lower()
        if mode not in ("headlines", "search"):
            return False

        if mode == "search":
            query = kwargs.get("query", "").strip()
            if not query or len(query) > 500:
                return False

        category = kwargs.get("category", "general")
        if category not in (
            "business",
            "entertainment",
            "general",
            "health",
            "science",
            "sports",
            "technology",
        ):
            return False

        return True

    async def _get_headlines(
        self, category: str, country: str, max_results: int
    ) -> dict[str, Any]:
        """
        Get top headlines.

        Args:
            category: News category
            country: Country code
            max_results: Maximum articles

        Returns:
            Dictionary with news articles
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/top-headlines",
                params={
                    "apiKey": self.api_key,
                    "category": category,
                    "country": country,
                    "pageSize": max_results,
                },
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()

        articles = []
        for article in data.get("articles", []):
            articles.append(
                {
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "url": article.get("url", ""),
                    "source": article.get("source", {}).get("name", ""),
                    "published_at": article.get("publishedAt", ""),
                    "author": article.get("author", "Unknown"),
                }
            )

        return {
            "mode": "headlines",
            "category": category,
            "country": country,
            "articles": articles,
            "article_count": len(articles),
            "total_results": data.get("totalResults", 0),
        }

    async def _search_news(
        self, query: str, language: str, max_results: int
    ) -> dict[str, Any]:
        """
        Search news articles.

        Args:
            query: Search query
            language: Language code
            max_results: Maximum articles

        Returns:
            Dictionary with news articles
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/everything",
                params={
                    "apiKey": self.api_key,
                    "q": query,
                    "language": language,
                    "pageSize": max_results,
                    "sortBy": "publishedAt",
                },
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()

        articles = []
        for article in data.get("articles", []):
            articles.append(
                {
                    "title": article.get("title", ""),
                    "description": article.get("description", ""),
                    "url": article.get("url", ""),
                    "source": article.get("source", {}).get("name", ""),
                    "published_at": article.get("publishedAt", ""),
                    "author": article.get("author", "Unknown"),
                }
            )

        return {
            "mode": "search",
            "query": query,
            "language": language,
            "articles": articles,
            "article_count": len(articles),
            "total_results": data.get("totalResults", 0),
        }

    async def cleanup(self) -> None:
        """No cleanup needed for news plugin."""
        pass
