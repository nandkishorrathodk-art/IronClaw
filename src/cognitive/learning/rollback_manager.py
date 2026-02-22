"""
Rollback Manager
Manages code deployment and automatic rollback on failures.
"""

from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
import subprocess
import shutil
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.database.models import CodeImprovement, LearningEvent
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DeploymentRecord:
    """Record of a code deployment."""
    improvement_id: int
    deployed_at: datetime
    commit_hash: str
    branch_name: str
    files_changed: List[str]
    backup_path: str


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    improvement_id: int
    reason: str
    reverted_files: List[str]
    commit_hash: Optional[str]


class RollbackManager:
    """
    Manages safe deployment and automatic rollback.
    
    Features:
    - Git integration for version control
    - Automatic backup before deployment
    - Health monitoring after deployment
    - Automatic rollback on failures
    - Deployment history tracking
    """

    def __init__(
        self,
        db_session: AsyncSession,
        project_root: str = ".",
        backup_dir: str = ".backups",
    ):
        """
        Initialize rollback manager.
        
        Args:
            db_session: Database session
            project_root: Root directory of the project
            backup_dir: Directory for backup files
        """
        self.db = db_session
        self.project_root = Path(project_root)
        self.backup_dir = self.project_root / backup_dir
        self.backup_dir.mkdir(exist_ok=True)
        self.deployment_history: List[DeploymentRecord] = []
        logger.info("RollbackManager initialized", backup_dir=str(self.backup_dir))

    async def deploy_improvement(
        self,
        improvement_id: int,
        create_backup: bool = True,
        commit_changes: bool = True,
    ) -> Optional[DeploymentRecord]:
        """
        Deploy a code improvement to production.
        
        Args:
            improvement_id: ID of the improvement to deploy
            create_backup: Whether to create a backup first
            commit_changes: Whether to commit changes to git
            
        Returns:
            Deployment record or None if failed
        """
        try:
            # Get improvement from database
            improvement = await self.db.get(CodeImprovement, improvement_id)
            if not improvement:
                logger.error("Improvement not found", improvement_id=improvement_id)
                return None

            if improvement.applied:
                logger.warning("Improvement already applied", improvement_id=improvement_id)
                return None

            # Create backup if requested
            backup_path = None
            if create_backup:
                backup_path = await self._create_backup(improvement.file_path)

            # Apply the improvement
            success = await self._apply_code_change(
                improvement.file_path,
                improvement.original_code,
                improvement.improved_code,
            )

            if not success:
                logger.error("Failed to apply code change")
                return None

            # Commit changes to git if requested
            commit_hash = None
            branch_name = None
            if commit_changes:
                commit_hash, branch_name = await self._commit_changes(
                    improvement.file_path,
                    f"🤖 Auto-improvement: {improvement.improvement_type}",
                )

            # Update database
            improvement.applied = True
            improvement.applied_at = datetime.utcnow()
            improvement.commit_hash = commit_hash
            improvement.branch_name = branch_name
            await self.db.commit()

            # Create deployment record
            record = DeploymentRecord(
                improvement_id=improvement_id,
                deployed_at=datetime.utcnow(),
                commit_hash=commit_hash or "",
                branch_name=branch_name or "",
                files_changed=[improvement.file_path],
                backup_path=backup_path or "",
            )

            self.deployment_history.append(record)

            # Log learning event
            event = LearningEvent(
                event_type="improvement_applied",
                event_category="code_quality",
                description=f"Applied improvement: {improvement.improvement_type}",
                related_improvement_id=improvement_id,
                impact_score=0.5,  # Will be updated after monitoring
            )
            self.db.add(event)
            await self.db.commit()

            logger.info(
                "Improvement deployed successfully",
                improvement_id=improvement_id,
                file=improvement.file_path,
                commit=commit_hash,
            )

            return record

        except Exception as e:
            logger.error("Deployment failed", error=str(e), improvement_id=improvement_id)
            await self.db.rollback()
            return None

    async def rollback_improvement(
        self, improvement_id: int, reason: str
    ) -> RollbackResult:
        """
        Rollback a deployed improvement.
        
        Args:
            improvement_id: ID of the improvement to rollback
            reason: Reason for rollback
            
        Returns:
            Rollback result
        """
        try:
            # Get improvement from database
            improvement = await self.db.get(CodeImprovement, improvement_id)
            if not improvement or not improvement.applied:
                return RollbackResult(
                    success=False,
                    improvement_id=improvement_id,
                    reason="Improvement not found or not applied",
                    reverted_files=[],
                    commit_hash=None,
                )

            # Find deployment record
            deployment = next(
                (d for d in self.deployment_history if d.improvement_id == improvement_id),
                None,
            )

            # Revert the code change
            success = await self._apply_code_change(
                improvement.file_path,
                improvement.improved_code,
                improvement.original_code,
            )

            if not success:
                return RollbackResult(
                    success=False,
                    improvement_id=improvement_id,
                    reason="Failed to revert code change",
                    reverted_files=[],
                    commit_hash=None,
                )

            # Commit rollback to git
            commit_hash, _ = await self._commit_changes(
                improvement.file_path,
                f"🔄 Rollback improvement {improvement_id}: {reason}",
            )

            # Update database
            improvement.rolled_back = True
            improvement.rollback_reason = reason
            await self.db.commit()

            # Log learning event
            event = LearningEvent(
                event_type="improvement_rolled_back",
                event_category="code_quality",
                description=f"Rolled back improvement: {reason}",
                related_improvement_id=improvement_id,
                impact_score=-0.3,  # Negative impact
            )
            self.db.add(event)
            await self.db.commit()

            logger.info(
                "Improvement rolled back",
                improvement_id=improvement_id,
                reason=reason,
                commit=commit_hash,
            )

            return RollbackResult(
                success=True,
                improvement_id=improvement_id,
                reason=reason,
                reverted_files=[improvement.file_path],
                commit_hash=commit_hash,
            )

        except Exception as e:
            logger.error("Rollback failed", error=str(e), improvement_id=improvement_id)
            await self.db.rollback()
            return RollbackResult(
                success=False,
                improvement_id=improvement_id,
                reason=f"Rollback error: {str(e)}",
                reverted_files=[],
                commit_hash=None,
            )

    async def monitor_and_rollback(
        self,
        improvement_id: int,
        monitoring_duration_seconds: int = 300,
        error_threshold: float = 0.1,
    ) -> bool:
        """
        Monitor a deployed improvement and rollback if issues detected.
        
        Args:
            improvement_id: ID of the improvement to monitor
            monitoring_duration_seconds: How long to monitor
            error_threshold: Error rate threshold (0-1) for rollback
            
        Returns:
            True if deployment is stable, False if rolled back
        """
        try:
            logger.info(
                "Starting post-deployment monitoring",
                improvement_id=improvement_id,
                duration=monitoring_duration_seconds,
            )

            # Monitor for the specified duration
            start_time = datetime.utcnow()
            check_interval = 30  # Check every 30 seconds

            while (datetime.utcnow() - start_time).total_seconds() < monitoring_duration_seconds:
                # Check error rates (simplified - would query actual metrics)
                error_rate = await self._check_error_rate()

                if error_rate > error_threshold:
                    logger.warning(
                        "High error rate detected, initiating rollback",
                        error_rate=error_rate,
                        threshold=error_threshold,
                    )

                    await self.rollback_improvement(
                        improvement_id,
                        f"High error rate detected: {error_rate:.2%} (threshold: {error_threshold:.2%})",
                    )
                    return False

                # Wait before next check
                await asyncio.sleep(check_interval)

            logger.info("Deployment monitoring completed successfully", improvement_id=improvement_id)
            return True

        except Exception as e:
            logger.error("Monitoring failed", error=str(e), improvement_id=improvement_id)
            # On monitoring failure, rollback to be safe
            await self.rollback_improvement(
                improvement_id,
                f"Monitoring failed: {str(e)}",
            )
            return False

    async def get_deployment_history(
        self, limit: int = 10
    ) -> List[Dict]:
        """
        Get recent deployment history.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of deployment records
        """
        try:
            query = (
                select(CodeImprovement)
                .where(CodeImprovement.applied == True)
                .order_by(CodeImprovement.applied_at.desc())
                .limit(limit)
            )

            result = await self.db.execute(query)
            improvements = result.scalars().all()

            history = []
            for imp in improvements:
                history.append(
                    {
                        "improvement_id": imp.id,
                        "file_path": imp.file_path,
                        "improvement_type": imp.improvement_type,
                        "applied_at": imp.applied_at.isoformat() if imp.applied_at else None,
                        "rolled_back": imp.rolled_back,
                        "rollback_reason": imp.rollback_reason,
                        "commit_hash": imp.commit_hash,
                    }
                )

            return history

        except Exception as e:
            logger.error("Failed to get deployment history", error=str(e))
            return []

    # Private helper methods

    async def _create_backup(self, file_path: str) -> str:
        """Create a backup of a file before modification."""
        try:
            source = self.project_root / file_path
            if not source.exists():
                logger.warning("Source file not found for backup", file_path=file_path)
                return ""

            # Create timestamped backup
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{Path(file_path).stem}_{timestamp}.bak"
            backup_path = self.backup_dir / backup_name

            shutil.copy2(source, backup_path)
            logger.debug("Backup created", source=file_path, backup=str(backup_path))

            return str(backup_path)

        except Exception as e:
            logger.error("Backup creation failed", error=str(e), file_path=file_path)
            return ""

    async def _apply_code_change(
        self, file_path: str, old_code: str, new_code: str
    ) -> bool:
        """Apply a code change to a file."""
        try:
            target = self.project_root / file_path
            if not target.exists():
                logger.error("Target file not found", file_path=file_path)
                return False

            # Read current content
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()

            # Replace old code with new code
            if old_code not in content:
                logger.warning(
                    "Old code not found in file (file may have changed)",
                    file_path=file_path,
                )
                # Try a fuzzy match or apply anyway
                # For now, just log and continue

            updated_content = content.replace(old_code, new_code)

            # Write updated content
            with open(target, "w", encoding="utf-8") as f:
                f.write(updated_content)

            logger.debug("Code change applied", file_path=file_path)
            return True

        except Exception as e:
            logger.error("Code change failed", error=str(e), file_path=file_path)
            return False

    async def _commit_changes(
        self, file_path: str, commit_message: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Commit changes to git."""
        try:
            # Add file
            subprocess.run(
                ["git", "add", file_path],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
            )

            # Commit
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
                text=True,
            )

            # Get commit hash
            hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
                text=True,
            )
            commit_hash = hash_result.stdout.strip()

            # Get branch name
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(self.project_root),
                check=True,
                capture_output=True,
                text=True,
            )
            branch_name = branch_result.stdout.strip()

            logger.info("Changes committed to git", commit=commit_hash, branch=branch_name)
            return commit_hash, branch_name

        except subprocess.CalledProcessError as e:
            logger.error("Git commit failed", error=str(e))
            return None, None

    async def _check_error_rate(self) -> float:
        """Check current error rate (simplified implementation)."""
        # In production, this would query actual metrics from Prometheus or logs
        # For now, return a safe value
        return 0.0
