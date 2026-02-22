"""
Base provider class for all LLM providers
"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, List, Optional
import time
from src.cognitive.llm.types import ChatRequest, ChatResponse, Message, ProviderHealth, Usage
from src.utils.logging import get_logger
from src.utils.metrics import (
    ai_requests_total,
    ai_request_duration_seconds,
    ai_tokens_total,
    ai_cost_usd_total,
    ai_errors_total,
)

logger = get_logger(__name__)


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    Provides common functionality like metrics, cost tracking, and error handling.
    """
    
    def __init__(self, name: str):
        self.name = name
        self._is_healthy = True
        self._last_error: Optional[str] = None
    
    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Generate chat completion.
        
        Args:
            request: Chat request with messages and configuration
            
        Returns:
            Chat response with generated content
        """
        pass
    
    @abstractmethod
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Generate streaming chat completion.
        
        Args:
            request: Chat request with messages and configuration
            
        Yields:
            Content chunks as they're generated
        """
        pass
    
    @abstractmethod
    def _calculate_cost(self, usage: Usage, model: str) -> float:
        """
        Calculate cost in USD for the given usage.
        
        Args:
            usage: Token usage information
            model: Model name used
            
        Returns:
            Cost in USD
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """
        Check if provider is healthy and reachable.
        
        Returns:
            Provider health status
        """
        pass
    
    def _record_metrics(
        self,
        model: str,
        task_type: str,
        duration_ms: int,
        usage: Usage,
        cost_usd: float,
        success: bool = True,
    ) -> None:
        """
        Record metrics to Prometheus.
        
        Args:
            model: Model name used
            task_type: Type of task
            duration_ms: Response time in milliseconds
            usage: Token usage
            cost_usd: Cost in USD
            success: Whether the request succeeded
        """
        # Request counter
        ai_requests_total.labels(
            provider=self.name,
            model=model,
            task_type=task_type
        ).inc()
        
        # Duration histogram
        ai_request_duration_seconds.labels(
            provider=self.name,
            model=model
        ).observe(duration_ms / 1000.0)
        
        # Token counters
        ai_tokens_total.labels(
            provider=self.name,
            model=model,
            type="prompt"
        ).inc(usage.prompt_tokens)
        
        ai_tokens_total.labels(
            provider=self.name,
            model=model,
            type="completion"
        ).inc(usage.completion_tokens)
        
        # Cost counter
        ai_cost_usd_total.labels(
            provider=self.name,
            model=model
        ).inc(cost_usd)
        
        logger.info(
            f"AI Request: provider={self.name}, model={model}, "
            f"tokens={usage.total_tokens}, cost=${cost_usd:.6f}, "
            f"duration={duration_ms}ms"
        )
    
    def _record_error(self, error_type: str, error: Exception) -> None:
        """
        Record error metrics and log.
        
        Args:
            error_type: Type of error (timeout, api_error, etc.)
            error: Exception that occurred
        """
        ai_errors_total.labels(
            provider=self.name,
            error_type=error_type
        ).inc()
        
        self._is_healthy = False
        self._last_error = str(error)
        
        logger.error(f"{self.name} error ({error_type}): {error}")
    
    def _messages_to_api_format(self, messages: List[Message]) -> List[Dict[str, str]]:
        """
        Convert Message objects to API format.
        
        Args:
            messages: List of Message objects
            
        Returns:
            List of dictionaries in API format
        """
        return [msg.to_dict() for msg in messages]
    
    @property
    def is_healthy(self) -> bool:
        """Check if provider is currently healthy."""
        return self._is_healthy
    
    @property
    def last_error(self) -> Optional[str]:
        """Get last error message if any."""
        return self._last_error
