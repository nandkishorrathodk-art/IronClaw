"""
Code Improver
Uses AI to analyze code and generate improvements automatically.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import ast
import difflib
import re
import subprocess
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import CodeImprovement, LearningEvent, PerformanceMetric
from src.cognitive.llm.router import AIRouter
from src.cognitive.llm.types import ChatMessage, TaskType
from src.utils.logging import get_logger
from src.cognitive.learning.performance_analyzer import PerformanceAnalyzer

logger = get_logger(__name__)


@dataclass
class CodeIssue:
    """Identified code issue."""
    file_path: str
    line_number: int
    issue_type: str  # slow_query, memory_leak, inefficient_loop, etc.
    severity: str  # critical, high, medium, low
    description: str
    suggestion: str
    estimated_improvement: str


@dataclass
class ImprovementProposal:
    """Proposed code improvement."""
    issue: CodeIssue
    original_code: str
    improved_code: str
    diff: str
    confidence: float  # 0-1, AI's confidence
    test_commands: List[str]
    impact_analysis: str


class CodeImprover:
    """
    Analyzes code and generates AI-powered improvements.
    
    Features:
    - Static code analysis
    - Performance profiling integration
    - AI-powered code generation
    - Automatic formatting and linting
    - Safe testing before deployment
    """

    def __init__(
        self,
        db_session: AsyncSession,
        ai_router: AIRouter,
        performance_analyzer: PerformanceAnalyzer,
        project_root: str = ".",
    ):
        """
        Initialize code improver.
        
        Args:
            db_session: Database session
            ai_router: AI router for code generation
            performance_analyzer: Performance analyzer for identifying issues
            project_root: Root directory of the project
        """
        self.db = db_session
        self.ai_router = ai_router
        self.perf_analyzer = performance_analyzer
        self.project_root = Path(project_root)
        logger.info("CodeImprover initialized", project_root=project_root)

    async def analyze_codebase(self) -> List[CodeIssue]:
        """
        Analyze the codebase for potential improvements.
        
        Returns:
            List of identified code issues
        """
        try:
            issues = []

            # 1. Get performance bottlenecks
            perf_report = await self.perf_analyzer.analyze_performance(hours=24)
            issues.extend(await self._analyze_slow_endpoints(perf_report))

            # 2. Static code analysis
            issues.extend(await self._run_static_analysis())

            # 3. Memory leak detection
            memory_leak = await self.perf_analyzer.detect_memory_leak()
            if memory_leak and memory_leak.get("detected"):
                issues.append(
                    CodeIssue(
                        file_path="unknown",
                        line_number=0,
                        issue_type="memory_leak",
                        severity="critical",
                        description=f"Memory leak detected: {memory_leak['growth_mb']:.1f} MB growth in 24h",
                        suggestion="Review recent code changes for object retention, unclosed files, or circular references",
                        estimated_improvement=f"Save {memory_leak['growth_mb']:.1f} MB",
                    )
                )

            logger.info("Code analysis completed", issues_found=len(issues))
            return issues

        except Exception as e:
            logger.error("Code analysis failed", error=str(e))
            return []

    async def generate_improvement(
        self, issue: CodeIssue
    ) -> Optional[ImprovementProposal]:
        """
        Generate an AI-powered improvement for a code issue.
        
        Args:
            issue: Code issue to fix
            
        Returns:
            Improvement proposal or None if unable to generate
        """
        try:
            # Read the file
            file_path = self.project_root / issue.file_path
            if not file_path.exists():
                logger.warning("File not found", file_path=str(file_path))
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                original_code = f.read()

            # Extract relevant code section (with context)
            lines = original_code.split("\n")
            start_line = max(0, issue.line_number - 10)
            end_line = min(len(lines), issue.line_number + 10)
            code_section = "\n".join(lines[start_line:end_line])

            # Generate improvement using AI
            prompt = f"""You are an expert Python developer. Analyze this code and provide an optimized version.

Issue: {issue.description}
Type: {issue.issue_type}
Severity: {issue.severity}

Code to improve:
```python
{code_section}
```

Provide:
1. The improved code (ONLY the fixed section, properly indented)
2. Explanation of the improvement
3. Expected performance impact

Format your response as:
IMPROVED_CODE:
```python
<your improved code>
```

EXPLANATION:
<explanation>

IMPACT:
<impact estimate>
"""

            messages = [ChatMessage(role="user", content=prompt)]
            response = await self.ai_router.chat(
                messages=messages,
                task_type=TaskType.CODE_GENERATION,
                temperature=0.3,  # Lower temperature for more consistent code
            )

            # Parse AI response
            improved_code = self._extract_code_block(response.content)
            if not improved_code:
                logger.warning("Failed to extract improved code from AI response")
                return None

            # Apply formatting
            improved_code = await self._format_code(improved_code)

            # Generate diff
            diff = "\n".join(
                difflib.unified_diff(
                    code_section.split("\n"),
                    improved_code.split("\n"),
                    fromfile=f"{issue.file_path} (original)",
                    tofile=f"{issue.file_path} (improved)",
                    lineterm="",
                )
            )

            # Extract explanation and impact
            explanation = self._extract_section(response.content, "EXPLANATION")
            impact = self._extract_section(response.content, "IMPACT")

            # Determine confidence based on issue type
            confidence = self._calculate_confidence(issue, improved_code)

            # Generate test commands
            test_commands = [
                "pytest tests/",
                "ruff check src/",
                "mypy src/",
            ]

            proposal = ImprovementProposal(
                issue=issue,
                original_code=code_section,
                improved_code=improved_code,
                diff=diff,
                confidence=confidence,
                test_commands=test_commands,
                impact_analysis=f"{explanation}\n\nExpected impact: {impact}",
            )

            logger.info(
                "Improvement generated",
                file=issue.file_path,
                confidence=confidence,
            )

            return proposal

        except Exception as e:
            logger.error("Failed to generate improvement", error=str(e), issue=issue)
            return None

    async def save_improvement(
        self, proposal: ImprovementProposal
    ) -> Optional[int]:
        """
        Save improvement proposal to database.
        
        Args:
            proposal: Improvement proposal
            
        Returns:
            Improvement ID or None
        """
        try:
            improvement = CodeImprovement(
                file_path=proposal.issue.file_path,
                improvement_type=proposal.issue.issue_type,
                issue_description=proposal.issue.description,
                performance_impact=proposal.issue.severity,
                confidence_score=proposal.confidence,
                original_code=proposal.original_code,
                improved_code=proposal.improved_code,
                diff=proposal.diff,
                test_status="pending",
            )

            self.db.add(improvement)
            await self.db.commit()
            await self.db.refresh(improvement)

            logger.info("Improvement saved", improvement_id=improvement.id)
            return improvement.id

        except Exception as e:
            logger.error("Failed to save improvement", error=str(e))
            await self.db.rollback()
            return None

    async def get_improvement_opportunities(
        self, limit: int = 10
    ) -> List[Dict]:
        """
        Get top improvement opportunities.
        
        Args:
            limit: Maximum number of opportunities to return
            
        Returns:
            List of improvement opportunities
        """
        try:
            issues = await self.analyze_codebase()
            
            # Sort by severity
            severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            issues.sort(key=lambda x: severity_order.get(x.severity, 4))

            opportunities = []
            for issue in issues[:limit]:
                opportunities.append(
                    {
                        "file": issue.file_path,
                        "line": issue.line_number,
                        "type": issue.issue_type,
                        "severity": issue.severity,
                        "description": issue.description,
                        "suggestion": issue.suggestion,
                        "estimated_improvement": issue.estimated_improvement,
                    }
                )

            return opportunities

        except Exception as e:
            logger.error("Failed to get improvement opportunities", error=str(e))
            return []

    # Private helper methods

    async def _analyze_slow_endpoints(self, perf_report) -> List[CodeIssue]:
        """Analyze slow endpoints and create issues."""
        issues = []

        for endpoint, avg_time in perf_report.top_slow_endpoints:
            # Try to find the file/function for this endpoint
            file_path, line_num = await self._find_endpoint_handler(endpoint)

            issues.append(
                CodeIssue(
                    file_path=file_path or "unknown",
                    line_number=line_num or 0,
                    issue_type="slow_endpoint",
                    severity="high" if avg_time > 200 else "medium",
                    description=f"Endpoint {endpoint} is slow: {avg_time:.1f}ms average",
                    suggestion="Consider adding caching, optimizing database queries, or using async operations",
                    estimated_improvement=f"{((avg_time - 100) / avg_time * 100):.0f}% faster",
                )
            )

        return issues

    async def _run_static_analysis(self) -> List[CodeIssue]:
        """Run static code analysis tools."""
        issues = []

        try:
            # Run ruff for linting
            result = subprocess.run(
                ["ruff", "check", "src/", "--output-format=json"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.stdout:
                import json
                ruff_issues = json.loads(result.stdout)

                for ruff_issue in ruff_issues[:10]:  # Limit to top 10
                    issues.append(
                        CodeIssue(
                            file_path=ruff_issue.get("filename", "unknown"),
                            line_number=ruff_issue.get("location", {}).get("row", 0),
                            issue_type="code_quality",
                            severity="low",
                            description=ruff_issue.get("message", "Code quality issue"),
                            suggestion=f"Fix {ruff_issue.get('code', '')} violation",
                            estimated_improvement="Better code quality",
                        )
                    )

        except Exception as e:
            logger.warning("Static analysis failed", error=str(e))

        return issues

    async def _find_endpoint_handler(self, endpoint: str) -> Tuple[Optional[str], Optional[int]]:
        """Find the file and line number for an API endpoint."""
        try:
            # Search for @router.get, @router.post decorators with this endpoint
            api_dir = self.project_root / "src" / "api"
            if not api_dir.exists():
                return None, None

            for py_file in api_dir.rglob("*.py"):
                with open(py_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for i, line in enumerate(lines, 1):
                    if endpoint in line and ("@router" in line or "@app" in line):
                        # Found it!
                        return str(py_file.relative_to(self.project_root)), i

        except Exception as e:
            logger.warning("Failed to find endpoint handler", error=str(e), endpoint=endpoint)

        return None, None

    def _extract_code_block(self, text: str) -> Optional[str]:
        """Extract code block from markdown-formatted text."""
        # Look for ```python ... ``` blocks
        pattern = r"```python\s*\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: look for any ``` blocks
        pattern = r"```\s*\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        return None

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a named section from AI response."""
        pattern = f"{section_name}:\\s*\n(.*?)(?:\n\n|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    async def _format_code(self, code: str) -> str:
        """Format code using black."""
        try:
            # Write to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            # Run black
            result = subprocess.run(
                ["black", "--quiet", temp_path],
                capture_output=True,
                timeout=10,
            )

            # Read formatted code
            with open(temp_path, "r") as f:
                formatted = f.read()

            # Clean up
            Path(temp_path).unlink()

            return formatted

        except Exception as e:
            logger.warning("Code formatting failed", error=str(e))
            return code  # Return original if formatting fails

    def _calculate_confidence(self, issue: CodeIssue, improved_code: str) -> float:
        """Calculate confidence score for the improvement."""
        confidence = 0.5  # Base confidence

        # Increase confidence for well-defined issues
        if issue.issue_type in ["slow_endpoint", "memory_leak", "inefficient_loop"]:
            confidence += 0.2

        # Increase confidence if code is syntactically valid
        try:
            ast.parse(improved_code)
            confidence += 0.2
        except SyntaxError:
            confidence -= 0.3

        # Decrease confidence for complex changes
        if len(improved_code.split("\n")) > 50:
            confidence -= 0.1

        return max(0.0, min(1.0, confidence))
