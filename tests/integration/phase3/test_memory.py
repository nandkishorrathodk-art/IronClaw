"""
Integration tests for semantic memory and context management
"""
import pytest
from src.cognitive.memory.vector_store import VectorStore
from src.cognitive.memory.embeddings import EmbeddingService
from src.cognitive.memory.semantic_memory import SemanticMemory
from src.cognitive.memory.context_manager import ContextManager
from src.cognitive.llm.types import Message, MessageRole


class TestVectorStore:
    """Tests for Qdrant vector store."""
    
    @pytest.fixture
    async def vector_store(self):
        """Create vector store for testing."""
        store = VectorStore(collection_name="test_collection")
        await store.initialize_collection(recreate=True)
        yield store
        # Cleanup not needed - collection will be recreated
    
    @pytest.mark.asyncio
    async def test_add_and_search_embedding(self, vector_store):
        """Test adding and searching embeddings."""
        # Create mock embedding (1536 dimensions)
        embedding = [0.1] * 1536
        
        # Add embedding
        point_id = vector_store.add_embedding(
            embedding=embedding,
            text="The quick brown fox jumps over the lazy dog",
            metadata={"category": "test", "conversation_id": 1}
        )
        
        assert point_id
        
        # Search for similar (using same embedding)
        results = vector_store.search(
            query_embedding=embedding,
            limit=5,
            score_threshold=0.9
        )
        
        assert len(results) > 0
        assert results[0][1] > 0.9  # Score should be high (same embedding)
    
    @pytest.mark.asyncio
    async def test_deduplication(self, vector_store):
        """Test that duplicate content is not added twice."""
        embedding = [0.2] * 1536
        text = "Test deduplication content"
        
        # Add first time
        point_id_1 = vector_store.add_embedding(
            embedding=embedding,
            text=text,
            metadata={"test": 1}
        )
        
        # Add second time (same text)
        point_id_2 = vector_store.add_embedding(
            embedding=embedding,
            text=text,
            metadata={"test": 2}
        )
        
        # Should return same point ID
        assert point_id_1 == point_id_2
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, vector_store):
        """Test batch adding embeddings."""
        embeddings = [[0.1 * i] * 1536 for i in range(1, 4)]
        texts = [f"Test text {i}" for i in range(1, 4)]
        metadatas = [{"index": i} for i in range(1, 4)]
        
        point_ids = vector_store.add_batch(
            embeddings=embeddings,
            texts=texts,
            metadatas=metadatas
        )
        
        assert len(point_ids) == 3
        
        # Verify we can search
        results = vector_store.search(
            query_embedding=embeddings[0],
            limit=5
        )
        assert len(results) > 0


class TestEmbeddingService:
    """Tests for embedding generation."""
    
    @pytest.fixture
    def embedding_service(self):
        """Create embedding service."""
        return EmbeddingService()
    
    @pytest.mark.asyncio
    async def test_single_embedding(self, embedding_service):
        """Test generating single embedding."""
        text = "Test embedding generation"
        
        embedding = await embedding_service.embed_text(text)
        
        assert len(embedding) == 1536  # text-embedding-3-small dimension
        assert all(isinstance(x, float) for x in embedding)
    
    @pytest.mark.asyncio
    async def test_batch_embeddings(self, embedding_service):
        """Test batch embedding generation."""
        texts = ["First text", "Second text", "Third text"]
        
        embeddings = await embedding_service.embed_batch(texts)
        
        assert len(embeddings) == 3
        for embedding in embeddings:
            assert len(embedding) == 1536
    
    @pytest.mark.asyncio
    async def test_embedding_cache(self, embedding_service):
        """Test that embeddings are cached."""
        text = "Cache test text"
        
        # First call (uncached)
        embedding1 = await embedding_service.embed_text(text, use_cache=True)
        
        # Second call (should be cached)
        embedding2 = await embedding_service.embed_text(text, use_cache=True)
        
        # Should be identical
        assert embedding1 == embedding2


class TestSemanticMemory:
    """Tests for semantic memory system."""
    
    @pytest.fixture
    async def semantic_memory(self):
        """Create semantic memory instance."""
        vector_store = VectorStore(collection_name="test_semantic_memory")
        await vector_store.initialize_collection(recreate=True)
        
        embedding_service = EmbeddingService()
        memory = SemanticMemory(
            vector_store=vector_store,
            embedding_service=embedding_service
        )
        
        yield memory
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve_message(self, semantic_memory):
        """Test storing and retrieving messages."""
        # Store message
        message = Message(
            role=MessageRole.USER,
            content="What is the capital of France?"
        )
        
        point_id = await semantic_memory.store_message(
            message=message,
            conversation_id=1,
            message_id=100,
            user_id=1
        )
        
        assert point_id
        
        # Retrieve similar messages
        context = await semantic_memory.retrieve_context(
            query="Tell me about Paris and France",
            limit=5,
            user_id=1
        )
        
        assert context.total_matches > 0
        assert context.matches[0].conversation_id == 1
    
    @pytest.mark.asyncio
    async def test_context_injection(self, semantic_memory):
        """Test injecting context into messages."""
        # Store some background messages
        messages = [
            Message(role=MessageRole.USER, content="I love programming in Python"),
            Message(role=MessageRole.ASSISTANT, content="Python is a great language!"),
        ]
        
        await semantic_memory.store_messages_batch(
            messages=messages,
            conversation_id=2,
            user_id=1
        )
        
        # Retrieve context
        context = await semantic_memory.retrieve_context(
            query="What programming language should I learn?",
            limit=3,
            user_id=1
        )
        
        # Inject into new conversation
        current_messages = [
            Message(role=MessageRole.USER, content="What programming language should I learn?")
        ]
        
        injected_messages = semantic_memory.inject_context_into_messages(
            messages=current_messages,
            context=context,
            max_context_items=2
        )
        
        # Should have more messages now (context injected)
        assert len(injected_messages) > len(current_messages)
    
    @pytest.mark.asyncio
    async def test_relevance_filtering(self, semantic_memory):
        """Test that only relevant context is retrieved."""
        # Store unrelated message
        unrelated = Message(
            role=MessageRole.USER,
            content="What's the weather like today?"
        )
        await semantic_memory.store_message(
            message=unrelated,
            conversation_id=3,
            user_id=1
        )
        
        # Store related message
        related = Message(
            role=MessageRole.USER,
            content="Python programming tips for beginners"
        )
        await semantic_memory.store_message(
            message=related,
            conversation_id=3,
            user_id=1
        )
        
        # Query about programming
        context = await semantic_memory.retrieve_context(
            query="Best practices for Python coding",
            limit=5,
            score_threshold=0.7,
            user_id=1
        )
        
        # Should get related message, not unrelated
        if context.matches:
            assert "python" in context.matches[0].text.lower() or "programming" in context.matches[0].text.lower()


class TestContextManager:
    """Tests for long-context conversation management."""
    
    @pytest.fixture
    def context_manager(self):
        """Create context manager."""
        return ContextManager(max_tokens=1000, recent_window_size=5)
    
    def test_context_within_budget(self, context_manager):
        """Test that short conversations pass through unchanged."""
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a helpful assistant"),
            Message(role=MessageRole.USER, content="Hello"),
            Message(role=MessageRole.ASSISTANT, content="Hi there!"),
        ]
        
        managed = context_manager.manage_context(messages)
        
        assert len(managed) == len(messages)
    
    def test_context_pruning(self, context_manager):
        """Test that long conversations are pruned."""
        # Create many messages (will exceed token budget)
        messages = [Message(role=MessageRole.SYSTEM, content="You are a helpful assistant")]
        
        for i in range(50):
            messages.append(Message(role=MessageRole.USER, content=f"Question {i}: " + "word " * 100))
            messages.append(Message(role=MessageRole.ASSISTANT, content=f"Answer {i}: " + "word " * 100))
        
        managed = context_manager.manage_context(messages, preserve_system=True)
        
        # Should be pruned
        assert len(managed) < len(messages)
        # Should keep system message
        assert managed[0].role == MessageRole.SYSTEM
        # Should keep recent messages
        assert managed[-1].content == messages[-1].content
    
    @pytest.mark.asyncio
    async def test_context_summarization(self, context_manager):
        """Test that old messages are summarized."""
        messages = [Message(role=MessageRole.SYSTEM, content="You are a helpful assistant")]
        
        # Add many messages
        for i in range(20):
            messages.append(Message(role=MessageRole.USER, content=f"Question {i}: Tell me about topic {i}"))
            messages.append(Message(role=MessageRole.ASSISTANT, content=f"Answer {i}: Here's info about topic {i}"))
        
        managed = await context_manager.manage_context_with_summary(
            messages=messages,
            preserve_system=True
        )
        
        # Should have summary message
        has_summary = any("summary" in msg.content.lower() for msg in managed)
        assert has_summary or len(managed) < len(messages)
    
    def test_relevance_based_pruning(self, context_manager):
        """Test pruning by relevance."""
        messages = [
            Message(role=MessageRole.USER, content="I love Python programming"),
            Message(role=MessageRole.ASSISTANT, content="Python is great!"),
            Message(role=MessageRole.USER, content="What's the weather?"),
            Message(role=MessageRole.ASSISTANT, content="It's sunny"),
            Message(role=MessageRole.USER, content="Tell me about Python syntax"),
            Message(role=MessageRole.ASSISTANT, content="Python uses indentation"),
        ]
        
        pruned = context_manager.prune_by_relevance(
            messages=messages,
            current_query="Best Python practices",
            keep_count=4
        )
        
        assert len(pruned) == 4
        # Should keep Python-related messages
        python_count = sum(1 for msg in pruned if "python" in msg.content.lower())
        assert python_count > 0


@pytest.mark.asyncio
async def test_end_to_end_memory_flow():
    """Test complete memory flow: store, retrieve, inject."""
    # Setup
    vector_store = VectorStore(collection_name="test_e2e_memory")
    await vector_store.initialize_collection(recreate=True)
    
    embedding_service = EmbeddingService()
    memory = SemanticMemory(vector_store=vector_store, embedding_service=embedding_service)
    context_manager = ContextManager(max_tokens=2000)
    
    # Store past conversation
    past_messages = [
        Message(role=MessageRole.USER, content="I'm learning machine learning with TensorFlow"),
        Message(role=MessageRole.ASSISTANT, content="TensorFlow is excellent for deep learning!"),
        Message(role=MessageRole.USER, content="What about PyTorch?"),
        Message(role=MessageRole.ASSISTANT, content="PyTorch is also great, more pythonic"),
    ]
    
    await memory.store_messages_batch(
        messages=past_messages,
        conversation_id=100,
        user_id=1
    )
    
    # New conversation
    new_messages = [
        Message(role=MessageRole.SYSTEM, content="You are a helpful AI assistant"),
        Message(role=MessageRole.USER, content="Which deep learning framework should I use?"),
    ]
    
    # Retrieve relevant context
    context = await memory.retrieve_context(
        query=new_messages[-1].content,
        limit=3,
        user_id=1
    )
    
    # Inject context
    messages_with_context = memory.inject_context_into_messages(
        messages=new_messages,
        context=context
    )
    
    # Manage context
    final_messages = context_manager.manage_context(messages_with_context)
    
    # Verify
    assert len(final_messages) > len(new_messages)
    assert any("tensorflow" in msg.content.lower() or "pytorch" in msg.content.lower() for msg in final_messages)
