"""
Common types for LLM providers
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    """Types of AI tasks for intelligent routing."""
    CONVERSATION = "conversation"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    VISION = "vision"
    PRIVACY = "privacy"  # For sensitive data, use local model
    GENERAL = "general"


class MessageRole(str, Enum):
    """Message roles in conversations."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class Message(BaseModel):
    """Single message in a conversation."""
    role: MessageRole
    content: str
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for API calls."""
        return {"role": self.role.value, "content": self.content}


class ChatRequest(BaseModel):
    """Request for chat completion."""
    messages: List[Message]
    task_type: TaskType = TaskType.GENERAL
    provider: Optional[str] = None  # If None, router will choose
    model: Optional[str] = None  # If None, use default for provider
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stream: bool = False
    
    class Config:
        json_schema_extra = {
            "example": {
                "messages": [
                    {"role": "user", "content": "Explain quantum computing"}
                ],
                "task_type": "conversation",
                "temperature": 0.7,
            }
        }


class Usage(BaseModel):
    """Token usage information."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Response from chat completion."""
    content: str
    provider: str
    model: str
    finish_reason: Optional[str] = None
    usage: Usage
    cost_usd: float = 0.0
    response_time_ms: int = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "content": "Quantum computing uses quantum mechanics...",
                "provider": "openai",
                "model": "gpt-4-turbo-preview",
                "finish_reason": "stop",
                "usage": {
                    "prompt_tokens": 15,
                    "completion_tokens": 120,
                    "total_tokens": 135
                },
                "cost_usd": 0.00405,
                "response_time_ms": 1234
            }
        }


class ProviderConfig(BaseModel):
    """Configuration for an AI provider."""
    name: str
    enabled: bool = True
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_fast: str
    model_smart: str
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: int = 120  # seconds
    
    # Cost per 1K tokens (USD)
    cost_per_1k_prompt_tokens: float = 0.0
    cost_per_1k_completion_tokens: float = 0.0


class ProviderHealth(BaseModel):
    """Health status of a provider."""
    name: str
    is_healthy: bool
    response_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    last_check: Optional[str] = None
