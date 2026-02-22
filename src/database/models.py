"""
SQLAlchemy database models for Ironclaw
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database.connection import Base


class User(Base):
    """User model for authentication and preferences."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    
    # Preferences
    preferred_ai_provider = Column(String(50), default="groq")
    preferred_language = Column(String(10), default="en")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<User {self.username} ({self.email})>"


class Conversation(Base):
    """Conversation model for storing chat history."""
    
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # Conversation metadata
    title = Column(String(255))
    summary = Column(Text)
    is_archived = Column(Boolean, default=False, nullable=False)
    
    # AI provider used
    ai_provider = Column(String(50))
    ai_model = Column(String(100))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    
    def __repr__(self) -> str:
        return f"<Conversation {self.id}: {self.title}>"


class Message(Base):
    """Message model for individual messages in conversations."""
    
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    
    # Message content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # Token usage
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    # Cost tracking
    cost_usd = Column(Float, default=0.0)
    
    # AI provider info
    ai_provider = Column(String(50))
    ai_model = Column(String(100))
    
    # Response metadata
    response_time_ms = Column(Integer)  # How long it took to generate
    finish_reason = Column(String(50))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self) -> str:
        return f"<Message {self.id} ({self.role}): {self.content[:50]}...>"


class AIUsageLog(Base):
    """Log of all AI provider API calls for monitoring and cost tracking."""
    
    __tablename__ = "ai_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Request details
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    task_type = Column(String(50))  # conversation, code_generation, reasoning, etc.
    
    # Token usage
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    
    # Cost
    cost_usd = Column(Float, default=0.0)
    
    # Performance
    response_time_ms = Column(Integer)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<AIUsageLog {self.provider}/{self.model}: {self.total_tokens} tokens>"


class CostLimit(Base):
    """User-specific cost limits to prevent overspending."""
    
    __tablename__ = "cost_limits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    
    # Limits in USD
    daily_limit_usd = Column(Float, default=10.0)
    monthly_limit_usd = Column(Float, default=100.0)
    
    # Current spending
    daily_spent_usd = Column(Float, default=0.0)
    monthly_spent_usd = Column(Float, default=0.0)
    
    # Last reset timestamps
    daily_reset_at = Column(DateTime(timezone=True), server_default=func.now())
    monthly_reset_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Alert settings
    alert_threshold_percent = Column(Float, default=80.0)  # Alert at 80% of limit
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<CostLimit user_id={self.user_id}: ${self.daily_limit_usd}/day, ${self.monthly_limit_usd}/month>"


class RoutingDecision(Base):
    """Track AI routing decisions for reinforcement learning."""
    
    __tablename__ = "routing_decisions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Request details
    task_type = Column(String(50), nullable=False, index=True)
    prompt_preview = Column(String(500))  # First 500 chars of prompt
    
    # Routing decision
    selected_provider = Column(String(50), nullable=False, index=True)
    selected_model = Column(String(100), nullable=False)
    alternative_providers = Column(JSON)  # List of other providers considered
    
    # Outcome metrics
    response_time_ms = Column(Integer)
    total_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # User feedback (explicit)
    user_rating = Column(Integer)  # 1-5 stars, or thumbs up/down (-1, 0, 1)
    user_feedback = Column(Text)
    
    # Quality metrics (implicit feedback)
    quality_score = Column(Float)  # 0-1, computed from various signals
    hallucination_detected = Column(Boolean, default=False)
    context_relevance = Column(Float)  # How relevant to conversation context
    
    # Reinforcement learning
    reward_value = Column(Float)  # Computed reward for RL
    exploration_decision = Column(Boolean, default=False)  # Was this an exploration vs exploitation?
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<RoutingDecision {self.task_type} → {self.selected_provider}/{self.selected_model}>"


class ProviderPerformance(Base):
    """Aggregate performance metrics for each provider by task type."""
    
    __tablename__ = "provider_performance"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Provider identification
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False, index=True)
    
    # Aggregated metrics
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)
    
    # Performance
    avg_response_time_ms = Column(Float)
    p50_response_time_ms = Column(Float)
    p95_response_time_ms = Column(Float)
    p99_response_time_ms = Column(Float)
    
    # Quality
    avg_user_rating = Column(Float)  # Average of user ratings (1-5)
    avg_quality_score = Column(Float)  # Average implicit quality score
    hallucination_rate = Column(Float)  # Percentage of responses with detected hallucinations
    
    # Cost
    total_cost_usd = Column(Float, default=0.0)
    avg_cost_per_request_usd = Column(Float)
    
    # Reinforcement learning
    avg_reward = Column(Float)  # Average reward value
    selection_probability = Column(Float, default=0.5)  # Current probability of selecting this provider for this task
    exploration_rate = Column(Float, default=0.1)  # How often to explore this provider
    
    # Timestamps
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self) -> str:
        return f"<ProviderPerformance {self.provider}/{self.model} for {self.task_type}: success={self.successful_requests}/{self.total_requests}>"


class ConversationMemory(Base):
    """Vector embeddings for semantic search of conversations."""
    
    __tablename__ = "conversation_memories"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    
    # Content and metadata
    content = Column(Text, nullable=False)
    content_type = Column(String(50), default="message")  # message, summary, key_point
    
    # Vector embedding (stored in Qdrant, this is just reference)
    qdrant_point_id = Column(String(100), unique=True, index=True)
    embedding_model = Column(String(100), default="text-embedding-3-small")
    
    # Search optimization
    content_hash = Column(String(64), index=True)  # SHA-256 of content for deduplication
    tokens = Column(Integer)  # Token count for context management
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self) -> str:
        return f"<ConversationMemory {self.id}: {self.content[:50]}...>"


class Feedback(Base):
    """User feedback for learning and self-improvement."""
    
    __tablename__ = "feedback"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=True, index=True)
    
    # Feedback details
    feedback_type = Column(String(20), nullable=False)  # thumbs_up, thumbs_down, rating_1-5
    rating = Column(Integer)  # 1-5 for rating feedback
    comment = Column(Text)  # Optional user comment
    
    # Context when feedback was given
    model_used = Column(String(100))
    task_type = Column(String(50))
    response_length = Column(Integer)  # Length of response in characters
    
    # Additional metadata
    metadata = Column(JSON)  # Store tone, style, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<Feedback {self.id}: {self.feedback_type} by user {self.user_id}>"


class PerformanceMetric(Base):
    """System performance metrics for self-improvement."""
    
    __tablename__ = "performance_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Metric identification
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False)  # response_time, error_rate, memory_usage, etc.
    endpoint = Column(String(255))  # API endpoint if applicable
    
    # Metric values
    value = Column(Float, nullable=False)
    unit = Column(String(20))  # ms, bytes, percent, count
    
    # Aggregation period
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    sample_count = Column(Integer, default=1)  # Number of samples aggregated
    
    # Statistical details
    min_value = Column(Float)
    max_value = Column(Float)
    avg_value = Column(Float)
    p50_value = Column(Float)
    p95_value = Column(Float)
    p99_value = Column(Float)
    
    # Additional context
    metadata = Column(JSON)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    def __repr__(self) -> str:
        return f"<PerformanceMetric {self.metric_name}: {self.value} {self.unit}>"


class CodeImprovement(Base):
    """Track AI-generated code improvements."""
    
    __tablename__ = "code_improvements"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Improvement identification
    file_path = Column(String(500), nullable=False, index=True)
    improvement_type = Column(String(50), nullable=False)  # optimization, bug_fix, refactor
    
    # Analysis
    issue_description = Column(Text, nullable=False)
    performance_impact = Column(String(50))  # high, medium, low
    confidence_score = Column(Float)  # 0-1, AI's confidence in the improvement
    
    # Code changes
    original_code = Column(Text)
    improved_code = Column(Text)
    diff = Column(Text)  # Git-style diff
    
    # Testing results
    test_status = Column(String(20))  # pending, passed, failed
    test_results = Column(JSON)
    
    # Deployment
    applied = Column(Boolean, default=False)
    applied_at = Column(DateTime(timezone=True))
    rolled_back = Column(Boolean, default=False)
    rollback_reason = Column(Text)
    
    # Git integration
    commit_hash = Column(String(40))
    branch_name = Column(String(255))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<CodeImprovement {self.file_path}: {self.improvement_type}>"


class LearningEvent(Base):
    """Track learning events for analytics and debugging."""
    
    __tablename__ = "learning_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False, index=True)  # preference_update, pattern_learned, improvement_applied
    event_category = Column(String(50))  # learning, performance, code_quality
    
    # Event data
    description = Column(Text)
    before_state = Column(JSON)  # State before the learning event
    after_state = Column(JSON)  # State after the learning event
    impact_score = Column(Float)  # Quantified impact (0-1)
    
    # Related entities
    related_feedback_id = Column(Integer, ForeignKey("feedback.id"), nullable=True)
    related_improvement_id = Column(Integer, ForeignKey("code_improvements.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<LearningEvent {self.event_type}: {self.description[:50]}>"
