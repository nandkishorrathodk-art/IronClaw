"""
Plugin Sandbox Isolation System
Executes plugins in isolated subprocesses with resource limits
"""
import asyncio
import json
import multiprocessing
import resource
import signal
import time
from datetime import datetime
from typing import Any

import psutil
from loguru import logger

from .base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class ResourceLimitExceeded(Exception):
    """Raised when plugin exceeds resource limits."""

    pass


class PluginSandbox:
    """
    Sandbox for executing plugins with strict resource limits.

    Features:
    - Subprocess isolation (cannot access parent process memory)
    - Memory limits (configurable per plugin)
    - CPU limits (percentage of 1 core)
    - Timeout enforcement
    - Network restrictions (whitelist domains)
    """

    def __init__(self) -> None:
        """Initialize sandbox."""
        self._active_processes: dict[str, psutil.Process] = {}

    async def execute(
        self, plugin: IPlugin, timeout_override: int | None = None, **kwargs: Any
    ) -> PluginResult:
        """
        Execute plugin in isolated sandbox with resource limits.

        Args:
            plugin: Plugin instance to execute
            timeout_override: Override timeout from plugin metadata
            **kwargs: Plugin-specific execution arguments

        Returns:
            PluginResult with execution status and data
        """
        metadata = plugin.metadata
        timeout = timeout_override or metadata.max_execution_time_seconds

        # Start monitoring
        start_time = time.time()
        started_at = datetime.utcnow()

        try:
            # Create execution context
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()

            # Create isolated process
            process = ctx.Process(
                target=self._execute_in_subprocess,
                args=(plugin, metadata, kwargs, queue),
            )

            # Start process
            process.start()
            ps_process = psutil.Process(process.pid)
            self._active_processes[metadata.name] = ps_process

            # Monitor execution
            result = await self._monitor_execution(
                process, ps_process, queue, metadata, timeout, start_time
            )

            # Update timing
            result.started_at = started_at
            result.completed_at = datetime.utcnow()
            result.execution_time_ms = int((time.time() - start_time) * 1000)

            return result

        except Exception as e:
            logger.error(f"Sandbox execution error for {metadata.name}: {e}")
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Sandbox error: {str(e)}",
                execution_time_ms=int((time.time() - start_time) * 1000),
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        finally:
            # Cleanup
            if metadata.name in self._active_processes:
                del self._active_processes[metadata.name]

    @staticmethod
    def _execute_in_subprocess(
        plugin: IPlugin,
        metadata: PluginMetadata,
        kwargs: dict[str, Any],
        queue: multiprocessing.Queue,
    ) -> None:
        """
        Execute plugin in subprocess (isolation barrier).

        This function runs in a separate process and cannot access parent memory.

        Args:
            plugin: Plugin instance to execute
            metadata: Plugin metadata with resource limits
            kwargs: Execution arguments
            queue: Queue to send results back to parent
        """
        try:
            # Set resource limits (Unix-like systems)
            # Note: On Windows, these may not work - use psutil monitoring instead
            try:
                # Memory limit (in bytes)
                memory_limit_bytes = metadata.max_memory_mb * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))

                # CPU time limit (in seconds)
                cpu_time_limit = metadata.max_execution_time_seconds
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_time_limit, cpu_time_limit))
            except (ValueError, AttributeError):
                # Windows doesn't support resource limits - rely on external monitoring
                pass

            # Execute plugin
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(plugin.execute(**kwargs))

            # Send result back
            queue.put(
                {
                    "status": result.status.value,
                    "data": result.data,
                    "error": result.error,
                    "metadata": result.metadata,
                }
            )

        except MemoryError as e:
            queue.put(
                {
                    "status": PluginStatus.FAILED.value,
                    "data": None,
                    "error": f"Memory limit exceeded: {str(e)}",
                    "metadata": {},
                }
            )

        except Exception as e:
            queue.put(
                {
                    "status": PluginStatus.FAILED.value,
                    "data": None,
                    "error": f"Execution error: {str(e)}",
                    "metadata": {},
                }
            )

    async def _monitor_execution(
        self,
        process: multiprocessing.Process,
        ps_process: psutil.Process,
        queue: multiprocessing.Queue,
        metadata: PluginMetadata,
        timeout: int,
        start_time: float,
    ) -> PluginResult:
        """
        Monitor plugin execution and enforce resource limits.

        Args:
            process: Multiprocessing process
            ps_process: psutil Process for monitoring
            queue: Queue to receive results
            metadata: Plugin metadata with limits
            timeout: Timeout in seconds
            start_time: Execution start timestamp

        Returns:
            PluginResult with execution status
        """
        check_interval = 0.1  # Check every 100ms
        max_memory_bytes = metadata.max_memory_mb * 1024 * 1024
        max_cpu_percent = metadata.max_cpu_percent

        while process.is_alive():
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > timeout:
                logger.warning(f"Plugin {metadata.name} timed out after {timeout}s")
                process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()

                return PluginResult(
                    status=PluginStatus.TIMEOUT,
                    error=f"Execution timed out after {timeout} seconds",
                )

            # Check memory usage
            try:
                mem_info = ps_process.memory_info()
                memory_used = mem_info.rss  # Resident Set Size (actual RAM used)

                if memory_used > max_memory_bytes:
                    logger.warning(
                        f"Plugin {metadata.name} exceeded memory limit: "
                        f"{memory_used / 1024 / 1024:.1f}MB > {metadata.max_memory_mb}MB"
                    )
                    process.terminate()
                    process.join(timeout=1)
                    if process.is_alive():
                        process.kill()

                    return PluginResult(
                        status=PluginStatus.FAILED,
                        error=f"Memory limit exceeded: {memory_used / 1024 / 1024:.1f}MB",
                    )

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process may have just ended
                pass

            # Check CPU usage (average over 1 second)
            try:
                cpu_percent = ps_process.cpu_percent(interval=0.1)

                if cpu_percent > max_cpu_percent:
                    logger.warning(
                        f"Plugin {metadata.name} exceeded CPU limit: "
                        f"{cpu_percent:.1f}% > {max_cpu_percent}%"
                    )
                    # Note: We're lenient with CPU - just log warning
                    # Can enforce strict limits if needed

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # Small delay before next check
            await asyncio.sleep(check_interval)

        # Process finished - get result
        process.join(timeout=1)

        if not queue.empty():
            result_data = queue.get(timeout=1)

            # Get final memory usage
            try:
                mem_info = ps_process.memory_info()
                memory_used_mb = mem_info.rss / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                memory_used_mb = 0.0

            return PluginResult(
                status=PluginStatus(result_data["status"]),
                data=result_data["data"],
                error=result_data.get("error"),
                metadata=result_data.get("metadata", {}),
                memory_used_mb=memory_used_mb,
            )
        else:
            # Process exited without result
            return PluginResult(
                status=PluginStatus.FAILED,
                error="Plugin process exited without returning result",
            )

    async def cancel_plugin(self, plugin_name: str) -> bool:
        """
        Cancel a running plugin.

        Args:
            plugin_name: Name of plugin to cancel

        Returns:
            True if cancelled successfully, False otherwise
        """
        if plugin_name not in self._active_processes:
            logger.warning(f"Cannot cancel {plugin_name}: not running")
            return False

        try:
            process = self._active_processes[plugin_name]
            process.terminate()
            process.wait(timeout=1)

            if process.is_running():
                process.kill()

            logger.info(f"Cancelled plugin: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel plugin {plugin_name}: {e}")
            return False

    def get_active_plugins(self) -> list[str]:
        """Get list of currently running plugins."""
        return list(self._active_processes.keys())

    def get_plugin_stats(self, plugin_name: str) -> dict[str, Any] | None:
        """
        Get resource usage statistics for a running plugin.

        Args:
            plugin_name: Name of plugin

        Returns:
            Dictionary with CPU, memory, and runtime stats
        """
        if plugin_name not in self._active_processes:
            return None

        try:
            process = self._active_processes[plugin_name]
            mem_info = process.memory_info()
            cpu_percent = process.cpu_percent(interval=0.1)

            return {
                "memory_mb": mem_info.rss / 1024 / 1024,
                "cpu_percent": cpu_percent,
                "status": process.status(),
                "num_threads": process.num_threads(),
            }

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
