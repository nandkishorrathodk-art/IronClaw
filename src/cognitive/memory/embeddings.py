"""
Embedding generation service
"""
from typing import List, Optional
import asyncio
from openai import AsyncOpenAI

from src.config import settings
from src.utils.logging import get_logger
from src.database.redis_client import cache_get, cache_set
import hashlib
import json

logger = get_logger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings.
    
    Features:
    - OpenAI text-embedding-3-small (fast, cheap)
    - Automatic caching to reduce API calls
    - Batch processing
    """
    
    def __init__(self):
        """Initialize embedding service."""
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for embeddings")
        
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"
        self.dimension = 1536
        self.cache_ttl = 86400 * 7  # 7 days
    
    async def embed_text(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            use_cache: Whether to use Redis cache (default: True)
            
        Returns:
            Embedding vector (1536 dimensions)
        """
        # Check cache
        if use_cache:
            cache_key = self._get_cache_key(text)
            cached = await cache_get(cache_key)
            if cached:
                logger.debug(f"Cache hit for embedding: {text[:50]}...")
                return json.loads(cached)
        
        # Generate embedding
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
                encoding_format="float"
            )
            
            embedding = response.data[0].embedding
            
            # Cache result
            if use_cache:
                await cache_set(cache_key, json.dumps(embedding), self.cache_ttl)
            
            logger.debug(f"Generated embedding: {text[:50]}...")
            return embedding
        
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    
    async def embed_batch(
        self,
        texts: List[str],
        use_cache: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.
        
        Args:
            texts: List of texts to embed
            use_cache: Whether to use Redis cache (default: True)
            
        Returns:
            List of embedding vectors
        """
        # Check cache for each text
        embeddings = []
        uncached_indices = []
        uncached_texts = []
        
        if use_cache:
            for i, text in enumerate(texts):
                cache_key = self._get_cache_key(text)
                cached = await cache_get(cache_key)
                
                if cached:
                    embeddings.append(json.loads(cached))
                else:
                    embeddings.append(None)
                    uncached_indices.append(i)
                    uncached_texts.append(text)
        else:
            uncached_indices = list(range(len(texts)))
            uncached_texts = texts
            embeddings = [None] * len(texts)
        
        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                # OpenAI API supports batch embedding
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=uncached_texts,
                    encoding_format="float"
                )
                
                # Extract embeddings and cache them
                for i, data in enumerate(response.data):
                    original_index = uncached_indices[i]
                    embedding = data.embedding
                    embeddings[original_index] = embedding
                    
                    # Cache
                    if use_cache:
                        cache_key = self._get_cache_key(uncached_texts[i])
                        await cache_set(cache_key, json.dumps(embedding), self.cache_ttl)
                
                logger.info(f"Generated {len(uncached_texts)} embeddings in batch")
            
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                raise
        
        return embeddings
    
    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        return f"embedding:{self.model}:{text_hash}"
    
    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        # Rough estimation: ~4 characters per token
        return len(text) // 4


# Global instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
