"""
Integration tests for Phase 8: Learning & Self-Improvement

Tests all components of the learning system working together:
- Preference tracking and learning convergence
- Performance monitoring and bottleneck detection
- Code improvement generation and testing
- Deployment and rollback mechanisms
- Long-term learning behavior
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.cognitive.learning.preference_tracker import PreferenceTracker, FeedbackType
from src.cognitive.learning.performance_analyzer import PerformanceAnalyzer
from src.cognitive.learning.code_improver import CodeImprover, CodeIssue
from src.cognitive.learning.sandbox import TestingSandbox
from src.cognitive.learning.rollback_manager import RollbackManager
from src.database.models import (
    User, Feedback, PerformanceMetric, CodeImprovement, LearningEvent
)


@pytest.fixture
async def test_user(db_session: AsyncSession):
    """Create a test user."""
    user = User(
        email="test@ironclaw.ai",
        username="test_user",
        hashed_password="hashed_password_here",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def preference_tracker(db_session: AsyncSession):
    """Create preference tracker instance."""
    return PreferenceTracker(db_session, learning_rate=0.2)


@pytest.fixture
async def performance_analyzer(db_session: AsyncSession):
    """Create performance analyzer instance."""
    return PerformanceAnalyzer(db_session)


@pytest.mark.asyncio
class TestPreferenceLearning:
    """Test preference tracking and learning convergence."""

    async def test_feedback_tracking_updates_preferences(
        self, preference_tracker, test_user, db_session
    ):
        """Test that feedback correctly updates user preferences."""
        # Submit positive feedback for GPT-4
        await preference_tracker.track_feedback(
            user_id=test_user.id,
            message_id=1,
            feedback_type=FeedbackType.THUMBS_UP,
            model_used="gpt-4",
            task_type="code_generation",
            response_length=500,
        )

        # Check preferences updated
        preferred_model = await preference_tracker.get_preferred_model(
            test_user.id, "code_generation"
        )
        assert preferred_model == "gpt-4"

        # Get stats
        stats = await preference_tracker.get_learning_stats(test_user.id)
        assert stats["total_models_tried"] >= 1
        assert "gpt-4" in stats["preferred_models"]
        assert stats["preferred_models"]["gpt-4"] > 0.5

    async def test_learning_convergence_over_time(
        self, preference_tracker, test_user, db_session
    ):
        """Test that preferences converge to correct values with repeated feedback."""
        # Simulate 20 interactions with GPT-4 (all positive)
        for i in range(20):
            await preference_tracker.track_feedback(
                user_id=test_user.id,
                message_id=i,
                feedback_type=FeedbackType.THUMBS_UP,
                model_used="gpt-4",
                task_type="conversation",
                response_length=300,
            )

        # Simulate 5 interactions with Claude (all negative)
        for i in range(20, 25):
            await preference_tracker.track_feedback(
                user_id=test_user.id,
                message_id=i,
                feedback_type=FeedbackType.THUMBS_DOWN,
                model_used="claude",
                task_type="conversation",
                response_length=300,
            )

        # Check convergence
        stats = await preference_tracker.get_learning_stats(test_user.id)
        gpt4_score = stats["preferred_models"].get("gpt-4", 0)
        claude_score = stats["preferred_models"].get("claude", 0)

        # GPT-4 should have higher score than Claude
        assert gpt4_score > claude_score
        assert gpt4_score > 0.7  # Should converge towards 1.0
        assert claude_score < 0.3  # Should converge towards 0.0

    async def test_time_based_pattern_learning(
        self, preference_tracker, test_user, db_session
    ):
        """Test learning of time-based usage patterns."""
        # Simulate morning tasks
        with patch('src.cognitive.learning.preference_tracker.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 9, 0)  # 9 AM
            mock_dt.utcnow.return_value = datetime(2024, 1, 1, 9, 0)

            for i in range(10):
                await preference_tracker.track_feedback(
                    user_id=test_user.id,
                    message_id=i,
                    feedback_type=FeedbackType.THUMBS_UP,
                    model_used="gpt-4",
                    task_type="code_generation",
                    response_length=500,
                )

        # Predict activity for morning time
        with patch('src.cognitive.learning.preference_tracker.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 2, 9, 30)  # Next day, 9:30 AM
            
            prediction = await preference_tracker.predict_next_activity(
                test_user.id
            )

        # Should predict code_generation for morning
        assert prediction == "code_generation"


@pytest.mark.asyncio
class TestPerformanceMonitoring:
    """Test performance monitoring and bottleneck detection."""

    async def test_record_and_analyze_metrics(
        self, performance_analyzer, db_session
    ):
        """Test recording metrics and analyzing performance."""
        # Record some slow endpoint metrics
        for i in range(10):
            await performance_analyzer.record_metric(
                metric_name="api_response_time",
                value=150.0 + (i * 10),  # Increasing response times
                unit="ms",
                metric_type="response_time",
                endpoint="/api/v1/chat",
            )

        # Flush metrics to database
        await performance_analyzer._flush_metrics()

        # Analyze performance
        report = await performance_analyzer.analyze_performance(hours=1)

        # Check report contains bottlenecks
        assert report.overall_health_score < 100  # Should detect issues
        assert len(report.bottlenecks) > 0
        assert any(b.issue_type == "slow_response" for b in report.bottlenecks)

    async def test_memory_leak_detection(
        self, performance_analyzer, db_session
    ):
        """Test memory leak detection."""
        # Simulate increasing memory usage
        base_time = datetime.utcnow()
        for i in range(10):
            metric = PerformanceMetric(
                metric_name="memory_usage",
                metric_type="gauge",
                value=1000.0 + (i * 150),  # Increasing by 150MB each hour
                unit="mb",
                period_start=base_time + timedelta(hours=i),
                period_end=base_time + timedelta(hours=i+1),
                sample_count=100,
            )
            db_session.add(metric)

        await db_session.commit()

        # Detect memory leak
        leak_info = await performance_analyzer.detect_memory_leak(
            hours=10, threshold_mb=500
        )

        assert leak_info is not None
        assert leak_info["detected"] is True
        assert leak_info["growth_mb"] > 500
        assert leak_info["growth_rate_mb_per_hour"] > 0

    async def test_current_memory_usage(self, performance_analyzer):
        """Test getting current memory usage."""
        usage = await performance_analyzer.get_current_memory_usage()

        assert "process_rss_mb" in usage
        assert "system_total_mb" in usage
        assert usage["process_rss_mb"] > 0
        assert usage["system_total_mb"] > 0


@pytest.mark.asyncio
class TestCodeImprovement:
    """Test code improvement generation and analysis."""

    async def test_analyze_codebase_finds_issues(
        self, performance_analyzer, db_session
    ):
        """Test that codebase analysis identifies issues."""
        # Create mock AI router and code improver
        mock_router = Mock()
        improver = CodeImprover(db_session, mock_router, performance_analyzer)

        # Mock performance report with slow endpoints
        mock_report = Mock()
        mock_report.top_slow_endpoints = [
            ("/api/v1/slow-endpoint", 250.0),
            ("/api/v1/chat", 180.0),
        ]
        mock_report.bottlenecks = []

        with patch.object(performance_analyzer, 'analyze_performance', return_value=mock_report):
            issues = await improver.analyze_codebase()

        # Should find issues from slow endpoints
        assert len(issues) > 0
        assert any(issue.issue_type == "slow_endpoint" for issue in issues)

    async def test_get_improvement_opportunities(
        self, performance_analyzer, db_session
    ):
        """Test getting improvement opportunities."""
        mock_router = Mock()
        improver = CodeImprover(db_session, mock_router, performance_analyzer)

        # Mock analyze_codebase to return test issues
        test_issues = [
            CodeIssue(
                file_path="src/api/v1/chat.py",
                line_number=50,
                issue_type="slow_endpoint",
                severity="high",
                description="Slow endpoint detected",
                suggestion="Add caching",
                estimated_improvement="50% faster",
            )
        ]

        with patch.object(improver, 'analyze_codebase', return_value=test_issues):
            opportunities = await improver.get_improvement_opportunities(limit=10)

        assert len(opportunities) > 0
        assert opportunities[0]["type"] == "slow_endpoint"
        assert opportunities[0]["severity"] == "high"


@pytest.mark.asyncio
class TestSandboxTesting:
    """Test sandbox testing environment."""

    async def test_sandbox_creation_and_cleanup(self, db_session):
        """Test sandbox can be created and cleaned up."""
        sandbox = TestingSandbox(db_session)

        # Create sandbox
        sandbox_path = await sandbox.create_sandbox()
        assert sandbox_path.exists()
        assert (sandbox_path / "src").exists()

        # Cleanup
        await sandbox.cleanup()
        assert not sandbox_path.exists()

    async def test_sandbox_context_manager(self, db_session):
        """Test sandbox works as context manager."""
        async with TestingSandbox(db_session) as sandbox:
            assert sandbox.sandbox_dir is not None
            assert sandbox.sandbox_dir.exists()
            sandbox_dir = sandbox.sandbox_dir

        # Should be cleaned up after exiting context
        assert not sandbox_dir.exists()

    async def test_run_tests_in_sandbox(self, db_session):
        """Test running tests in sandbox."""
        async with TestingSandbox(db_session) as sandbox:
            # Run a simple test
            result = await sandbox._run_command("echo test", timeout=10)

            assert result.success is True
            assert "test" in result.output


@pytest.mark.asyncio
class TestDeploymentAndRollback:
    """Test deployment and rollback mechanisms."""

    async def test_deployment_creates_backup(self, db_session):
        """Test that deployment creates backup before applying changes."""
        rollback_mgr = RollbackManager(db_session, project_root=".")

        # Create test improvement
        improvement = CodeImprovement(
            file_path="test_file.py",
            improvement_type="optimization",
            issue_description="Test optimization",
            performance_impact="high",
            confidence_score=0.9,
            original_code="print('old')",
            improved_code="print('new')",
            diff="diff here",
            test_status="pending",
        )
        db_session.add(improvement)
        await db_session.commit()
        await db_session.refresh(improvement)

        # Mock file operations
        with patch.object(rollback_mgr, '_create_backup', return_value="/backup/path"):
            with patch.object(rollback_mgr, '_apply_code_change', return_value=True):
                with patch.object(rollback_mgr, '_commit_changes', return_value=("abc123", "main")):
                    record = await rollback_mgr.deploy_improvement(
                        improvement.id,
                        create_backup=True,
                        commit_changes=True,
                    )

        assert record is not None
        assert record.improvement_id == improvement.id
        assert record.commit_hash == "abc123"

    async def test_rollback_reverts_changes(self, db_session):
        """Test that rollback correctly reverts changes."""
        rollback_mgr = RollbackManager(db_session)

        # Create and deploy improvement
        improvement = CodeImprovement(
            file_path="test_file.py",
            improvement_type="optimization",
            issue_description="Test",
            performance_impact="high",
            confidence_score=0.9,
            original_code="old",
            improved_code="new",
            diff="diff",
            applied=True,
            applied_at=datetime.utcnow(),
        )
        db_session.add(improvement)
        await db_session.commit()
        await db_session.refresh(improvement)

        # Mock operations
        with patch.object(rollback_mgr, '_apply_code_change', return_value=True):
            with patch.object(rollback_mgr, '_commit_changes', return_value=("def456", "main")):
                result = await rollback_mgr.rollback_improvement(
                    improvement.id,
                    reason="Test rollback"
                )

        assert result.success is True
        assert result.improvement_id == improvement.id
        assert "Test rollback" in result.reason

    async def test_deployment_history_tracking(self, db_session):
        """Test that deployment history is tracked correctly."""
        rollback_mgr = RollbackManager(db_session)

        # Create multiple improvements
        for i in range(3):
            improvement = CodeImprovement(
                file_path=f"file{i}.py",
                improvement_type="optimization",
                issue_description=f"Test {i}",
                performance_impact="medium",
                confidence_score=0.8,
                original_code="old",
                improved_code="new",
                diff="diff",
                applied=True,
                applied_at=datetime.utcnow(),
                commit_hash=f"hash{i}",
            )
            db_session.add(improvement)

        await db_session.commit()

        # Get deployment history
        history = await rollback_mgr.get_deployment_history(limit=10)

        assert len(history) >= 3
        assert all("improvement_id" in h for h in history)
        assert all("commit_hash" in h for h in history)


@pytest.mark.asyncio
class TestEndToEndLearningWorkflow:
    """Test complete end-to-end learning workflow."""

    async def test_complete_learning_cycle(
        self, test_user, db_session, preference_tracker, performance_analyzer
    ):
        """Test complete learning cycle from feedback to improvement."""
        # Step 1: User gives feedback
        for i in range(5):
            await preference_tracker.track_feedback(
                user_id=test_user.id,
                message_id=i,
                feedback_type=FeedbackType.THUMBS_UP,
                model_used="gpt-4",
                task_type="conversation",
                response_length=500,
            )

        # Step 2: System learns preference
        preferred = await preference_tracker.get_preferred_model(
            test_user.id, "conversation"
        )
        assert preferred == "gpt-4"

        # Step 3: Record performance metrics
        for i in range(5):
            await performance_analyzer.record_metric(
                metric_name="response_time",
                value=100.0,
                unit="ms",
                metric_type="response_time",
                endpoint="/api/v1/chat",
            )

        await performance_analyzer._flush_metrics()

        # Step 4: Analyze performance
        report = await performance_analyzer.analyze_performance(hours=1)
        assert report.overall_health_score > 0

        # Step 5: Check learning stats
        stats = await preference_tracker.get_learning_stats(test_user.id)
        assert stats["total_models_tried"] > 0
        assert stats["task_preferences_learned"] > 0

    async def test_long_term_learning_stability(
        self, test_user, preference_tracker, db_session
    ):
        """Test that learning remains stable over long periods."""
        # Simulate 100 interactions over "time"
        for i in range(100):
            feedback_type = (
                FeedbackType.THUMBS_UP if i % 3 != 0 
                else FeedbackType.THUMBS_DOWN
            )
            
            await preference_tracker.track_feedback(
                user_id=test_user.id,
                message_id=i,
                feedback_type=feedback_type,
                model_used="gpt-4" if i % 2 == 0 else "claude",
                task_type="conversation",
                response_length=500,
            )

        # Check preferences are stable and meaningful
        stats = await preference_tracker.get_learning_stats(test_user.id)
        assert stats["total_models_tried"] == 2
        assert stats["preference_confidence"] > 0  # Should have clear preference

        # Scores should be between 0 and 1
        for model, score in stats["preferred_models"].items():
            assert 0.0 <= score <= 1.0


@pytest.mark.asyncio
class TestLearningSystemIntegration:
    """Test integration between all learning components."""

    async def test_all_components_work_together(
        self, test_user, db_session
    ):
        """Test that all learning components integrate correctly."""
        # Initialize all components
        tracker = PreferenceTracker(db_session)
        analyzer = PerformanceAnalyzer(db_session)
        
        # 1. Track user preference
        await tracker.track_feedback(
            user_id=test_user.id,
            message_id=1,
            feedback_type=FeedbackType.THUMBS_UP,
            model_used="gpt-4",
            task_type="code_generation",
            response_length=500,
        )

        # 2. Record performance metric
        await analyzer.record_metric(
            metric_name="response_time",
            value=150.0,
            unit="ms",
            metric_type="response_time",
            endpoint="/api/v1/chat",
        )

        # 3. Create learning event
        event = LearningEvent(
            user_id=test_user.id,
            event_type="preference_update",
            event_category="learning",
            description="User preference updated",
            impact_score=0.5,
        )
        db_session.add(event)
        await db_session.commit()

        # Verify all data is connected
        stats = await tracker.get_learning_stats(test_user.id)
        assert stats is not None

        memory_usage = await analyzer.get_current_memory_usage()
        assert memory_usage["process_rss_mb"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
