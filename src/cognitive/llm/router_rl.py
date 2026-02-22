"""
Reinforcement Learning enhanced AI router
Learns from feedback and improves provider selection over time
"""
from typing import Optional, Dict, Any, List
import random
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.cognitive.llm.router import AIRouter
from src.cognitive.llm.types import ChatRequest, ChatResponse, TaskType
from src.database.connection import get_db_session
from src.database.models import RoutingDecision, ProviderPerformance
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RLAIRouter(AIRouter):
    """
    Reinforcement Learning enhanced AI router.
    
    Features:
    - Tracks success rate per model per task type
    - Learns from user feedback (thumbs up/down)
    - Adjusts routing probabilities over time
    - A/B testing with exploration vs exploitation
    - Automatic performance analysis
    """
    
    def __init__(
        self,
        exploration_rate: float = 0.1,
        learning_rate: float = 0.01,
        discount_factor: float = 0.9
    ):
        """
        Initialize RL router.
        
        Args:
            exploration_rate: Probability of trying non-optimal provider (default: 0.1)
            learning_rate: How fast to update probabilities (default: 0.01)
            discount_factor: How much to weight future rewards (default: 0.9)
        """
        super().__init__()
        self.exploration_rate = exploration_rate
        self.learning_rate = learning_rate
        self.discount_factor = discount_factor
        
        # Cache for performance stats (refreshed periodically)
        self._performance_cache: Dict[str, ProviderPerformance] = {}
        self._cache_updated_at: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=5)
    
    async def select_provider_rl(
        self,
        request: ChatRequest,
        session: Optional[AsyncSession] = None
    ) -> tuple[str, bool]:
        """
        Select provider using reinforcement learning.
        
        Args:
            request: Chat request
            session: Database session
            
        Returns:
            (provider_name, is_exploration) tuple
        """
        # Refresh performance cache if needed
        await self._refresh_performance_cache(session)
        
        # Get performance for this task type
        task_key = request.task_type.value
        candidates = [
            (name, perf)
            for name, perf in self._performance_cache.items()
            if perf.task_type == task_key and name in self.providers
        ]
        
        # If no historical data, use default selection
        if not candidates:
            logger.debug(f"No RL data for {task_key}, using default selection")
            return self.select_provider(request), False
        
        # Exploration vs Exploitation
        is_exploration = random.random() < self.exploration_rate
        
        if is_exploration:
            # Explore: choose random provider
            provider_name = random.choice([name for name, _ in candidates])
            logger.info(f"🔍 Exploration: selected {provider_name} for {task_key}")
        else:
            # Exploit: choose best provider based on selection probability
            # Sort by selection probability
            candidates.sort(key=lambda x: x[1].selection_probability, reverse=True)
            provider_name = candidates[0][0]
            logger.info(f"🎯 Exploitation: selected {provider_name} for {task_key} (prob={candidates[0][1].selection_probability:.3f})")
        
        return provider_name, is_exploration
    
    async def chat_with_tracking(
        self,
        request: ChatRequest,
        user_id: Optional[int] = None,
        session: Optional[AsyncSession] = None
    ) -> tuple[ChatResponse, int]:
        """
        Chat with full tracking for reinforcement learning.
        
        Args:
            request: Chat request
            user_id: User ID for tracking
            session: Database session
            
        Returns:
            (response, decision_id) tuple
        """
        # Select provider with RL
        own_session = session is None
        if own_session:
            session = await get_db_session()
        
        try:
            provider_name, is_exploration = await self.select_provider_rl(request, session)
            
            # Override request provider
            request.provider = provider_name
            
            # Get alternative providers
            alternatives = [
                name for name in self.providers.keys()
                if name != provider_name
            ]
            
            # Execute chat
            response = await self.chat(request)
            
            # Create routing decision record
            decision = RoutingDecision(
                user_id=user_id,
                task_type=request.task_type.value,
                prompt_preview=request.messages[-1].content[:500] if request.messages else "",
                selected_provider=response.provider,
                selected_model=response.model,
                alternative_providers=alternatives,
                response_time_ms=response.response_time_ms,
                total_tokens=response.usage.total_tokens,
                cost_usd=response.cost_usd,
                success=True,
                exploration_decision=is_exploration
            )
            
            session.add(decision)
            await session.commit()
            await session.refresh(decision)
            
            logger.info(f"Tracked routing decision: {decision.id}")
            
            return response, decision.id
        
        except Exception as e:
            logger.error(f"Chat with tracking failed: {e}")
            
            # Record failed decision
            if session:
                decision = RoutingDecision(
                    user_id=user_id,
                    task_type=request.task_type.value,
                    selected_provider=request.provider or "unknown",
                    selected_model="unknown",
                    success=False,
                    error_message=str(e)
                )
                session.add(decision)
                await session.commit()
            
            raise
        
        finally:
            if own_session and session:
                await session.close()
    
    async def record_feedback(
        self,
        decision_id: int,
        rating: int,
        feedback: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> None:
        """
        Record user feedback on a routing decision.
        
        Args:
            decision_id: Decision ID to update
            rating: User rating (-1 thumbs down, 0 neutral, 1 thumbs up)
            feedback: Optional text feedback
            session: Database session
        """
        own_session = session is None
        if own_session:
            session = await get_db_session()
        
        try:
            # Get decision
            result = await session.execute(
                select(RoutingDecision).where(RoutingDecision.id == decision_id)
            )
            decision = result.scalar_one_or_none()
            
            if not decision:
                logger.warning(f"Decision {decision_id} not found")
                return
            
            # Update with feedback
            decision.user_rating = rating
            decision.user_feedback = feedback
            
            # Compute reward value
            # Reward formula: rating + cost_efficiency + speed_bonus
            cost_efficiency = max(0, 1.0 - (decision.cost_usd / 0.01))  # Normalize cost
            speed_bonus = max(0, 1.0 - (decision.response_time_ms / 5000))  # Normalize speed
            reward = rating + (cost_efficiency * 0.3) + (speed_bonus * 0.2)
            decision.reward_value = reward
            
            await session.commit()
            
            # Update provider performance
            await self._update_provider_performance(
                provider=decision.selected_provider,
                model=decision.selected_model,
                task_type=decision.task_type,
                reward=reward,
                session=session
            )
            
            logger.info(f"Recorded feedback for decision {decision_id}: rating={rating}, reward={reward:.2f}")
        
        finally:
            if own_session and session:
                await session.close()
    
    async def _refresh_performance_cache(self, session: Optional[AsyncSession] = None) -> None:
        """Refresh performance cache from database."""
        # Check if cache is still valid
        if self._cache_updated_at and datetime.utcnow() - self._cache_updated_at < self._cache_ttl:
            return
        
        own_session = session is None
        if own_session:
            session = await get_db_session()
        
        try:
            # Load all performance records
            result = await session.execute(
                select(ProviderPerformance)
            )
            performances = result.scalars().all()
            
            # Update cache
            self._performance_cache = {}
            for perf in performances:
                key = f"{perf.provider}:{perf.task_type}"
                self._performance_cache[key] = perf
            
            self._cache_updated_at = datetime.utcnow()
            logger.debug(f"Refreshed performance cache: {len(self._performance_cache)} entries")
        
        finally:
            if own_session and session:
                await session.close()
    
    async def _update_provider_performance(
        self,
        provider: str,
        model: str,
        task_type: str,
        reward: float,
        session: AsyncSession
    ) -> None:
        """
        Update provider performance metrics with new reward.
        
        Uses exponential moving average for online learning.
        """
        # Find or create performance record
        result = await session.execute(
            select(ProviderPerformance).where(
                and_(
                    ProviderPerformance.provider == provider,
                    ProviderPerformance.model == model,
                    ProviderPerformance.task_type == task_type
                )
            )
        )
        perf = result.scalar_one_or_none()
        
        if not perf:
            # Create new record
            perf = ProviderPerformance(
                provider=provider,
                model=model,
                task_type=task_type,
                total_requests=1,
                successful_requests=1 if reward > 0 else 0,
                avg_reward=reward,
                selection_probability=0.5
            )
            session.add(perf)
        else:
            # Update existing record with exponential moving average
            perf.total_requests += 1
            if reward > 0:
                perf.successful_requests += 1
            
            # Update average reward (EMA with learning rate)
            perf.avg_reward = (
                (1 - self.learning_rate) * perf.avg_reward +
                self.learning_rate * reward
            )
            
            # Update selection probability based on reward
            # Use softmax-like update: increase prob if reward > avg, decrease otherwise
            delta = self.learning_rate * (reward - perf.avg_reward)
            perf.selection_probability = max(0.1, min(0.9,
                perf.selection_probability + delta
            ))
        
        await session.commit()
        logger.debug(
            f"Updated performance for {provider}/{model} on {task_type}: "
            f"avg_reward={perf.avg_reward:.2f}, prob={perf.selection_probability:.3f}"
        )
    
    async def get_performance_report(
        self,
        task_type: Optional[str] = None,
        session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        Get performance report for all providers.
        
        Args:
            task_type: Filter by task type (optional)
            session: Database session
            
        Returns:
            Performance report dict
        """
        own_session = session is None
        if own_session:
            session = await get_db_session()
        
        try:
            # Build query
            query = select(ProviderPerformance)
            if task_type:
                query = query.where(ProviderPerformance.task_type == task_type)
            
            result = await session.execute(query)
            performances = result.scalars().all()
            
            # Build report
            report = {
                "total_providers": len(performances),
                "providers": []
            }
            
            for perf in performances:
                report["providers"].append({
                    "provider": perf.provider,
                    "model": perf.model,
                    "task_type": perf.task_type,
                    "total_requests": perf.total_requests,
                    "success_rate": perf.successful_requests / perf.total_requests if perf.total_requests > 0 else 0,
                    "avg_reward": perf.avg_reward,
                    "selection_probability": perf.selection_probability,
                })
            
            # Sort by avg reward
            report["providers"].sort(key=lambda x: x["avg_reward"], reverse=True)
            
            return report
        
        finally:
            if own_session and session:
                await session.close()


# Global RL router instance
_rl_router: Optional[RLAIRouter] = None


def get_rl_router() -> RLAIRouter:
    """Get global RL router instance."""
    global _rl_router
    if _rl_router is None:
        _rl_router = RLAIRouter()
    return _rl_router
