"""
Chain-of-Thought (CoT) Reasoning
Step-by-step problem solving with self-verification
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from src.cognitive.llm.types import ChatRequest, ChatResponse, Message, MessageRole, TaskType
from src.cognitive.llm.router import AIRouter
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ReasoningStep(BaseModel):
    """A single step in chain-of-thought reasoning."""
    step_number: int
    description: str
    reasoning: str
    result: Optional[str] = None
    confidence: float = 1.0


class CoTResult(BaseModel):
    """Result from chain-of-thought reasoning."""
    question: str
    steps: List[ReasoningStep]
    final_answer: str
    verification_passed: bool
    total_confidence: float
    reasoning_tokens: int = 0


class ChainOfThoughtReasoner:
    """
    Chain-of-Thought reasoning implementation.
    
    Uses structured prompting to make AI think step-by-step,
    show its work, and verify answers.
    
    Features:
    - Multi-step problem decomposition
    - Self-verification of answers
    - Confidence scoring per step
    - Works with any LLM provider
    """
    
    def __init__(self, router: Optional[AIRouter] = None):
        """
        Initialize Chain-of-Thought reasoner.
        
        Args:
            router: AI router instance. If None, creates new one.
        """
        self.router = router or AIRouter()
    
    async def reason(
        self,
        question: str,
        context: Optional[str] = None,
        max_steps: int = 10,
        provider: Optional[str] = None
    ) -> CoTResult:
        """
        Apply chain-of-thought reasoning to a question.
        
        Args:
            question: Question to reason about
            context: Optional context/background information
            max_steps: Maximum reasoning steps (default: 10)
            provider: Specific AI provider to use (default: auto-select)
            
        Returns:
            CoTResult with steps, answer, and verification
        """
        logger.info(f"Starting CoT reasoning for: {question[:100]}...")
        
        # Build CoT prompt
        cot_prompt = self._build_cot_prompt(question, context)
        
        # Get reasoning steps from AI
        request = ChatRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are an expert problem solver who thinks step by step."),
                Message(role=MessageRole.USER, content=cot_prompt)
            ],
            task_type=TaskType.REASONING,
            provider=provider,
            temperature=0.3  # Lower temperature for more focused reasoning
        )
        
        response = await self.router.chat(request)
        
        # Parse reasoning steps
        steps = self._parse_reasoning_steps(response.content)
        
        # Extract final answer
        final_answer = self._extract_final_answer(response.content)
        
        # Verify answer
        verification_passed, verification_reasoning = await self._verify_answer(
            question=question,
            answer=final_answer,
            reasoning_steps=steps,
            provider=provider
        )
        
        # Calculate overall confidence
        total_confidence = sum(step.confidence for step in steps) / len(steps) if steps else 0.0
        
        result = CoTResult(
            question=question,
            steps=steps,
            final_answer=final_answer,
            verification_passed=verification_passed,
            total_confidence=total_confidence,
            reasoning_tokens=response.usage.total_tokens
        )
        
        logger.info(
            f"CoT reasoning complete: {len(steps)} steps, "
            f"verified={verification_passed}, confidence={total_confidence:.2f}"
        )
        
        return result
    
    def _build_cot_prompt(self, question: str, context: Optional[str] = None) -> str:
        """Build a chain-of-thought prompt."""
        prompt_parts = []
        
        if context:
            prompt_parts.append(f"Context:\n{context}\n")
        
        prompt_parts.append(f"Question: {question}\n")
        prompt_parts.append(
            "Please solve this step by step:\n"
            "1. Break down the problem\n"
            "2. Show your reasoning for each step\n"
            "3. State your confidence (0-1) for each step\n"
            "4. Provide the final answer\n\n"
            "Format your response as:\n"
            "Step 1: [description] (confidence: X.X)\n"
            "Reasoning: [your reasoning]\n"
            "Result: [step result]\n\n"
            "...\n\n"
            "Final Answer: [your answer]"
        )
        
        return "\n".join(prompt_parts)
    
    def _parse_reasoning_steps(self, response_text: str) -> List[ReasoningStep]:
        """Parse reasoning steps from AI response."""
        steps = []
        lines = response_text.split('\n')
        
        current_step = None
        current_step_number = 0
        
        for line in lines:
            line = line.strip()
            
            # Detect step header
            if line.lower().startswith('step '):
                current_step_number += 1
                
                # Extract confidence if present
                confidence = 1.0
                if '(confidence:' in line.lower():
                    try:
                        conf_str = line.split('(confidence:')[1].split(')')[0].strip()
                        confidence = float(conf_str)
                    except (IndexError, ValueError):
                        pass
                
                # Extract description
                description = line.split(':', 1)[1] if ':' in line else line
                description = description.split('(confidence')[0].strip()
                
                if current_step:
                    steps.append(current_step)
                
                current_step = ReasoningStep(
                    step_number=current_step_number,
                    description=description,
                    reasoning="",
                    confidence=confidence
                )
            
            # Detect reasoning
            elif current_step and line.lower().startswith('reasoning:'):
                current_step.reasoning = line.split(':', 1)[1].strip()
            
            # Detect result
            elif current_step and line.lower().startswith('result:'):
                current_step.result = line.split(':', 1)[1].strip()
            
            # Append to reasoning if we're in a step
            elif current_step and line and not line.lower().startswith('final answer'):
                if current_step.reasoning:
                    current_step.reasoning += " " + line
                else:
                    current_step.reasoning = line
        
        # Add last step
        if current_step:
            steps.append(current_step)
        
        return steps
    
    def _extract_final_answer(self, response_text: str) -> str:
        """Extract final answer from AI response."""
        lines = response_text.split('\n')
        
        for i, line in enumerate(lines):
            if 'final answer' in line.lower():
                # Extract answer from this line or next lines
                answer_parts = []
                
                # Try to get answer from same line
                if ':' in line:
                    answer_part = line.split(':', 1)[1].strip()
                    if answer_part:
                        answer_parts.append(answer_part)
                
                # Get subsequent lines until empty line or new section
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line or next_line.lower().startswith('verification'):
                        break
                    answer_parts.append(next_line)
                
                if answer_parts:
                    return ' '.join(answer_parts)
        
        # Fallback: return last non-empty line
        for line in reversed(lines):
            if line.strip():
                return line.strip()
        
        return "No answer found"
    
    async def _verify_answer(
        self,
        question: str,
        answer: str,
        reasoning_steps: List[ReasoningStep],
        provider: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Verify the answer using a separate AI call.
        
        Args:
            question: Original question
            answer: Answer to verify
            reasoning_steps: Steps that led to answer
            provider: AI provider to use
            
        Returns:
            (verification_passed, reasoning)
        """
        # Build verification prompt
        steps_summary = "\n".join([
            f"Step {s.step_number}: {s.description} → {s.result}"
            for s in reasoning_steps
        ])
        
        verification_prompt = (
            f"Question: {question}\n\n"
            f"Reasoning steps:\n{steps_summary}\n\n"
            f"Proposed answer: {answer}\n\n"
            "Please verify if this answer is correct and the reasoning is sound. "
            "Respond with 'VERIFIED' if correct, or 'FAILED: [reason]' if incorrect."
        )
        
        request = ChatRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are a critical reviewer who checks answers carefully."),
                Message(role=MessageRole.USER, content=verification_prompt)
            ],
            task_type=TaskType.REASONING,
            provider=provider,
            temperature=0.2  # Very focused for verification
        )
        
        try:
            response = await self.router.chat(request)
            verification_text = response.content.strip().upper()
            
            if 'VERIFIED' in verification_text:
                return True, response.content
            else:
                return False, response.content
        
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return False, f"Verification error: {e}"


async def reason_with_cot(
    question: str,
    context: Optional[str] = None,
    router: Optional[AIRouter] = None
) -> CoTResult:
    """
    Convenience function for chain-of-thought reasoning.
    
    Args:
        question: Question to reason about
        context: Optional context
        router: Optional AI router
        
    Returns:
        CoTResult with reasoning steps and answer
    """
    reasoner = ChainOfThoughtReasoner(router=router)
    return await reasoner.reason(question=question, context=context)
