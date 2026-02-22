"""
Intelligent AI router with cost tracking and provider selection
Selects the best AI provider for each task based on task type, cost, and performance
"""
from typing import AsyncIterator, Dict, List, Optional
import asyncio

from src.cognitive.llm.base_provider import BaseLLMProvider
from src.cognitive.llm.openai_provider import OpenAIProvider
from src.cognitive.llm.groq_provider import GroqProvider
from src.cognitive.llm.types import (
    ChatRequest,
    ChatResponse,
    ProviderHealth,
    TaskType,
)
from src.config import settings
from src.utils.logging import get_logger
from src.database.redis_client import cache_get, cache_set

logger = get_logger(__name__)


class AIRouter:
    """
    Intelligent router for selecting optimal AI provider.
    
    Features:
    - Task-based routing (conversation → Groq, code → GPT-4, etc.)
    - Cost tracking and optimization
    - Automatic failover to backup providers
    - Health monitoring
    - Learning from user feedback
    """
    
    def __init__(self):
        self.providers: Dict[str, BaseLLMProvider] = {}
        self._initialize_providers()
    
    def _initialize_providers(self) -> None:
        """Initialize all configured AI providers."""
        
        # OpenAI (GPT-4, GPT-3.5-turbo)
        if settings.openai_api_key:
            try:
                self.providers["openai"] = OpenAIProvider()
                logger.info("✅ OpenAI provider registered")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI: {e}")
        
        # Groq (Ultra-fast Llama 3, Mixtral)
        if settings.groq_api_key:
            try:
                self.providers["groq"] = GroqProvider()
                logger.info("✅ Groq provider registered")
            except Exception as e:
                logger.error(f"Failed to initialize Groq: {e}")
        
        # Anthropic (Claude) - Placeholder for future implementation
        # if settings.anthropic_api_key:
        #     self.providers["anthropic"] = AnthropicProvider()
        
        # Google Gemini - Placeholder for future implementation
        # if settings.google_api_key:
        #     self.providers["google"] = GoogleProvider()
        
        # Local NPU model - Will be implemented in Phase 1.5
        # if settings.enable_local_ai:
        #     self.providers["local"] = LocalNPUProvider()
        
        if not self.providers:
            logger.error("⚠️ No AI providers configured! Please add at least one API key.")
        else:
            logger.info(f"AI Router initialized with providers: {list(self.providers.keys())}")
    
    def select_provider(self, request: ChatRequest) -> str:
        """
        Select the best provider for the given request.
        
        Args:
            request: Chat request with task type and preferences
            
        Returns:
            Provider name to use
        """
        # If provider explicitly requested, use it
        if request.provider and request.provider in self.providers:
            return request.provider
        
        # Get configured provider for this task type
        provider_name = settings.get_model_for_task(request.task_type.value)
        
        # Verify provider is available
        if provider_name in self.providers:
            provider = self.providers[provider_name]
            if provider.is_healthy:
                return provider_name
            logger.warning(f"Provider {provider_name} is unhealthy, selecting fallback")
        
        # Fallback: use default provider
        default = settings.router_default_provider
        if default in self.providers:
            return default
        
        # Last resort: use first available healthy provider
        for name, provider in self.providers.items():
            if provider.is_healthy:
                logger.info(f"Using fallback provider: {name}")
                return name
        
        raise ValueError("No healthy AI providers available")
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """
        Route chat request to appropriate provider.
        
        Args:
            request: Chat request
            
        Returns:
            Chat response from selected provider
        """
        # Select provider
        provider_name = self.select_provider(request)
        provider = self.providers[provider_name]
        
        logger.info(
            f"Routing {request.task_type.value} task to {provider_name} "
            f"(model: {request.model or 'default'})"
        )
        
        try:
            # Generate response
            response = await provider.chat(request)
            
            # Track cost in database (will be implemented later)
            # await self._track_cost(response)
            
            return response
            
        except Exception as e:
            logger.error(f"Provider {provider_name} failed: {e}")
            
            # Try failover to another provider
            if len(self.providers) > 1:
                logger.info("Attempting failover to backup provider...")
                return await self._failover_chat(request, failed_provider=provider_name)
            
            raise
    
    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Route streaming chat request to appropriate provider.
        
        Args:
            request: Chat request
            
        Yields:
            Content chunks from selected provider
        """
        provider_name = self.select_provider(request)
        provider = self.providers[provider_name]
        
        logger.info(f"Streaming {request.task_type.value} from {provider_name}")
        
        try:
            async for chunk in provider.chat_stream(request):
                yield chunk
        except Exception as e:
            logger.error(f"Streaming failed from {provider_name}: {e}")
            raise
    
    async def _failover_chat(
        self,
        request: ChatRequest,
        failed_provider: str
    ) -> ChatResponse:
        """
        Attempt to fulfill request using backup provider.
        
        Args:
            request: Original request
            failed_provider: Provider that failed
            
        Returns:
            Response from backup provider
        """
        for name, provider in self.providers.items():
            if name != failed_provider and provider.is_healthy:
                logger.info(f"Failing over to {name}")
                try:
                    return await provider.chat(request)
                except Exception as e:
                    logger.error(f"Failover to {name} also failed: {e}")
                    continue
        
        raise ValueError("All providers failed")
    
    async def health_check_all(self) -> Dict[str, ProviderHealth]:
        """
        Check health of all providers concurrently.
        
        Returns:
            Dictionary mapping provider name to health status
        """
        tasks = {
            name: provider.health_check()
            for name, provider in self.providers.items()
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        health_status = {}
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                health_status[name] = ProviderHealth(
                    name=name,
                    is_healthy=False,
                    error_message=str(result)
                )
            else:
                health_status[name] = result
        
        return health_status
    
    def get_available_providers(self) -> List[str]:
        """Get list of available provider names."""
        return list(self.providers.keys())
    
    def get_provider(self, name: str) -> Optional[BaseLLMProvider]:
        """Get provider instance by name."""
        return self.providers.get(name)


# Global router instance
_router: Optional[AIRouter] = None


def get_router() -> AIRouter:
    """
    Get global AI router instance.
    Creates router on first call.
    """
    global _router
    if _router is None:
        _router = AIRouter()
    return _router
