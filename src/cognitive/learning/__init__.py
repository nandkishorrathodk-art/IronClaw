"""
Learning & Self-Improvement Module
Enables Ironclaw to learn from user interactions and improve itself over time.
"""

from src.cognitive.learning.preference_tracker import PreferenceTracker
from src.cognitive.learning.performance_analyzer import PerformanceAnalyzer
from src.cognitive.learning.code_improver import CodeImprover
from src.cognitive.learning.sandbox import TestingSandbox
from src.cognitive.learning.rollback_manager import RollbackManager

__all__ = [
    "PreferenceTracker",
    "PerformanceAnalyzer",
    "CodeImprover",
    "TestingSandbox",
    "RollbackManager",
]
