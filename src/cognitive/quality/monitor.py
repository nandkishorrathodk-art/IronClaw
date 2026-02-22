"""
Response quality monitoring system
Detects hallucinations, checks facts, and scores confidence
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import re

from src.cognitive.llm.types import ChatRequest, ChatResponse, Message, MessageRole, TaskType
from src.cognitive.llm.router import AIRouter
from src.cognitive.memory.semantic_memory import SemanticMemory, get_semantic_memory
from src.utils.logging import get_logger

logger = get_logger(__name__)


class QualityScore(BaseModel):
    """Quality assessment of an AI response."""
    overall_score: float  # 0-1
    confidence_score: float  # How confident the response seems
    hallucination_score: float  # Likelihood of hallucination (0=none, 1=high)
    factuality_score: float  # How factual the response is
    relevance_score: float  # How relevant to the query
    
    # Detailed findings
    hallucination_indicators: List[str] = []
    fact_check_results: List[str] = []
    improvement_suggestions: List[str] = []


class QualityMonitor:
    """
    Monitor and assess response quality.
    
    Features:
    - Automatic hallucination detection
    - Fact-checking against knowledge base
    - Confidence scoring
    - Improvement suggestions
    """
    
    def __init__(
        self,
        router: Optional[AIRouter] = None,
        memory: Optional[SemanticMemory] = None
    ):
        """
        Initialize quality monitor.
        
        Args:
            router: AI router for verification
            memory: Semantic memory for fact-checking
        """
        self.router = router or AIRouter()
        self.memory = memory or get_semantic_memory()
        
        # Hallucination indicators (heuristics)
        self.hallucination_patterns = [
            r"i think|i believe|probably|maybe|perhaps|possibly",  # Uncertainty
            r"as far as i know|to the best of my knowledge",  # Hedging
            r"\d{4,}",  # Specific numbers (often hallucinated)
            r"according to recent studies",  # Vague citations
            r"research shows|studies indicate",  # Vague attribution
        ]
    
    async def assess_response(
        self,
        response: ChatResponse,
        query: str,
        context: Optional[List[Message]] = None
    ) -> QualityScore:
        """
        Assess quality of an AI response.
        
        Args:
            response: AI response to assess
            query: Original query
            context: Optional conversation context
            
        Returns:
            QualityScore with detailed assessment
        """
        logger.info(f"Assessing response quality for: {query[:50]}...")
        
        # 1. Confidence scoring
        confidence_score = await self._assess_confidence(response.content)
        
        # 2. Hallucination detection
        hallucination_score, hallucination_indicators = self._detect_hallucinations(response.content)
        
        # 3. Fact-checking against memory
        factuality_score, fact_check_results = await self._check_facts(
            response.content,
            query
        )
        
        # 4. Relevance scoring
        relevance_score = await self._assess_relevance(response.content, query)
        
        # 5. Generate improvement suggestions
        improvement_suggestions = self._generate_improvements(
            confidence_score,
            hallucination_score,
            factuality_score,
            relevance_score
        )
        
        # Calculate overall score
        overall_score = (
            confidence_score * 0.3 +
            (1 - hallucination_score) * 0.3 +
            factuality_score * 0.2 +
            relevance_score * 0.2
        )
        
        quality = QualityScore(
            overall_score=overall_score,
            confidence_score=confidence_score,
            hallucination_score=hallucination_score,
            factuality_score=factuality_score,
            relevance_score=relevance_score,
            hallucination_indicators=hallucination_indicators,
            fact_check_results=fact_check_results,
            improvement_suggestions=improvement_suggestions
        )
        
        logger.info(
            f"Quality assessment complete: overall={overall_score:.2f}, "
            f"hallucination={hallucination_score:.2f}, confidence={confidence_score:.2f}"
        )
        
        return quality
    
    async def _assess_confidence(self, response_text: str) -> float:
        """
        Assess how confident the response is.
        
        Uses AI to evaluate confidence level.
        
        Args:
            response_text: Response to assess
            
        Returns:
            Confidence score (0-1)
        """
        prompt = (
            f"Assess how confident this response is:\n\n{response_text}\n\n"
            "Rate the confidence level from 0.0 (very uncertain) to 1.0 (very confident). "
            "Look for:\n"
            "- Definitive statements (confident)\n"
            "- Hedging language like 'maybe', 'probably' (uncertain)\n"
            "- Specific facts vs vague claims\n\n"
            "Respond with only a number between 0.0 and 1.0."
        )
        
        try:
            request = ChatRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are an expert at assessing confidence levels."),
                    Message(role=MessageRole.USER, content=prompt)
                ],
                task_type=TaskType.REASONING,
                temperature=0.2
            )
            
            result = await self.router.chat(request)
            
            # Extract score
            score_text = result.content.strip()
            try:
                score = float(score_text)
                return max(0.0, min(1.0, score))
            except ValueError:
                # Try to find a number in the text
                numbers = re.findall(r'0?\.\d+|[01]\.0+', score_text)
                if numbers:
                    return float(numbers[0])
                return 0.5  # Default
        
        except Exception as e:
            logger.warning(f"Confidence assessment failed: {e}")
            return 0.5  # Default medium confidence
    
    def _detect_hallucinations(self, response_text: str) -> tuple[float, List[str]]:
        """
        Detect hallucination indicators in response.
        
        Uses heuristics to identify potential hallucinations.
        
        Args:
            response_text: Response to check
            
        Returns:
            (hallucination_score, indicators) tuple
        """
        indicators = []
        response_lower = response_text.lower()
        
        # Check each pattern
        for pattern in self.hallucination_patterns:
            matches = re.findall(pattern, response_lower)
            if matches:
                indicators.append(f"Found pattern '{pattern}': {matches[:3]}")
        
        # Calculate score based on number of indicators
        # More indicators = higher hallucination risk
        hallucination_score = min(1.0, len(indicators) * 0.2)
        
        return hallucination_score, indicators
    
    async def _check_facts(
        self,
        response_text: str,
        query: str
    ) -> tuple[float, List[str]]:
        """
        Check facts in response against knowledge base.
        
        Args:
            response_text: Response to check
            query: Original query
            
        Returns:
            (factuality_score, fact_check_results) tuple
        """
        # Retrieve relevant context from memory
        try:
            context = await self.memory.retrieve_context(
                query=query,
                limit=3,
                score_threshold=0.7
            )
            
            if not context.matches:
                # No knowledge base to check against
                return 0.5, ["No knowledge base available for fact-checking"]
            
            # Build fact-checking prompt
            knowledge_summary = "\n".join([
                f"- {match.text}"
                for match in context.matches
            ])
            
            prompt = (
                f"Check if this response is factually consistent with the knowledge base:\n\n"
                f"Response:\n{response_text}\n\n"
                f"Knowledge base:\n{knowledge_summary}\n\n"
                "Are there any factual inconsistencies? "
                "Respond with 'CONSISTENT' if facts match, or 'INCONSISTENT: [reason]' if they don't."
            )
            
            request = ChatRequest(
                messages=[
                    Message(role=MessageRole.SYSTEM, content="You are a fact-checker."),
                    Message(role=MessageRole.USER, content=prompt)
                ],
                task_type=TaskType.REASONING,
                temperature=0.2
            )
            
            result = await self.router.chat(request)
            
            # Parse result
            result_text = result.content.strip().upper()
            if 'CONSISTENT' in result_text and 'INCONSISTENT' not in result_text:
                return 1.0, ["Facts consistent with knowledge base"]
            else:
                return 0.3, [f"Fact-check result: {result.content}"]
        
        except Exception as e:
            logger.warning(f"Fact-checking failed: {e}")
            return 0.5, [f"Fact-checking error: {e}"]
    
    async def _assess_relevance(self, response_text: str, query: str) -> float:
        """
        Assess how relevant the response is to the query.
        
        Args:
            response_text: Response to assess
            query: Original query
            
        Returns:
            Relevance score (0-1)
        """
        # Simple heuristic: keyword overlap
        query_words = set(query.lower().split())
        response_words = set(response_text.lower().split())
        
        # Calculate Jaccard similarity
        intersection = len(query_words & response_words)
        union = len(query_words | response_words)
        
        if union == 0:
            return 0.0
        
        jaccard_score = intersection / union
        
        # Boost score if query words appear in response
        query_coverage = sum(1 for word in query_words if word in response_words) / len(query_words) if query_words else 0
        
        # Combine scores
        relevance_score = (jaccard_score * 0.4 + query_coverage * 0.6)
        
        return min(1.0, relevance_score * 1.5)  # Scale up slightly
    
    def _generate_improvements(
        self,
        confidence_score: float,
        hallucination_score: float,
        factuality_score: float,
        relevance_score: float
    ) -> List[str]:
        """
        Generate improvement suggestions based on scores.
        
        Args:
            confidence_score: Confidence score
            hallucination_score: Hallucination score
            factuality_score: Factuality score
            relevance_score: Relevance score
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        if confidence_score < 0.5:
            suggestions.append("Response seems uncertain. Consider using a more capable model or providing more context.")
        
        if hallucination_score > 0.5:
            suggestions.append("High hallucination risk detected. Verify facts before using this response.")
        
        if factuality_score < 0.5:
            suggestions.append("Factual inconsistencies detected. Check against reliable sources.")
        
        if relevance_score < 0.5:
            suggestions.append("Response may not be fully relevant to query. Consider rephrasing the question.")
        
        if not suggestions:
            suggestions.append("Response quality looks good!")
        
        return suggestions


# Global instance
_quality_monitor: Optional[QualityMonitor] = None


def get_quality_monitor() -> QualityMonitor:
    """Get global quality monitor instance."""
    global _quality_monitor
    if _quality_monitor is None:
        _quality_monitor = QualityMonitor()
    return _quality_monitor
