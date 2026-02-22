"""
Integration tests for Chain-of-Thought and Tree-of-Thought reasoning
"""
import pytest
from src.cognitive.reasoning.chain_of_thought import ChainOfThoughtReasoner
from src.cognitive.reasoning.tree_of_thought import TreeOfThoughtReasoner


class TestChainOfThoughtReasoning:
    """Tests for Chain-of-Thought reasoning."""
    
    @pytest.mark.asyncio
    async def test_simple_math_problem(self):
        """Test CoT on a simple math problem."""
        reasoner = ChainOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="If a train travels 60 miles per hour for 2.5 hours, how far does it travel?",
            max_steps=5
        )
        
        # Verify result structure
        assert result.question
        assert len(result.steps) > 0
        assert result.final_answer
        assert isinstance(result.verification_passed, bool)
        assert 0 <= result.total_confidence <= 1
        
        # Check answer correctness (should mention 150 miles)
        assert "150" in result.final_answer
    
    @pytest.mark.asyncio
    async def test_logical_reasoning(self):
        """Test CoT on logical reasoning problem."""
        reasoner = ChainOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="All cats are mammals. Fluffy is a cat. Is Fluffy a mammal?",
            max_steps=3
        )
        
        assert result.verification_passed
        assert "yes" in result.final_answer.lower() or "mammal" in result.final_answer.lower()
        assert len(result.steps) >= 1
    
    @pytest.mark.asyncio
    async def test_step_confidence_scores(self):
        """Test that step confidence scores are generated."""
        reasoner = ChainOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="What is 5 + 3 * 2?",
            max_steps=4
        )
        
        # All steps should have confidence scores
        for step in result.steps:
            assert 0 <= step.confidence <= 1
            assert step.description
            assert step.reasoning


class TestTreeOfThoughtReasoning:
    """Tests for Tree-of-Thought reasoning."""
    
    @pytest.mark.asyncio
    async def test_multiple_paths_explored(self):
        """Test that ToT explores multiple solution paths."""
        reasoner = TreeOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="How can you measure exactly 4 liters using only a 5-liter and a 3-liter jug?",
            max_depth=3,
            branches_per_node=2
        )
        
        # Should explore multiple paths
        assert result.paths_explored > 0
        assert result.best_path
        assert len(result.best_path.nodes) > 0
        assert result.total_nodes > 0
    
    @pytest.mark.asyncio
    async def test_best_path_selection(self):
        """Test that ToT selects the best path."""
        reasoner = TreeOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="What is 2 + 2?",
            max_depth=2,
            branches_per_node=2
        )
        
        # Best path should have highest score
        assert result.best_path.total_score >= 0
        
        if result.alternative_paths:
            for alt_path in result.alternative_paths:
                assert result.best_path.total_score >= alt_path.total_score
    
    @pytest.mark.asyncio
    async def test_reasoning_trace(self):
        """Test that reasoning trace is generated."""
        reasoner = TreeOfThoughtReasoner()
        
        result = await reasoner.reason(
            question="What is the capital of France?",
            max_depth=2,
            branches_per_node=2
        )
        
        assert result.best_path.reasoning_trace
        assert result.best_path.solution
        assert "→" in result.best_path.reasoning_trace  # Path separator


@pytest.mark.asyncio
async def test_cot_vs_tot_comparison():
    """Compare CoT and ToT on the same problem."""
    question = "If 3 apples cost $1.50, how much do 7 apples cost?"
    
    # Run both reasoners
    cot_reasoner = ChainOfThoughtReasoner()
    tot_reasoner = TreeOfThoughtReasoner()
    
    cot_result = await cot_reasoner.reason(question, max_steps=5)
    tot_result = await tot_reasoner.reason(question, max_depth=3, branches_per_node=2)
    
    # Both should produce results
    assert cot_result.final_answer
    assert tot_result.best_path.solution
    
    # Both should mention 3.50
    assert "3.5" in cot_result.final_answer or "$3.50" in cot_result.final_answer
