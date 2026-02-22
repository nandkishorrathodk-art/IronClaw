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
