"""
Chat API endpoints for Ironclaw
Provides REST API for AI chat completions with intelligent routing
"""
from typing import Dict, List
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from src.cognitive.llm.router import get_router
from src.cognitive.llm.types import ChatRequest, ChatResponse, ProviderHealth
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/", response_model=ChatResponse)
async def create_chat_completion(request: ChatRequest) -> ChatResponse:
    """
    Generate AI chat completion.
    
    The router will automatically select the best AI provider based on:
    - Task type (conversation, code, reasoning, etc.)
    - Cost optimization
    - Provider health and availability
    
    Example request:
    ```json
    {
      "messages": [
        {"role": "user", "content": "Explain quantum computing"}
      ],
      "task_type": "conversation",
      "temperature": 0.7
    }
    ```
    """
    try:
        ai_router = get_router()
        response = await ai_router.chat(request)
        return response
    except ValueError as e:
        logger.error(f"Chat request failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate response"
        )


@router.post("/stream")
async def create_chat_completion_stream(request: ChatRequest):
    """
    Generate streaming AI chat completion.
    
    Streams response tokens as they are generated for lower perceived latency.
    
    Example request:
    ```json
    {
      "messages": [
        {"role": "user", "content": "Write a Python function to sort a list"}
      ],
      "task_type": "code_generation",
      "stream": true
    }
    ```
    """
    try:
        ai_router = get_router()
        
        async def generate():
            try:
                async for chunk in ai_router.chat_stream(request):
                    yield chunk
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"\n\nError: {str(e)}"
        
        return StreamingResponse(generate(), media_type="text/plain")
        
    except Exception as e:
        logger.error(f"Failed to start stream: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start streaming"
        )


@router.get("/providers")
async def list_available_providers() -> Dict[str, List[str]]:
    """
    List all available AI providers.
    
    Returns:
    ```json
    {
      "providers": ["openai", "groq", "anthropic", "local"],
      "default": "groq"
    }
    ```
    """
    ai_router = get_router()
    return {
        "providers": ai_router.get_available_providers(),
        "default": "groq",  # Will be from settings
    }


@router.get("/providers/health")
async def check_providers_health() -> Dict[str, ProviderHealth]:
    """
    Check health status of all AI providers.
    
    Returns health metrics including:
    - Provider availability
    - Response time
    - Last error (if any)
    
    Example response:
    ```json
    {
      "openai": {
        "name": "openai",
        "is_healthy": true,
        "response_time_ms": 234
      },
      "groq": {
        "name": "groq",
        "is_healthy": true,
        "response_time_ms": 156
      }
    }
    ```
    """
    ai_router = get_router()
    return await ai_router.health_check_all()
