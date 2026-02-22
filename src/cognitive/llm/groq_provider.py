"""
Groq provider implementation
Ultra-fast inference with Llama 3 and Mixtral models
"""
import time
from typing import AsyncIterator
from groq import AsyncGroq, APIError, APITimeoutError, RateLimitError

from src.cognitive.llm.base_provider import BaseLLMProvider
from src.cognitive.llm.types import ChatRequest, ChatResponse, ProviderHealth, Usage
from src.config import settings
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GroqProvider(BaseLLMProvider):
    """Groq API provider for ultra-fast LLM inference."""
    
    # Model costs per 1K tokens (USD) - Groq has generous free tier!
    MODEL_COSTS = {
        "llama-3.1-8b-instant": {"prompt": 0.00005, "completion": 0.00008},
        "llama-3.1-70b-versatile": {"prompt": 0.00059, "completion": 0.00079},
        "mixtral-8x7b-32768": {"prompt": 0.00024, "completion": 0.00024},
    }
    
    def __init__(self):
        super().__init__(name="groq")
        
        if not settings.groq_api_key:
            logger.warning("Groq API key not configured")
            self._client = None
        else:
            self._client = AsyncGroq(
                api_key=settings.groq_api_key,
                timeout=settings.request_timeout_seconds,
            )
            logger.info("Groq provider initialized")
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Generate chat completion using Groq API."""
        if not self._client:
            raise ValueError("Groq API key not configured")
        
        model = request.model or settings.groq_model_fast
        start_time = time.time()
        
        try:
            # Call Groq API
            response = await self._client.chat.completions.create(
                model=model,
                messages=self._messages_to_api_format(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_tokens or settings.groq_max_tokens,
            )
            
            # Extract response data
            content = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            
            # Calculate usage and cost
            usage = Usage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )
            
            cost_usd = self._calculate_cost(usage, model)
            duration_ms = int((time.time() - start_time) * 1000)
            
            # Record metrics
            self._record_metrics(
                model=model,
                task_type=request.task_type.value,
                duration_ms=duration_ms,
                usage=usage,
                cost_usd=cost_usd,
            )
            
            # Mark as healthy
            self._is_healthy = True
            self._last_error = None
            
            return ChatResponse(
                content=content,
                provider=self.name,
                model=model,
                finish_reason=finish_reason,
                usage=usage,
                cost_usd=cost_usd,
                response_time_ms=duration_ms,
            )
            
        except RateLimitError as e:
            self._record_error("rate_limit", e)
            raise
        except APITimeoutError as e:
            self._record_error("timeout", e)
            raise
        except APIError as e:
            self._record_error("api_error", e)
            raise
        except Exception as e:
            self._record_error("unknown", e)
            raise
    
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Generate streaming chat completion."""
        if not self._client:
            raise ValueError("Groq API key not configured")
        
        model = request.model or settings.groq_model_fast
        
        try:
            stream = await self._client.chat.completions.create(
                model=model,
                messages=self._messages_to_api_format(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_tokens or settings.groq_max_tokens,
                stream=True,
            )
            
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
            
            # Mark as healthy
            self._is_healthy = True
            self._last_error = None
            
        except Exception as e:
            self._record_error("stream_error", e)
            raise
    
    def _calculate_cost(self, usage: Usage, model: str) -> float:
        """Calculate cost based on token usage."""
        if model not in self.MODEL_COSTS:
            # Use llama-3.1-8b pricing as default
            costs = self.MODEL_COSTS["llama-3.1-8b-instant"]
        else:
            costs = self.MODEL_COSTS[model]
        
        prompt_cost = (usage.prompt_tokens / 1000) * costs["prompt"]
        completion_cost = (usage.completion_tokens / 1000) * costs["completion"]
        
        return prompt_cost + completion_cost
    
    async def health_check(self) -> ProviderHealth:
        """Check Groq API health."""
        if not self._client:
            return ProviderHealth(
                name=self.name,
                is_healthy=False,
                error_message="API key not configured",
            )
        
        start_time = time.time()
        
        try:
            # Simple API call to check connectivity
            await self._client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5,
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return ProviderHealth(
                name=self.name,
                is_healthy=True,
                response_time_ms=duration_ms,
            )
            
        except Exception as e:
            return ProviderHealth(
                name=self.name,
                is_healthy=False,
                error_message=str(e),
            )
