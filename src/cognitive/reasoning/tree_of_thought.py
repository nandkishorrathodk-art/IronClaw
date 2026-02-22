"""
Tree-of-Thought (ToT) Reasoning
Explores multiple solution paths and selects the best one
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
import asyncio

from src.cognitive.llm.types import ChatRequest, ChatResponse, Message, MessageRole, TaskType
from src.cognitive.llm.router import AIRouter
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ThoughtNode(BaseModel):
    """A single thought node in the tree."""
    node_id: str
    parent_id: Optional[str] = None
    depth: int
    content: str
    evaluation_score: float = 0.0  # 0-1, how promising this path is
    is_terminal: bool = False  # Has reached a solution
    children: List[str] = []  # IDs of child nodes


class ToTPath(BaseModel):
    """A complete path through the thought tree."""
    nodes: List[ThoughtNode]
    total_score: float
    solution: str
    reasoning_trace: str


class ToTResult(BaseModel):
    """Result from tree-of-thought reasoning."""
    question: str
    paths_explored: int
    best_path: ToTPath
    alternative_paths: List[ToTPath]
    total_nodes: int
    reasoning_tokens: int = 0


class TreeOfThoughtReasoner:
    """
    Tree-of-Thought reasoning implementation.
    
    Explores multiple solution paths in parallel, evaluates each path,
    and selects the most promising solution.
    
    Features:
    - Multiple path exploration
    - Path evaluation and pruning
    - Backtracking on dead ends
    - Best solution selection
    """
    
    def __init__(self, router: Optional[AIRouter] = None):
        """
        Initialize Tree-of-Thought reasoner.
        
        Args:
            router: AI router instance. If None, creates new one.
        """
        self.router = router or AIRouter()
        self.nodes: Dict[str, ThoughtNode] = {}
        self.node_counter = 0
    
    async def reason(
        self,
        question: str,
        context: Optional[str] = None,
        max_depth: int = 4,
        branches_per_node: int = 3,
        provider: Optional[str] = None
    ) -> ToTResult:
        """
        Apply tree-of-thought reasoning to a question.
        
        Args:
            question: Question to reason about
            context: Optional context/background information
            max_depth: Maximum tree depth (default: 4)
            branches_per_node: How many branches per node (default: 3)
            provider: Specific AI provider to use (default: auto-select)
            
        Returns:
            ToTResult with best path and alternatives
        """
        logger.info(f"Starting ToT reasoning for: {question[:100]}...")
        
        self.nodes = {}
        self.node_counter = 0
        
        # Create root node
        root = self._create_node(
            content=f"Problem: {question}",
            parent_id=None,
            depth=0
        )
        
        # Expand tree using BFS with evaluation
        await self._expand_tree(
            root_id=root.node_id,
            question=question,
            context=context,
            max_depth=max_depth,
            branches_per_node=branches_per_node,
            provider=provider
        )
        
        # Extract all paths to terminal nodes
        paths = self._extract_paths()
        
        # Sort paths by score
        paths.sort(key=lambda p: p.total_score, reverse=True)
        
        # Get best path and alternatives
        best_path = paths[0] if paths else self._create_fallback_path(question)
        alternative_paths = paths[1:min(4, len(paths))]  # Top 3 alternatives
        
        result = ToTResult(
            question=question,
            paths_explored=len(paths),
            best_path=best_path,
            alternative_paths=alternative_paths,
            total_nodes=len(self.nodes),
            reasoning_tokens=0  # Would need to track across all AI calls
        )
        
        logger.info(
            f"ToT reasoning complete: {len(paths)} paths explored, "
            f"best score={best_path.total_score:.2f}"
        )
        
        return result
    
    def _create_node(
        self,
        content: str,
        parent_id: Optional[str],
        depth: int
    ) -> ThoughtNode:
        """Create a new thought node."""
        node_id = f"node_{self.node_counter}"
        self.node_counter += 1
        
        node = ThoughtNode(
            node_id=node_id,
            parent_id=parent_id,
            depth=depth,
            content=content
        )
        
        self.nodes[node_id] = node
        
        # Add to parent's children
        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)
        
        return node
    
    async def _expand_tree(
        self,
        root_id: str,
        question: str,
        context: Optional[str],
        max_depth: int,
        branches_per_node: int,
        provider: Optional[str]
    ):
        """Expand the thought tree using breadth-first search."""
        queue = [root_id]
        
        while queue:
            current_id = queue.pop(0)
            current_node = self.nodes[current_id]
            
            # Stop if max depth reached
            if current_node.depth >= max_depth:
                current_node.is_terminal = True
                continue
            
            # Generate child thoughts
            child_thoughts = await self._generate_child_thoughts(
                parent_node=current_node,
                question=question,
                context=context,
                num_children=branches_per_node,
                provider=provider
            )
            
            # Create child nodes and evaluate them
            for thought_content in child_thoughts:
                child_node = self._create_node(
                    content=thought_content,
                    parent_id=current_id,
                    depth=current_node.depth + 1
                )
                
                # Evaluate this thought
                evaluation_score = await self._evaluate_thought(
                    node=child_node,
                    question=question,
                    provider=provider
                )
                child_node.evaluation_score = evaluation_score
                
                # Check if this is a terminal (solution) node
                is_terminal = await self._is_terminal_node(
                    node=child_node,
                    question=question,
                    provider=provider
                )
                child_node.is_terminal = is_terminal
                
                # Only add promising nodes to queue
                if evaluation_score > 0.3 and not is_terminal:
                    queue.append(child_node.node_id)
    
    async def _generate_child_thoughts(
        self,
        parent_node: ThoughtNode,
        question: str,
        context: Optional[str],
        num_children: int,
        provider: Optional[str]
    ) -> List[str]:
        """Generate child thought branches from a parent node."""
        # Build prompt for thought generation
        prompt = self._build_thought_generation_prompt(
            parent_content=parent_node.content,
            question=question,
            context=context,
            num_thoughts=num_children
        )
        
        request = ChatRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are a creative problem solver exploring multiple solution paths."),
                Message(role=MessageRole.USER, content=prompt)
            ],
            task_type=TaskType.REASONING,
            provider=provider,
            temperature=0.8  # Higher temperature for diverse thoughts
        )
        
        try:
            response = await self.router.chat(request)
            
            # Parse thoughts from response
            thoughts = self._parse_thoughts(response.content, num_children)
            return thoughts
        
        except Exception as e:
            logger.error(f"Failed to generate child thoughts: {e}")
            return [f"Alternative approach {i+1}" for i in range(num_children)]
    
    def _build_thought_generation_prompt(
        self,
        parent_content: str,
        question: str,
        context: Optional[str],
        num_thoughts: int
    ) -> str:
        """Build prompt for generating child thoughts."""
        prompt_parts = []
        
        if context:
            prompt_parts.append(f"Context: {context}\n")
        
        prompt_parts.append(f"Question: {question}\n")
        prompt_parts.append(f"Current thought: {parent_content}\n")
        prompt_parts.append(
            f"Generate {num_thoughts} different next steps or approaches to solve this problem. "
            "Make them diverse and creative.\n\n"
            "Format: One thought per line, numbered:\n"
            "1. [first thought]\n"
            "2. [second thought]\n"
            "..."
        )
        
        return "\n".join(prompt_parts)
    
    def _parse_thoughts(self, response_text: str, expected_count: int) -> List[str]:
        """Parse thoughts from AI response."""
        thoughts = []
        lines = response_text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Match numbered thoughts
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                # Remove numbering/bullets
                thought = line.lstrip('0123456789.-• ').strip()
                if thought:
                    thoughts.append(thought)
        
        # Ensure we have expected count
        while len(thoughts) < expected_count:
            thoughts.append(f"Alternative approach {len(thoughts) + 1}")
        
        return thoughts[:expected_count]
    
    async def _evaluate_thought(
        self,
        node: ThoughtNode,
        question: str,
        provider: Optional[str]
    ) -> float:
        """
        Evaluate how promising a thought node is.
        
        Returns:
            Score from 0 to 1
        """
        prompt = (
            f"Question: {question}\n"
            f"Thought: {node.content}\n\n"
            "Rate how promising this thought is for solving the question. "
            "Consider:\n"
            "- Relevance to the question\n"
            "- Likelihood of leading to solution\n"
            "- Feasibility\n\n"
            "Respond with a single number from 0.0 (not promising) to 1.0 (very promising)."
        )
        
        request = ChatRequest(
            messages=[
                Message(role=MessageRole.SYSTEM, content="You are an expert evaluator."),
                Message(role=MessageRole.USER, content=prompt)
            ],
            task_type=TaskType.REASONING,
            provider=provider,
            temperature=0.2  # Low temperature for consistent evaluation
        )
        
        try:
            response = await self.router.chat(request)
            
            # Extract score from response
            score_text = response.content.strip()
            
            # Try to parse as float
            try:
                score = float(score_text)
                return max(0.0, min(1.0, score))  # Clamp to [0, 1]
            except ValueError:
                # If response contains a number, extract it
                import re
                numbers = re.findall(r'0?\.\d+|[01]\.0+', score_text)
                if numbers:
                    return float(numbers[0])
                
                # Default to medium score
                return 0.5
        
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return 0.5  # Default medium score
    
    async def _is_terminal_node(
        self,
        node: ThoughtNode,
        question: str,
        provider: Optional[str]
    ) -> bool:
        """Check if a node represents a terminal (solution) state."""
        # Simple heuristic: check if node content contains solution-like keywords
        content_lower = node.content.lower()
        solution_keywords = ['therefore', 'conclusion', 'answer is', 'solution:', 'final']
        
        if any(keyword in content_lower for keyword in solution_keywords):
            return True
        
        # If depth is high, consider it terminal
        if node.depth >= 3:
            return True
        
        return False
    
    def _extract_paths(self) -> List[ToTPath]:
        """Extract all paths from root to terminal nodes."""
        paths = []
        
        # Find all terminal nodes
        terminal_nodes = [
            node for node in self.nodes.values()
            if node.is_terminal
        ]
        
        # Build path for each terminal node
        for terminal in terminal_nodes:
            path_nodes = self._build_path_to_root(terminal)
            
            # Calculate total score (average of node scores)
            total_score = sum(n.evaluation_score for n in path_nodes) / len(path_nodes) if path_nodes else 0.0
            
            # Build reasoning trace
            reasoning_trace = "\n→ ".join([n.content for n in path_nodes])
            
            # Extract solution from terminal node
            solution = terminal.content
            
            path = ToTPath(
                nodes=path_nodes,
                total_score=total_score,
                solution=solution,
                reasoning_trace=reasoning_trace
            )
            paths.append(path)
        
        return paths
    
    def _build_path_to_root(self, node: ThoughtNode) -> List[ThoughtNode]:
        """Build path from node back to root."""
        path = [node]
        current = node
        
        while current.parent_id:
            parent = self.nodes.get(current.parent_id)
            if not parent:
                break
            path.insert(0, parent)
            current = parent
        
        return path
    
    def _create_fallback_path(self, question: str) -> ToTPath:
        """Create a fallback path if no solution found."""
        fallback_node = ThoughtNode(
            node_id="fallback",
            depth=0,
            content=f"Unable to find a clear solution to: {question}",
            evaluation_score=0.0,
            is_terminal=True
        )
        
        return ToTPath(
            nodes=[fallback_node],
            total_score=0.0,
            solution="No solution found",
            reasoning_trace="Reasoning incomplete"
        )


async def reason_with_tot(
    question: str,
    context: Optional[str] = None,
    router: Optional[AIRouter] = None
) -> ToTResult:
    """
    Convenience function for tree-of-thought reasoning.
    
    Args:
        question: Question to reason about
        context: Optional context
        router: Optional AI router
        
    Returns:
        ToTResult with best path and alternatives
    """
    reasoner = TreeOfThoughtReasoner(router=router)
    return await reasoner.reason(question=question, context=context)
