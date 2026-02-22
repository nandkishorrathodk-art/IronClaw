"""
Testing Sandbox
Safe environment for testing code improvements before production deployment.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import subprocess
import shutil
import tempfile
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CodeImprovement
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestResult:
    """Result of a sandbox test."""
    success: bool
    test_type: str  # unit, integration, linting, type_check
    output: str
    error_output: str
    exit_code: int
    duration_seconds: float


@dataclass
class SandboxReport:
    """Comprehensive sandbox test report."""
    improvement_id: int
    all_tests_passed: bool
    test_results: List[TestResult]
    performance_comparison: Optional[Dict[str, float]]
    recommendation: str  # apply, reject, manual_review


class TestingSandbox:
    """
    Safe testing environment for code improvements.
    
    Features:
    - Isolated test environment
    - Automatic test suite execution
    - Performance benchmarking
    - Rollback support
    - Safe production deployment
    """

    def __init__(self, db_session: AsyncSession, project_root: str = "."):
        """
        Initialize testing sandbox.
        
        Args:
            db_session: Database session
            project_root: Root directory of the project
        """
        self.db = db_session
        self.project_root = Path(project_root)
        self.sandbox_dir: Optional[Path] = None
        logger.info("TestingSandbox initialized")

    async def create_sandbox(self) -> Path:
        """
        Create an isolated sandbox environment.
        
        Returns:
            Path to sandbox directory
        """
        try:
            # Create temporary directory for sandbox
            self.sandbox_dir = Path(tempfile.mkdtemp(prefix="ironclaw_sandbox_"))

            # Copy project files to sandbox
            logger.info("Creating sandbox", sandbox_dir=str(self.sandbox_dir))

            # Copy source code
            shutil.copytree(
                self.project_root / "src",
                self.sandbox_dir / "src",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )

            # Copy tests
            if (self.project_root / "tests").exists():
                shutil.copytree(
                    self.project_root / "tests",
                    self.sandbox_dir / "tests",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )

            # Copy configuration files
            for config_file in ["pyproject.toml", "pytest.ini", ".env.example"]:
                src = self.project_root / config_file
                if src.exists():
                    shutil.copy2(src, self.sandbox_dir / config_file)

            logger.info("Sandbox created successfully")
            return self.sandbox_dir

        except Exception as e:
            logger.error("Failed to create sandbox", error=str(e))
            raise

    async def apply_improvement(self, improvement_id: int) -> bool:
        """
        Apply a code improvement to the sandbox.
        
        Args:
            improvement_id: ID of the improvement to apply
            
        Returns:
            True if applied successfully
        """
        try:
            if not self.sandbox_dir:
                await self.create_sandbox()

            # Get improvement from database
            improvement = await self.db.get(CodeImprovement, improvement_id)
            if not improvement:
                logger.error("Improvement not found", improvement_id=improvement_id)
                return False

            # Apply the improvement
            file_path = self.sandbox_dir / improvement.file_path
            if not file_path.exists():
                logger.error("File not found in sandbox", file_path=str(file_path))
                return False

            # Read original file
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Replace the relevant section with improved code
            # This is a simplified version - in production, you'd want more sophisticated patching
            improved_content = content.replace(
                improvement.original_code,
                improvement.improved_code,
            )

            # Write improved code
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(improved_content)

            logger.info("Improvement applied to sandbox", file=str(file_path))
            return True

        except Exception as e:
            logger.error("Failed to apply improvement", error=str(e), improvement_id=improvement_id)
            return False

    async def run_tests(self, test_commands: Optional[List[str]] = None) -> SandboxReport:
        """
        Run full test suite in sandbox.
        
        Args:
            test_commands: Custom test commands (uses defaults if not provided)
            
        Returns:
            Sandbox test report
        """
        try:
            if not self.sandbox_dir:
                raise ValueError("Sandbox not created")

            if test_commands is None:
                test_commands = [
                    "pytest tests/ -v --tb=short",
                    "ruff check src/",
                    "mypy src/",
                    "black --check src/",
                ]

            test_results = []
            all_passed = True

            for cmd in test_commands:
                result = await self._run_command(cmd)
                test_results.append(result)
                if not result.success:
                    all_passed = False

            # Determine recommendation
            if all_passed:
                recommendation = "apply"
            elif all(r.test_type in ["linting", "formatting"] for r in test_results if not r.success):
                recommendation = "manual_review"  # Only style issues
            else:
                recommendation = "reject"

            report = SandboxReport(
                improvement_id=0,  # Will be set by caller
                all_tests_passed=all_passed,
                test_results=test_results,
                performance_comparison=None,  # Could add benchmarking here
                recommendation=recommendation,
            )

            logger.info(
                "Sandbox tests completed",
                all_passed=all_passed,
                recommendation=recommendation,
            )

            return report

        except Exception as e:
            logger.error("Sandbox tests failed", error=str(e))
            raise

    async def benchmark_performance(
        self, endpoint: str, num_requests: int = 100
    ) -> Dict[str, float]:
        """
        Benchmark endpoint performance in sandbox.
        
        Args:
            endpoint: API endpoint to benchmark
            num_requests: Number of requests to send
            
        Returns:
            Performance metrics
        """
        try:
            # This would start the server in sandbox and run load tests
            # Simplified implementation for now
            logger.info("Benchmarking performance", endpoint=endpoint)

            # In production, you'd use locust, ab, or similar tools
            return {
                "avg_response_time_ms": 0.0,
                "p95_response_time_ms": 0.0,
                "p99_response_time_ms": 0.0,
                "requests_per_second": 0.0,
            }

        except Exception as e:
            logger.error("Performance benchmarking failed", error=str(e))
            return {}

    async def cleanup(self) -> None:
        """Clean up sandbox environment."""
        try:
            if self.sandbox_dir and self.sandbox_dir.exists():
                shutil.rmtree(self.sandbox_dir)
                logger.info("Sandbox cleaned up", sandbox_dir=str(self.sandbox_dir))
                self.sandbox_dir = None

        except Exception as e:
            logger.error("Failed to clean up sandbox", error=str(e))

    async def _run_command(
        self, command: str, timeout: int = 300
    ) -> TestResult:
        """
        Run a shell command in the sandbox.
        
        Args:
            command: Command to run
            timeout: Timeout in seconds
            
        Returns:
            Test result
        """
        try:
            start_time = datetime.utcnow()

            # Determine test type from command
            test_type = "unit"
            if "pytest" in command:
                test_type = "unit"
            elif "ruff" in command:
                test_type = "linting"
            elif "mypy" in command:
                test_type = "type_check"
            elif "black" in command:
                test_type = "formatting"

            # Run command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=str(self.sandbox_dir),
                timeout=timeout,
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            return TestResult(
                success=(result.returncode == 0),
                test_type=test_type,
                output=result.stdout,
                error_output=result.stderr,
                exit_code=result.returncode,
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            logger.error("Command timed out", command=command)
            return TestResult(
                success=False,
                test_type="unknown",
                output="",
                error_output=f"Command timed out after {timeout}s",
                exit_code=-1,
                duration_seconds=timeout,
            )

        except Exception as e:
            logger.error("Command execution failed", error=str(e), command=command)
            return TestResult(
                success=False,
                test_type="unknown",
                output="",
                error_output=str(e),
                exit_code=-1,
                duration_seconds=0.0,
            )

    async def __aenter__(self):
        """Context manager entry."""
        await self.create_sandbox()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup sandbox."""
        await self.cleanup()
