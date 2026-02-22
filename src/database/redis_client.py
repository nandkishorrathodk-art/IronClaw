"""
Redis client for caching with async support
"""
import json
from typing import Any, Optional
from redis.asyncio import Redis, ConnectionPool
from src.config import settings
from src.utils.logging import get_logger
from src.utils.metrics import cache_operations_total

logger = get_logger(__name__)

# Global Redis client
redis_client: Optional[Redis] = None
connection_pool: Optional[ConnectionPool] = None


async def init_redis() -> None:
    """
    Initialize Redis connection pool and client.
    Called during application startup.
    """
    global redis_client, connection_pool
    
    logger.info(f"Initializing Redis connection to: {settings.redis_url}")
    
    # Create connection pool
    connection_pool = ConnectionPool.from_url(
        settings.redis_url,
        max_connections=settings.redis_max_connections,
        decode_responses=True,  # Automatically decode bytes to strings
    )
    
    # Create Redis client
    redis_client = Redis(connection_pool=connection_pool)
    
    # Test connection
    try:
        await redis_client.ping()
        logger.info("✅ Redis initialized successfully")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def close_redis() -> None:
    """
    Close Redis connections.
    Called during application shutdown.
    """
    global redis_client, connection_pool
    
    if redis_client:
        logger.info("Closing Redis connections...")
        await redis_client.close()
        logger.info("✅ Redis connections closed")
    
    if connection_pool:
        await connection_pool.disconnect()


async def get_redis() -> Redis:
    """
    Get Redis client instance.
    Raises RuntimeError if Redis is not initialized.
    """
    if redis_client is None:
        raise RuntimeError("Redis not initialized. Call init_redis() first.")
    return redis_client


async def cache_get(key: str) -> Optional[Any]:
    """
    Get value from cache.
    
    Args:
        key: Cache key
        
    Returns:
        Cached value (deserialized from JSON) or None if not found
    """
    redis = await get_redis()
    
    try:
        value = await redis.get(key)
        
        if value is None:
            cache_operations_total.labels(operation="get", result="miss").inc()
            return None
        
        cache_operations_total.labels(operation="get", result="hit").inc()
        
        # Try to deserialize JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Return as-is if not JSON
            return value
            
    except Exception as e:
        logger.error(f"Cache get error for key '{key}': {e}")
        return None


async def cache_set(
    key: str,
    value: Any,
    ttl: Optional[int] = None
) -> bool:
    """
    Set value in cache.
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized if not a string)
        ttl: Time to live in seconds (default: from settings)
        
    Returns:
        True if successful, False otherwise
    """
    redis = await get_redis()
    ttl = ttl or settings.redis_cache_ttl
    
    try:
        # Serialize to JSON if not a string
        if not isinstance(value, str):
            value = json.dumps(value)
        
        await redis.setex(key, ttl, value)
        cache_operations_total.labels(operation="set", result="success").inc()
        return True
        
    except Exception as e:
        logger.error(f"Cache set error for key '{key}': {e}")
        cache_operations_total.labels(operation="set", result="error").inc()
        return False


async def cache_delete(key: str) -> bool:
    """
    Delete value from cache.
    
    Args:
        key: Cache key
        
    Returns:
        True if key was deleted, False otherwise
    """
    redis = await get_redis()
    
    try:
        deleted = await redis.delete(key)
        cache_operations_total.labels(
            operation="delete",
            result="success" if deleted else "miss"
        ).inc()
        return bool(deleted)
        
    except Exception as e:
        logger.error(f"Cache delete error for key '{key}': {e}")
        cache_operations_total.labels(operation="delete", result="error").inc()
        return False


async def cache_exists(key: str) -> bool:
    """
    Check if key exists in cache.
    
    Args:
        key: Cache key
        
    Returns:
        True if key exists, False otherwise
    """
    redis = await get_redis()
    
    try:
        exists = await redis.exists(key)
        return bool(exists)
    except Exception as e:
        logger.error(f"Cache exists error for key '{key}': {e}")
        return False


async def cache_clear_pattern(pattern: str) -> int:
    """
    Delete all keys matching pattern.
    
    Args:
        pattern: Key pattern (e.g., "user:*" for all user keys)
        
    Returns:
        Number of keys deleted
    """
    redis = await get_redis()
    
    try:
        keys = []
        async for key in redis.scan_iter(match=pattern, count=100):
            keys.append(key)
        
        if keys:
            deleted = await redis.delete(*keys)
            logger.info(f"Cleared {deleted} keys matching pattern '{pattern}'")
            return deleted
        
        return 0
        
    except Exception as e:
        logger.error(f"Cache clear pattern error for '{pattern}': {e}")
        return 0


async def check_redis_health() -> bool:
    """
    Check if Redis connection is healthy.
    Used for readiness probes.
    """
    try:
        if redis_client is None:
            return False
        
        await redis_client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False
