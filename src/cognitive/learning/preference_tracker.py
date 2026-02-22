"""
User Preference Tracking System
Learns from user feedback and adapts over time.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal
from enum import Enum
import json
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict
import asyncio

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Feedback, Conversation, Message
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FeedbackType(str, Enum):
    """Types of user feedback."""
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    RATING_1 = "rating_1"
    RATING_2 = "rating_2"
    RATING_3 = "rating_3"
    RATING_4 = "rating_4"
    RATING_5 = "rating_5"


class TimeOfDay(str, Enum):
    """Time of day categories."""
    MORNING = "morning"      # 6-12
    AFTERNOON = "afternoon"  # 12-18
    EVENING = "evening"      # 18-22
    NIGHT = "night"          # 22-6


@dataclass
class UserPreference:
    """User preference data structure."""
    user_id: int
    preferred_models: Dict[str, float]  # model_name -> preference_score (0-1)
    preferred_tone: str  # casual, professional, friendly, etc.
    preferred_response_length: str  # short, medium, long
    time_patterns: Dict[str, Dict[str, float]]  # time_of_day -> {activity: frequency}
    task_model_preferences: Dict[str, str]  # task_type -> preferred_model
    learning_rate: float = 0.1
    last_updated: datetime = None

    def __post_init__(self) -> None:
        """Initialize last_updated if not set."""
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()


class PreferenceTracker:
    """
    Tracks user preferences and learns from feedback.
    
    Features:
    - Learns from thumbs up/down feedback
    - Tracks preferred AI models per task type
    - Learns preferred response styles
    - Identifies time-based patterns
    - Adapts over time with exponential moving average
    """

    def __init__(self, db_session: AsyncSession, learning_rate: float = 0.1):
        """
        Initialize preference tracker.
        
        Args:
            db_session: Database session for persistence
            learning_rate: How quickly to adapt (0-1, higher = faster adaptation)
        """
        self.db = db_session
        self.learning_rate = learning_rate
        self.preferences: Dict[int, UserPreference] = {}
        logger.info("PreferenceTracker initialized", learning_rate=learning_rate)

    async def track_feedback(
        self,
        user_id: int,
        message_id: int,
        feedback_type: FeedbackType,
        model_used: str,
        task_type: str,
        response_length: int,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Track user feedback and update preferences.
        
        Args:
            user_id: User ID
            message_id: Message ID that received feedback
            feedback_type: Type of feedback (thumbs_up, thumbs_down, rating)
            model_used: AI model that generated the response
            task_type: Type of task (conversation, code_generation, etc.)
            response_length: Length of response in characters
            metadata: Additional metadata (tone, style, etc.)
        """
        try:
            # Get or create user preference
            if user_id not in self.preferences:
                await self._load_user_preferences(user_id)

            pref = self.preferences[user_id]

            # Calculate feedback score (0-1)
            score = self._feedback_to_score(feedback_type)

            # Update model preference with exponential moving average
            current_score = pref.preferred_models.get(model_used, 0.5)
            new_score = (1 - self.learning_rate) * current_score + self.learning_rate * score
            pref.preferred_models[model_used] = new_score

            # Update task-specific model preference
            if score > 0.7:  # Only update on positive feedback
                pref.task_model_preferences[task_type] = model_used

            # Update response length preference
            length_category = self._categorize_length(response_length)
            if score > 0.7:
                pref.preferred_response_length = length_category

            # Update tone preference from metadata
            if metadata and "tone" in metadata and score > 0.7:
                pref.preferred_tone = metadata["tone"]

            # Track time-based patterns
            time_of_day = self._get_time_of_day()
            if time_of_day not in pref.time_patterns:
                pref.time_patterns[time_of_day] = {}
            
            if task_type not in pref.time_patterns[time_of_day]:
                pref.time_patterns[time_of_day][task_type] = 0.0
            
            current_freq = pref.time_patterns[time_of_day][task_type]
            pref.time_patterns[time_of_day][task_type] = (
                (1 - self.learning_rate) * current_freq + self.learning_rate * 1.0
            )

            # Update timestamp
            pref.last_updated = datetime.utcnow()

            # Save to database
            await self._save_user_preferences(pref)

            logger.info(
                "Feedback tracked",
                user_id=user_id,
                model=model_used,
                task=task_type,
                feedback=feedback_type,
                new_score=new_score,
            )

        except Exception as e:
            logger.error("Failed to track feedback", error=str(e), user_id=user_id)

    async def get_preferred_model(
        self, user_id: int, task_type: str, current_time: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Get user's preferred model for a specific task type.
        
        Args:
            user_id: User ID
            task_type: Type of task
            current_time: Current time (for time-based patterns)
            
        Returns:
            Preferred model name or None if no preference
        """
        try:
            if user_id not in self.preferences:
                await self._load_user_preferences(user_id)

            pref = self.preferences[user_id]

            # Check task-specific preference first
            if task_type in pref.task_model_preferences:
                return pref.task_model_preferences[task_type]

            # Fall back to overall best-performing model
            if pref.preferred_models:
                return max(pref.preferred_models.items(), key=lambda x: x[1])[0]

            return None

        except Exception as e:
            logger.error("Failed to get preferred model", error=str(e), user_id=user_id)
            return None

    async def get_preferred_settings(self, user_id: int) -> Dict[str, any]:
        """
        Get user's preferred settings for responses.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary of preferred settings
        """
        try:
            if user_id not in self.preferences:
                await self._load_user_preferences(user_id)

            pref = self.preferences[user_id]

            return {
                "tone": pref.preferred_tone,
                "response_length": pref.preferred_response_length,
                "time_of_day": self._get_time_of_day(),
                "frequent_tasks": self._get_frequent_tasks(pref),
            }

        except Exception as e:
            logger.error("Failed to get preferred settings", error=str(e), user_id=user_id)
            return {}

    async def predict_next_activity(
        self, user_id: int, current_time: Optional[datetime] = None
    ) -> Optional[str]:
        """
        Predict user's next likely activity based on time patterns.
        
        Args:
            user_id: User ID
            current_time: Current time (defaults to now)
            
        Returns:
            Predicted activity/task type or None
        """
        try:
            if user_id not in self.preferences:
                await self._load_user_preferences(user_id)

            pref = self.preferences[user_id]
            time_of_day = self._get_time_of_day(current_time)

            if time_of_day not in pref.time_patterns:
                return None

            # Get most frequent activity for this time of day
            patterns = pref.time_patterns[time_of_day]
            if not patterns:
                return None

            return max(patterns.items(), key=lambda x: x[1])[0]

        except Exception as e:
            logger.error("Failed to predict activity", error=str(e), user_id=user_id)
            return None

    async def get_learning_stats(self, user_id: int) -> Dict[str, any]:
        """
        Get statistics about learned preferences.
        
        Args:
            user_id: User ID
            
        Returns:
            Statistics dictionary
        """
        try:
            if user_id not in self.preferences:
                await self._load_user_preferences(user_id)

            pref = self.preferences[user_id]

            # Calculate model preference confidence (variance)
            model_scores = list(pref.preferred_models.values())
            confidence = max(model_scores) - min(model_scores) if model_scores else 0

            return {
                "total_models_tried": len(pref.preferred_models),
                "task_preferences_learned": len(pref.task_model_preferences),
                "time_patterns_learned": sum(
                    len(tasks) for tasks in pref.time_patterns.values()
                ),
                "preference_confidence": confidence,
                "last_updated": pref.last_updated.isoformat(),
                "preferred_models": {
                    model: round(score, 3)
                    for model, score in sorted(
                        pref.preferred_models.items(), key=lambda x: x[1], reverse=True
                    )[:5]
                },
            }

        except Exception as e:
            logger.error("Failed to get learning stats", error=str(e), user_id=user_id)
            return {}

    # Private helper methods

    def _feedback_to_score(self, feedback: FeedbackType) -> float:
        """Convert feedback type to numeric score (0-1)."""
        mapping = {
            FeedbackType.THUMBS_DOWN: 0.0,
            FeedbackType.RATING_1: 0.2,
            FeedbackType.RATING_2: 0.4,
            FeedbackType.RATING_3: 0.6,
            FeedbackType.RATING_4: 0.8,
            FeedbackType.RATING_5: 1.0,
            FeedbackType.THUMBS_UP: 1.0,
        }
        return mapping.get(feedback, 0.5)

    def _categorize_length(self, char_count: int) -> str:
        """Categorize response length."""
        if char_count < 200:
            return "short"
        elif char_count < 1000:
            return "medium"
        else:
            return "long"

    def _get_time_of_day(self, dt: Optional[datetime] = None) -> TimeOfDay:
        """Get time of day category."""
        if dt is None:
            dt = datetime.now()
        
        hour = dt.hour
        if 6 <= hour < 12:
            return TimeOfDay.MORNING
        elif 12 <= hour < 18:
            return TimeOfDay.AFTERNOON
        elif 18 <= hour < 22:
            return TimeOfDay.EVENING
        else:
            return TimeOfDay.NIGHT

    def _get_frequent_tasks(self, pref: UserPreference, top_n: int = 3) -> List[str]:
        """Get most frequent tasks across all times."""
        task_counts = Counter()
        for time_patterns in pref.time_patterns.values():
            for task, freq in time_patterns.items():
                task_counts[task] += freq
        
        return [task for task, _ in task_counts.most_common(top_n)]

    async def _load_user_preferences(self, user_id: int) -> None:
        """Load user preferences from database."""
        try:
            # Query user's feedback history
            query = select(Feedback).where(Feedback.user_id == user_id)
            result = await self.db.execute(query)
            feedbacks = result.scalars().all()

            # Initialize default preferences
            pref = UserPreference(
                user_id=user_id,
                preferred_models={},
                preferred_tone="professional",
                preferred_response_length="medium",
                time_patterns={},
                task_model_preferences={},
            )

            # Build preferences from historical feedback
            # (This is a simplified version - in production, you'd want
            # to aggregate this more efficiently)
            for fb in feedbacks:
                if fb.model_used:
                    score = self._feedback_to_score(FeedbackType(fb.feedback_type))
                    current = pref.preferred_models.get(fb.model_used, 0.5)
                    pref.preferred_models[fb.model_used] = (
                        (current + score) / 2
                    )  # Simple average

            self.preferences[user_id] = pref
            logger.debug("Loaded user preferences", user_id=user_id)

        except Exception as e:
            logger.error("Failed to load user preferences", error=str(e), user_id=user_id)
            # Create default preferences on error
            self.preferences[user_id] = UserPreference(
                user_id=user_id,
                preferred_models={},
                preferred_tone="professional",
                preferred_response_length="medium",
                time_patterns={},
                task_model_preferences={},
            )

    async def _save_user_preferences(self, pref: UserPreference) -> None:
        """Save user preferences to database."""
        # For now, preferences are stored in Feedback table
        # In production, you might want a dedicated UserPreferences table
        pass
