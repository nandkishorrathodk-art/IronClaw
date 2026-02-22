"""
Prometheus metrics for monitoring Ironclaw performance
"""
from prometheus_client import Counter, Histogram, Gauge, Info
import psutil
import asyncio
from src.config import settings


# HTTP Metrics
http_requests_total = Counter(
    "ironclaw_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"]
)

http_request_duration_seconds = Histogram(
    "ironclaw_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"]
)

http_requests_in_progress = Gauge(
    "ironclaw_http_requests_in_progress",
    "Number of HTTP requests in progress",
    ["method", "endpoint"]
)

# AI Provider Metrics
ai_requests_total = Counter(
    "ironclaw_ai_requests_total",
    "Total AI provider requests",
    ["provider", "model", "task_type"]
)

ai_request_duration_seconds = Histogram(
    "ironclaw_ai_request_duration_seconds",
    "AI request latency",
    ["provider", "model"]
)

ai_tokens_total = Counter(
    "ironclaw_ai_tokens_total",
    "Total tokens processed",
    ["provider", "model", "type"]  # type: prompt, completion
)

ai_cost_usd_total = Counter(
    "ironclaw_ai_cost_usd_total",
    "Total AI cost in USD",
    ["provider", "model"]
)

ai_errors_total = Counter(
    "ironclaw_ai_errors_total",
    "Total AI provider errors",
    ["provider", "error_type"]
)

# Database Metrics
db_queries_total = Counter(
    "ironclaw_db_queries_total",
    "Total database queries",
    ["operation"]  # select, insert, update, delete
)

db_query_duration_seconds = Histogram(
    "ironclaw_db_query_duration_seconds",
    "Database query latency",
    ["operation"]
)

db_connections_active = Gauge(
    "ironclaw_db_connections_active",
    "Number of active database connections"
)

# Cache Metrics
cache_operations_total = Counter(
    "ironclaw_cache_operations_total",
    "Total cache operations",
    ["operation", "result"]  # operation: get/set/delete, result: hit/miss
)

# System Metrics
system_memory_bytes = Gauge(
    "ironclaw_system_memory_bytes",
    "System memory usage in bytes",
    ["type"]  # type: used, available, total
)

system_cpu_percent = Gauge(
    "ironclaw_system_cpu_percent",
    "CPU usage percentage"
)

# Application Info
app_info = Info(
    "ironclaw_app",
    "Ironclaw application information"
)

# Set application info
app_info.info({
    "version": "0.1.0",
    "environment": settings.environment,
    "python_version": "3.11+",
})


async def update_system_metrics():
    """Background task to update system metrics."""
    while True:
        try:
            # Memory metrics
            memory = psutil.virtual_memory()
            system_memory_bytes.labels(type="used").set(memory.used)
            system_memory_bytes.labels(type="available").set(memory.available)
            system_memory_bytes.labels(type="total").set(memory.total)
            
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            system_cpu_percent.set(cpu_percent)
            
            # Warning if memory usage is high
            if memory.used > settings.memory_warning_threshold_mb * 1024 * 1024:
                from src.utils.logging import get_logger
                logger = get_logger(__name__)
                logger.warning(
                    f"High memory usage: {memory.used / 1024 / 1024:.0f}MB / "
                    f"{settings.max_memory_mb}MB limit"
                )
            
            await asyncio.sleep(10)  # Update every 10 seconds
            
        except Exception as e:
            from src.utils.logging import get_logger
            logger = get_logger(__name__)
            logger.error(f"Error updating system metrics: {e}")
            await asyncio.sleep(10)


def get_current_memory_usage_mb() -> float:
    """Get current memory usage in MB."""
    return psutil.Process().memory_info().rss / 1024 / 1024


# Plugin Metrics
plugin_executions_total = Counter(
    "ironclaw_plugin_executions_total",
    "Total plugin executions",
    ["plugin_name", "status"]
)

plugin_execution_duration_seconds = Histogram(
    "ironclaw_plugin_execution_duration_seconds",
    "Plugin execution latency",
    ["plugin_name"]
)

# Workflow Metrics
workflow_executions_total = Counter(
    "ironclaw_workflow_executions_total",
    "Total workflow executions",
    ["workflow_name", "status"]
)

workflow_execution_duration_seconds = Histogram(
    "ironclaw_workflow_execution_duration_seconds",
    "Workflow execution latency",
    ["workflow_name"]
)

workflow_steps_total = Counter(
    "ironclaw_workflow_steps_total",
    "Total workflow steps executed",
    ["workflow_name", "step_name", "status"]
)

# Voice Metrics
voice_transcriptions_total = Counter(
    "ironclaw_voice_transcriptions_total",
    "Total voice transcriptions",
    ["engine", "language"]
)

voice_transcription_duration_seconds = Histogram(
    "ironclaw_voice_transcription_duration_seconds",
    "Voice transcription latency",
    ["engine"]
)

voice_syntheses_total = Counter(
    "ironclaw_voice_syntheses_total",
    "Total voice syntheses",
    ["engine", "language", "voice"]
)

# Security Metrics
security_scans_total = Counter(
    "ironclaw_security_scans_total",
    "Total security scans",
    ["scan_type", "status"]
)

security_vulnerabilities_found = Counter(
    "ironclaw_security_vulnerabilities_found",
    "Total vulnerabilities found",
    ["severity", "vulnerability_type"]
)

security_scan_duration_seconds = Histogram(
    "ironclaw_security_scan_duration_seconds",
    "Security scan latency",
    ["scan_type"]
)
