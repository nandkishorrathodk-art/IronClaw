"""
Performance Analyzer
Monitors system performance and identifies bottlenecks for self-improvement.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import asyncio
import psutil

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PerformanceMetric, AIUsageLog, Message, LearningEvent
from src.utils.logging import get_logger
from src.utils.metrics import metrics

logger = get_logger(__name__)


@dataclass
class PerformanceBottleneck:
    """Identified performance bottleneck."""
    location: str  # Endpoint or component
    issue_type: str  # slow_response, high_memory, high_error_rate
    severity: str  # critical, high, medium, low
    current_value: float
    threshold: float
    recommendation: str
    estimated_impact: str  # Estimated improvement if fixed


@dataclass
class PerformanceReport:
    """Performance analysis report."""
    period_start: datetime
    period_end: datetime
    bottlenecks: List[PerformanceBottleneck]
    top_slow_endpoints: List[Tuple[str, float]]  # (endpoint, avg_time_ms)
    memory_trends: Dict[str, float]
    error_rate_by_endpoint: Dict[str, float]
    cost_by_feature: Dict[str, float]
    overall_health_score: float  # 0-100


class PerformanceAnalyzer:
    """
    Analyzes system performance and identifies improvement opportunities.
    
    Features:
    - Real-time performance metric tracking
    - Slow endpoint detection (<100ms target)
    - Memory leak detection
    - Error rate monitoring
    - Cost per feature analysis
    - Automatic bottleneck identification
    """

    # Performance thresholds
    RESPONSE_TIME_THRESHOLD_MS = 100
    MEMORY_WARNING_THRESHOLD_MB = 7168  # 7GB (out of 8GB budget)
    ERROR_RATE_THRESHOLD = 0.05  # 5%
    COST_PER_REQUEST_THRESHOLD_USD = 0.01  # $0.01 per request

    def __init__(self, db_session: AsyncSession):
        """
        Initialize performance analyzer.
        
        Args:
            db_session: Database session for storing metrics
        """
        self.db = db_session
        self.metrics_buffer: List[Dict] = []
        self.buffer_size = 100
        logger.info("PerformanceAnalyzer initialized")

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        unit: str,
        metric_type: str = "gauge",
        endpoint: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> None:
        """
        Record a performance metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement (ms, bytes, percent, count)
            metric_type: Type of metric (gauge, counter, histogram)
            endpoint: API endpoint if applicable
            metadata: Additional context
        """
        try:
            metric_data = {
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "metric_type": metric_type,
                "endpoint": endpoint,
                "metadata": metadata or {},
                "timestamp": datetime.utcnow(),
            }

            # Add to buffer
            self.metrics_buffer.append(metric_data)

            # Flush buffer if full
            if len(self.metrics_buffer) >= self.buffer_size:
                await self._flush_metrics()

            # Update Prometheus metrics
            if metric_type == "response_time" and endpoint:
                metrics.http_request_duration_seconds.labels(
                    method="POST", endpoint=endpoint, status="200"
                ).observe(value / 1000)  # Convert ms to seconds

        except Exception as e:
            logger.error("Failed to record metric", error=str(e), metric_name=metric_name)

    async def analyze_performance(
        self, hours: int = 24
    ) -> PerformanceReport:
        """
        Analyze performance over the specified time period.
        
        Args:
            hours: Number of hours to analyze
            
        Returns:
            Performance report with identified issues
        """
        try:
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(hours=hours)

            # Analyze different aspects
            bottlenecks = await self._identify_bottlenecks(period_start, period_end)
            slow_endpoints = await self._find_slow_endpoints(period_start, period_end)
            memory_trends = await self._analyze_memory_trends(period_start, period_end)
            error_rates = await self._calculate_error_rates(period_start, period_end)
            costs = await self._analyze_costs(period_start, period_end)

            # Calculate overall health score
            health_score = self._calculate_health_score(
                bottlenecks, slow_endpoints, memory_trends, error_rates
            )

            report = PerformanceReport(
                period_start=period_start,
                period_end=period_end,
                bottlenecks=bottlenecks,
                top_slow_endpoints=slow_endpoints[:10],
                memory_trends=memory_trends,
                error_rate_by_endpoint=error_rates,
                cost_by_feature=costs,
                overall_health_score=health_score,
            )

            logger.info(
                "Performance analysis completed",
                health_score=health_score,
                bottlenecks_found=len(bottlenecks),
            )

            return report

        except Exception as e:
            logger.error("Performance analysis failed", error=str(e))
            raise

    async def get_current_memory_usage(self) -> Dict[str, float]:
        """
        Get current system memory usage.
        
        Returns:
            Memory usage statistics in MB
        """
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            virtual_memory = psutil.virtual_memory()

            usage = {
                "process_rss_mb": memory_info.rss / (1024 * 1024),
                "process_vms_mb": memory_info.vms / (1024 * 1024),
                "system_total_mb": virtual_memory.total / (1024 * 1024),
                "system_available_mb": virtual_memory.available / (1024 * 1024),
                "system_used_percent": virtual_memory.percent,
            }

            # Record metric
            await self.record_metric(
                "memory_usage",
                usage["process_rss_mb"],
                "mb",
                "gauge",
                metadata=usage,
            )

            return usage

        except Exception as e:
            logger.error("Failed to get memory usage", error=str(e))
            return {}

    async def detect_memory_leak(
        self, hours: int = 24, threshold_mb: float = 100
    ) -> Optional[Dict]:
        """
        Detect potential memory leaks.
        
        Args:
            hours: Number of hours to analyze
            threshold_mb: Growth threshold in MB
            
        Returns:
            Memory leak detection result or None
        """
        try:
            period_end = datetime.utcnow()
            period_start = period_end - timedelta(hours=hours)

            # Query memory metrics
            query = (
                select(PerformanceMetric)
                .where(
                    and_(
                        PerformanceMetric.metric_name == "memory_usage",
                        PerformanceMetric.period_start >= period_start,
                    )
                )
                .order_by(PerformanceMetric.period_start)
            )
            result = await self.db.execute(query)
            metrics = result.scalars().all()

            if len(metrics) < 2:
                return None

            # Calculate trend
            first_value = metrics[0].value
            last_value = metrics[-1].value
            growth_mb = last_value - first_value
            growth_rate = growth_mb / hours  # MB per hour

            if growth_mb > threshold_mb:
                return {
                    "detected": True,
                    "start_value_mb": first_value,
                    "end_value_mb": last_value,
                    "growth_mb": growth_mb,
                    "growth_rate_mb_per_hour": growth_rate,
                    "estimated_time_to_limit_hours": (
                        (self.MEMORY_WARNING_THRESHOLD_MB - last_value) / growth_rate
                        if growth_rate > 0
                        else float("inf")
                    ),
                }

            return {"detected": False, "growth_mb": growth_mb}

        except Exception as e:
            logger.error("Memory leak detection failed", error=str(e))
            return None

    # Private helper methods

    async def _flush_metrics(self) -> None:
        """Flush buffered metrics to database."""
        try:
            if not self.metrics_buffer:
                return

            # Group by time window (5-minute buckets)
            time_window = timedelta(minutes=5)
            grouped_metrics = defaultdict(list)

            for metric in self.metrics_buffer:
                bucket = metric["timestamp"].replace(
                    minute=(metric["timestamp"].minute // 5) * 5, second=0, microsecond=0
                )
                key = (metric["metric_name"], metric["metric_type"], metric["endpoint"], bucket)
                grouped_metrics[key].append(metric["value"])

            # Create aggregated metrics
            for (name, mtype, endpoint, bucket), values in grouped_metrics.items():
                metric = PerformanceMetric(
                    metric_name=name,
                    metric_type=mtype,
                    endpoint=endpoint,
                    value=sum(values) / len(values),  # Average
                    unit=self.metrics_buffer[0]["unit"],
                    period_start=bucket,
                    period_end=bucket + time_window,
                    sample_count=len(values),
                    min_value=min(values),
                    max_value=max(values),
                    avg_value=sum(values) / len(values),
                    p50_value=sorted(values)[len(values) // 2] if values else 0,
                    p95_value=sorted(values)[int(len(values) * 0.95)] if values else 0,
                    p99_value=sorted(values)[int(len(values) * 0.99)] if values else 0,
                )
                self.db.add(metric)

            await self.db.commit()
            self.metrics_buffer.clear()

        except Exception as e:
            logger.error("Failed to flush metrics", error=str(e))
            await self.db.rollback()

    async def _identify_bottlenecks(
        self, start: datetime, end: datetime
    ) -> List[PerformanceBottleneck]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        # Find slow endpoints
        query = (
            select(
                PerformanceMetric.endpoint,
                func.avg(PerformanceMetric.value).label("avg_time"),
            )
            .where(
                and_(
                    PerformanceMetric.metric_type == "response_time",
                    PerformanceMetric.period_start >= start,
                    PerformanceMetric.period_end <= end,
                    PerformanceMetric.endpoint.isnot(None),
                )
            )
            .group_by(PerformanceMetric.endpoint)
            .having(func.avg(PerformanceMetric.value) > self.RESPONSE_TIME_THRESHOLD_MS)
        )

        result = await self.db.execute(query)
        slow_endpoints = result.all()

        for endpoint, avg_time in slow_endpoints:
            severity = "critical" if avg_time > 500 else "high" if avg_time > 200 else "medium"
            bottlenecks.append(
                PerformanceBottleneck(
                    location=endpoint,
                    issue_type="slow_response",
                    severity=severity,
                    current_value=avg_time,
                    threshold=self.RESPONSE_TIME_THRESHOLD_MS,
                    recommendation=f"Optimize {endpoint} - consider caching, async operations, or database query optimization",
                    estimated_impact=f"{((avg_time - self.RESPONSE_TIME_THRESHOLD_MS) / avg_time * 100):.1f}% faster",
                )
            )

        return bottlenecks

    async def _find_slow_endpoints(
        self, start: datetime, end: datetime
    ) -> List[Tuple[str, float]]:
        """Find slowest endpoints."""
        query = (
            select(
                PerformanceMetric.endpoint,
                func.avg(PerformanceMetric.value).label("avg_time"),
            )
            .where(
                and_(
                    PerformanceMetric.metric_type == "response_time",
                    PerformanceMetric.period_start >= start,
                    PerformanceMetric.endpoint.isnot(None),
                )
            )
            .group_by(PerformanceMetric.endpoint)
            .order_by(func.avg(PerformanceMetric.value).desc())
            .limit(10)
        )

        result = await self.db.execute(query)
        return [(row.endpoint, row.avg_time) for row in result.all()]

    async def _analyze_memory_trends(
        self, start: datetime, end: datetime
    ) -> Dict[str, float]:
        """Analyze memory usage trends."""
        query = (
            select(
                func.avg(PerformanceMetric.value).label("avg"),
                func.max(PerformanceMetric.value).label("max"),
                func.min(PerformanceMetric.value).label("min"),
            )
            .where(
                and_(
                    PerformanceMetric.metric_name == "memory_usage",
                    PerformanceMetric.period_start >= start,
                )
            )
        )

        result = await self.db.execute(query)
        row = result.first()

        if row:
            return {
                "avg_mb": row.avg or 0,
                "max_mb": row.max or 0,
                "min_mb": row.min or 0,
            }
        return {"avg_mb": 0, "max_mb": 0, "min_mb": 0}

    async def _calculate_error_rates(
        self, start: datetime, end: datetime
    ) -> Dict[str, float]:
        """Calculate error rates by endpoint."""
        # This would query from API logs if available
        # For now, returning empty dict as placeholder
        return {}

    async def _analyze_costs(
        self, start: datetime, end: datetime
    ) -> Dict[str, float]:
        """Analyze costs by feature."""
        query = (
            select(
                AIUsageLog.task_type,
                func.sum(AIUsageLog.cost_usd).label("total_cost"),
            )
            .where(
                and_(
                    AIUsageLog.created_at >= start,
                    AIUsageLog.task_type.isnot(None),
                )
            )
            .group_by(AIUsageLog.task_type)
        )

        result = await self.db.execute(query)
        return {row.task_type: row.total_cost for row in result.all()}

    def _calculate_health_score(
        self,
        bottlenecks: List[PerformanceBottleneck],
        slow_endpoints: List[Tuple[str, float]],
        memory_trends: Dict[str, float],
        error_rates: Dict[str, float],
    ) -> float:
        """
        Calculate overall system health score (0-100).
        
        100 = Perfect health
        0 = Critical issues
        """
        score = 100.0

        # Deduct for bottlenecks
        for bn in bottlenecks:
            if bn.severity == "critical":
                score -= 20
            elif bn.severity == "high":
                score -= 10
            elif bn.severity == "medium":
                score -= 5

        # Deduct for high memory usage
        if memory_trends.get("max_mb", 0) > self.MEMORY_WARNING_THRESHOLD_MB:
            score -= 15

        # Deduct for error rates
        avg_error_rate = sum(error_rates.values()) / len(error_rates) if error_rates else 0
        if avg_error_rate > self.ERROR_RATE_THRESHOLD:
            score -= 10

        return max(0.0, min(100.0, score))
