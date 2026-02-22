"""
API endpoints for advanced reasoning (CoT, ToT)
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from src.cognitive.reasoning.chain_of_thought import ChainOfThoughtReasoner, CoTResult
from src.cognitive.reasoning.tree_of_thought import TreeOfThoughtReasoner, ToTResult
from src.cognitive.llm.router import get_router
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/reasoning", tags=["reasoning"])


class ReasoningRequest(BaseModel):
    """Request for reasoning."""
    question: str
    context: Optional[str] = None
    provider: Optional[str] = None


class CoTResponse(BaseModel):
    """Response from chain-of-thought reasoning."""
    result: CoTResult


class ToTResponse(BaseModel):
    """Response from tree-of-thought reasoning."""
    result: ToTResult


@router.post("/chain-of-thought", response_model=CoTResponse)
async def chain_of_thought_reasoning(request: ReasoningRequest):
    """
    Apply chain-of-thought reasoning to a question.
    
    - **question**: Question to reason about
    - **context**: Optional context/background information
    - **provider**: Optional AI provider to use
    """
    try:
        reasoner = ChainOfThoughtReasoner(router=get_router())
        result = await reasoner.reason(
            question=request.question,
            context=request.context,
            provider=request.provider
        )
        
        return CoTResponse(result=result)
    
    except Exception as e:
        logger.error(f"CoT reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tree-of-thought", response_model=ToTResponse)
async def tree_of_thought_reasoning(request: ReasoningRequest):
    """
    Apply tree-of-thought reasoning to a question.
    
    - **question**: Question to reason about
    - **context**: Optional context/background information
    - **provider**: Optional AI provider to use
    """
    try:
        reasoner = TreeOfThoughtReasoner(router=get_router())
        result = await reasoner.reason(
            question=request.question,
            context=request.context,
            provider=request.provider
        )
        
        return ToTResponse(result=result)
    
    except Exception as e:
        logger.error(f"ToT reasoning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
