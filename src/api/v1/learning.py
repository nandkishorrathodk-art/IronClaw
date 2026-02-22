"""
Learning & Self-Improvement API endpoints
"""

from typing import List, Optional, Dict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from src.database.connection import get_db_session
from src.database.models import User
from src.api.auth import get_current_user
from src.cognitive.learning import (
    PreferenceTracker,
    PerformanceAnalyzer,
    CodeImprover,
    TestingSandbox,
    RollbackManager,
)
from src.cognitive.learning.preference_tracker import FeedbackType
from src.cognitive.llm.router import AIRouter
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/learning", tags=["learning"])


# Request/Response Models

class FeedbackRequest(BaseModel):
    """Request to submit user feedback."""
    message_id: int
    feedback_type: FeedbackType
    model_used: str
    task_type: str
    response_length: int
    comment: Optional[str] = None
    metadata: Optional[Dict] = None


class PreferenceResponse(BaseModel):
    """User preference response."""
    preferred_models: Dict[str, float]
    preferred_tone: str
    preferred_response_length: str
    frequent_tasks: List[str]
    learning_stats: Dict


class PerformanceReportResponse(BaseModel):
    """Performance analysis report."""
    period_start: datetime
    period_end: datetime
    overall_health_score: float
    bottlenecks_count: int
    top_slow_endpoints: List[tuple]
    memory_usage: Dict[str, float]
    cost_by_feature: Dict[str, float]


class ImprovementOpportunityResponse(BaseModel):
    """Code improvement opportunity."""
    file: str
    line: int
    type: str
    severity: str
    description: str
    suggestion: str
    estimated_improvement: str


class DeploymentRequest(BaseModel):
    """Request to deploy an improvement."""
    improvement_id: int
    create_backup: bool = True
    commit_changes: bool = True
    monitor_duration_seconds: int = 300


class DeploymentResponse(BaseModel):
    """Deployment response."""
    success: bool
    improvement_id: int
    deployed_at: Optional[datetime]
    commit_hash: Optional[str]
    message: str


# Endpoints

@router.post("/feedback")
async def submit_feedback(
    feedback: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Submit user feedback for learning.
    
    The system learns from feedback to improve model selection
    and response quality over time.
    """
    try:
        tracker = PreferenceTracker(db)
        
        await tracker.track_feedback(
            user_id=current_user.id,
            message_id=feedback.message_id,
            feedback_type=feedback.feedback_type,
            model_used=feedback.model_used,
            task_type=feedback.task_type,
            response_length=feedback.response_length,
            metadata=feedback.metadata,
        )
        
        return {
            "success": True,
            "message": "Feedback recorded successfully"
        }
        
    except Exception as e:
        logger.error("Failed to submit feedback", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/preferences", response_model=PreferenceResponse)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get learned user preferences.
    
    Returns the system's understanding of your preferences
    based on historical feedback.
    """
    try:
        tracker = PreferenceTracker(db)
        
        # Get preferences
        settings = await tracker.get_preferred_settings(current_user.id)
        stats = await tracker.get_learning_stats(current_user.id)
        
        # Get user's preference object
        if current_user.id in tracker.preferences:
            pref = tracker.preferences[current_user.id]
            return PreferenceResponse(
                preferred_models=pref.preferred_models,
                preferred_tone=pref.preferred_tone,
                preferred_response_length=pref.preferred_response_length,
                frequent_tasks=settings.get("frequent_tasks", []),
                learning_stats=stats,
            )
        
        # Return defaults if no preferences yet
        return PreferenceResponse(
            preferred_models={},
            preferred_tone="professional",
            preferred_response_length="medium",
            frequent_tasks=[],
            learning_stats=stats,
        )
        
    except Exception as e:
        logger.error("Failed to get preferences", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance/report", response_model=PerformanceReportResponse)
async def get_performance_report(
    hours: int = 24,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get performance analysis report.
    
    Analyzes system performance over the specified time period
    and identifies bottlenecks and improvement opportunities.
    """
    try:
        analyzer = PerformanceAnalyzer(db)
        report = await analyzer.analyze_performance(hours=hours)
        
        return PerformanceReportResponse(
            period_start=report.period_start,
            period_end=report.period_end,
            overall_health_score=report.overall_health_score,
            bottlenecks_count=len(report.bottlenecks),
            top_slow_endpoints=report.top_slow_endpoints,
            memory_usage=report.memory_trends,
            cost_by_feature=report.cost_by_feature,
        )
        
    except Exception as e:
        logger.error("Failed to get performance report", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/improvements/opportunities")
async def get_improvement_opportunities(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get code improvement opportunities.
    
    Analyzes the codebase and identifies potential improvements
    for performance, memory usage, and code quality.
    """
    try:
        # Import here to avoid circular imports
        from src.config import settings
        
        ai_router = AIRouter()
        perf_analyzer = PerformanceAnalyzer(db)
        improver = CodeImprover(db, ai_router, perf_analyzer)
        
        opportunities = await improver.get_improvement_opportunities(limit=limit)
        
        return {
            "count": len(opportunities),
            "opportunities": opportunities,
        }
        
    except Exception as e:
        logger.error("Failed to get improvement opportunities", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improvements/{improvement_id}/generate")
async def generate_improvement(
    improvement_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Generate an AI-powered code improvement.
    
    Uses AI to analyze a code issue and generate an improved version.
    The improvement is saved but not automatically deployed.
    """
    try:
        from src.database.models import CodeImprovement
        
        # Get the issue
        improvement = await db.get(CodeImprovement, improvement_id)
        if not improvement:
            raise HTTPException(status_code=404, detail="Improvement not found")
        
        # This endpoint would typically receive a CodeIssue, not an existing improvement
        # For now, return a message
        return {
            "success": False,
            "message": "This endpoint generates improvements from issues. Use /improvements/opportunities first."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate improvement", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improvements/{improvement_id}/test")
async def test_improvement(
    improvement_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Test a code improvement in sandbox.
    
    Runs full test suite in an isolated environment to verify
    the improvement doesn't break anything.
    """
    try:
        from src.database.models import CodeImprovement
        
        improvement = await db.get(CodeImprovement, improvement_id)
        if not improvement:
            raise HTTPException(status_code=404, detail="Improvement not found")
        
        # Test in background
        async def run_tests():
            async with TestingSandbox(db) as sandbox:
                await sandbox.apply_improvement(improvement_id)
                report = await sandbox.run_tests()
                
                # Update improvement with test results
                improvement.test_status = "passed" if report.all_tests_passed else "failed"
                improvement.test_results = {
                    "all_passed": report.all_tests_passed,
                    "recommendation": report.recommendation,
                }
                await db.commit()
                
                logger.info(
                    "Improvement tested",
                    improvement_id=improvement_id,
                    passed=report.all_tests_passed,
                )
        
        background_tasks.add_task(run_tests)
        
        return {
            "success": True,
            "message": "Testing started in background",
            "improvement_id": improvement_id,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to test improvement", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improvements/{improvement_id}/deploy", response_model=DeploymentResponse)
async def deploy_improvement(
    improvement_id: int,
    request: DeploymentRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deploy a code improvement to production.
    
    Deploys the improvement with automatic backup and rollback
    capabilities. Monitors the deployment and automatically
    rolls back if issues are detected.
    """
    try:
        rollback_mgr = RollbackManager(db)
        
        # Deploy the improvement
        record = await rollback_mgr.deploy_improvement(
            improvement_id=improvement_id,
            create_backup=request.create_backup,
            commit_changes=request.commit_changes,
        )
        
        if not record:
            raise HTTPException(status_code=500, detail="Deployment failed")
        
        # Monitor in background
        async def monitor_deployment():
            stable = await rollback_mgr.monitor_and_rollback(
                improvement_id=improvement_id,
                monitoring_duration_seconds=request.monitor_duration_seconds,
            )
            if not stable:
                logger.warning("Deployment unstable, rollback performed", improvement_id=improvement_id)
        
        background_tasks.add_task(monitor_deployment)
        
        return DeploymentResponse(
            success=True,
            improvement_id=improvement_id,
            deployed_at=record.deployed_at,
            commit_hash=record.commit_hash,
            message="Deployment successful, monitoring in progress",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to deploy improvement", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/improvements/{improvement_id}/rollback")
async def rollback_improvement(
    improvement_id: int,
    reason: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Manually rollback a deployed improvement.
    
    Reverts the improvement and restores the original code.
    """
    try:
        rollback_mgr = RollbackManager(db)
        
        result = await rollback_mgr.rollback_improvement(improvement_id, reason)
        
        if not result.success:
            raise HTTPException(status_code=500, detail=result.reason)
        
        return {
            "success": True,
            "improvement_id": improvement_id,
            "reverted_files": result.reverted_files,
            "commit_hash": result.commit_hash,
            "reason": result.reason,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to rollback improvement", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/history")
async def get_deployment_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get deployment history.
    
    Returns recent deployments and their status.
    """
    try:
        rollback_mgr = RollbackManager(db)
        history = await rollback_mgr.get_deployment_history(limit=limit)
        
        return {
            "count": len(history),
            "deployments": history,
        }
        
    except Exception as e:
        logger.error("Failed to get deployment history", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_learning_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Get overall learning system statistics.
    
    Returns metrics about how much the system has learned
    and improved over time.
    """
    try:
        from sqlalchemy import select, func
        from src.database.models import LearningEvent, CodeImprovement, Feedback
        
        # Count learning events
        events_query = select(func.count(LearningEvent.id))
        events_result = await db.execute(events_query)
        total_events = events_result.scalar() or 0
        
        # Count improvements
        improvements_query = select(
            func.count(CodeImprovement.id).label("total"),
            func.sum(CodeImprovement.applied.cast(int)).label("applied"),
            func.sum(CodeImprovement.rolled_back.cast(int)).label("rolled_back"),
        )
        imp_result = await db.execute(improvements_query)
        imp_row = imp_result.first()
        
        # Count feedback
        feedback_query = select(func.count(Feedback.id))
        feedback_result = await db.execute(feedback_query)
        total_feedback = feedback_result.scalar() or 0
        
        return {
            "learning_events": total_events,
            "total_improvements": imp_row.total or 0,
            "applied_improvements": imp_row.applied or 0,
            "rolled_back_improvements": imp_row.rolled_back or 0,
            "success_rate": (
                (imp_row.applied - imp_row.rolled_back) / imp_row.applied
                if imp_row.applied and imp_row.applied > 0
                else 0.0
            ),
            "total_feedback_received": total_feedback,
        }
        
    except Exception as e:
        logger.error("Failed to get learning stats", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
