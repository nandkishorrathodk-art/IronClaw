"""
Qdrant vector database client for semantic memory
"""
from typing import List, Optional, Dict, Any, Tuple
import hashlib
from datetime import datetime
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchParams,
)
from qdrant_client.http.exceptions import UnexpectedResponse

from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class VectorStore:
    """
    Qdrant vector database client for semantic search.
    
    Features:
    - Store and retrieve conversation embeddings
    - Fast similarity search (<50ms)
    - Metadata filtering
    - Automatic deduplication
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "conversations"
    ):
        """
        Initialize Qdrant client.
        
        Args:
            host: Qdrant host (default: localhost)
            port: Qdrant port (default: 6333)
            collection_name: Collection name (default: conversations)
        """
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.embedding_dimension = 1536  # text-embedding-3-small dimension
        
        logger.info(f"Initializing VectorStore: {host}:{port}, collection={collection_name}")
    
    async def initialize_collection(self, recreate: bool = False) -> None:
        """
        Initialize Qdrant collection.
        
        Args:
            recreate: If True, delete and recreate collection
        """
        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if exists and recreate:
                logger.info(f"Deleting existing collection: {self.collection_name}")
                self.client.delete_collection(collection_name=self.collection_name)
                exists = False
            
            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"✅ Collection created: {self.collection_name}")
            else:
                logger.info(f"✅ Collection exists: {self.collection_name}")
        
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            raise
    
    def add_embedding(
        self,
        embedding: List[float],
        text: str,
        metadata: Dict[str, Any]
    ) -> str:
        """
        Add an embedding to the vector store.
        
        Args:
            embedding: Vector embedding (1536 dimensions)
            text: Original text
            metadata: Additional metadata (user_id, conversation_id, etc.)
            
        Returns:
            Point ID of inserted embedding
        """
        # Generate content hash for deduplication
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        
        # Check if this content already exists
        existing = self._find_by_hash(content_hash)
        if existing:
            logger.debug(f"Skipping duplicate content: {content_hash[:16]}...")
            return existing
        
        # Generate unique point ID
        point_id = str(uuid.uuid4())
        
        # Prepare payload
        payload = {
            "text": text,
            "content_hash": content_hash,
            "created_at": datetime.utcnow().isoformat(),
            **metadata
        }
        
        # Insert into Qdrant
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )
            logger.debug(f"Added embedding: {point_id}")
            return point_id
        
        except Exception as e:
            logger.error(f"Failed to add embedding: {e}")
            raise
    
    def add_batch(
        self,
        embeddings: List[List[float]],
        texts: List[str],
        metadatas: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Add multiple embeddings in batch.
        
        Args:
            embeddings: List of vector embeddings
            texts: List of original texts
            metadatas: List of metadata dicts
            
        Returns:
            List of point IDs
        """
        if not (len(embeddings) == len(texts) == len(metadatas)):
            raise ValueError("embeddings, texts, and metadatas must have same length")
        
        points = []
        point_ids = []
        
        for embedding, text, metadata in zip(embeddings, texts, metadatas):
            # Generate content hash
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            
            # Skip if duplicate
            existing = self._find_by_hash(content_hash)
            if existing:
                point_ids.append(existing)
                continue
            
            # Generate point ID
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)
            
            # Prepare payload
            payload = {
                "text": text,
                "content_hash": content_hash,
                "created_at": datetime.utcnow().isoformat(),
                **metadata
            }
            
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload
                )
            )
        
        # Batch upsert
        if points:
            try:
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points
                )
                logger.info(f"Added {len(points)} embeddings in batch")
            except Exception as e:
                logger.error(f"Batch upsert failed: {e}")
                raise
        
        return point_ids
    
    def search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        score_threshold: float = 0.7,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[str, float, Dict[str, Any]]]:
        """
        Search for similar embeddings.
        
        Args:
            query_embedding: Query vector
            limit: Maximum results to return (default: 5)
            score_threshold: Minimum similarity score (default: 0.7)
            filter_dict: Optional metadata filters (e.g., {"user_id": 123})
            
        Returns:
            List of (text, score, metadata) tuples
        """
        # Build filter
        query_filter = None
        if filter_dict:
            conditions = [
                FieldCondition(
                    key=key,
                    match=MatchValue(value=value)
                )
                for key, value in filter_dict.items()
            ]
            query_filter = Filter(must=conditions)
        
        # Search
        try:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                search_params=SearchParams(
                    exact=False,  # Use HNSW index for speed
                    hnsw_ef=128
                )
            )
            
            # Extract results
            matches = []
            for hit in results:
                text = hit.payload.get("text", "")
                score = hit.score
                metadata = {k: v for k, v in hit.payload.items() if k != "text"}
                matches.append((text, score, metadata))
            
            logger.debug(f"Found {len(matches)} similar embeddings (threshold={score_threshold})")
            return matches
        
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    def _find_by_hash(self, content_hash: str) -> Optional[str]:
        """
        Find existing point by content hash.
        
        Args:
            content_hash: SHA-256 hash of content
            
        Returns:
            Point ID if found, None otherwise
        """
        try:
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="content_hash",
                            match=MatchValue(value=content_hash)
                        )
                    ]
                ),
                limit=1
            )
            
            if results[0]:  # results is tuple (points, next_offset)
                return str(results[0][0].id)
            
            return None
        
        except Exception:
            return None
    
    def delete_by_metadata(self, filter_dict: Dict[str, Any]) -> int:
        """
        Delete points by metadata filter.
        
        Args:
            filter_dict: Metadata filters (e.g., {"conversation_id": 123})
            
        Returns:
            Number of points deleted
        """
        conditions = [
            FieldCondition(
                key=key,
                match=MatchValue(value=value)
            )
            for key, value in filter_dict.items()
        ]
        
        try:
            # Scroll to find matching points
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=conditions),
                limit=1000
            )
            
            point_ids = [str(point.id) for point in results[0]]
            
            if point_ids:
                self.client.delete(
                    collection_name=self.collection_name,
                    points_selector=point_ids
                )
                logger.info(f"Deleted {len(point_ids)} points")
            
            return len(point_ids)
        
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return 0
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        try:
            info = self.client.get_collection(collection_name=self.collection_name)
            return {
                "name": self.collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status,
            }
        except Exception as e:
            logger.error(f"Failed to get collection info: {e}")
            return {}


# Global instance
_vector_store: Optional[VectorStore] = None


def get_vector_store(collection_name: str = "conversations") -> VectorStore:
    """
    Get global vector store instance.
    
    Args:
        collection_name: Collection to use
        
    Returns:
        VectorStore instance
    """
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            collection_name=collection_name
        )
    return _vector_store
