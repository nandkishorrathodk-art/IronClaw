"""
Plugin Base Classes and Interfaces
Defines the contract for all Ironclaw plugins
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class PluginStatus(str, Enum):
    """Plugin execution status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class PluginMetadata:
    """Plugin metadata and configuration."""

    name: str
    version: str
    description: str
    author: str = "Unknown"
    dependencies: list[str] = field(default_factory=list)
    max_execution_time_seconds: int = 30
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    requires_network: bool = False
    allowed_domains: list[str] = field(default_factory=list)
    requires_permissions: list[str] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate metadata after initialization."""
        if not self.name or not self.version:
            raise ValueError("Plugin name and version are required")
        if self.max_execution_time_seconds < 1 or self.max_execution_time_seconds > 300:
            raise ValueError("Execution time must be between 1 and 300 seconds")
        if self.max_memory_mb < 64 or self.max_memory_mb > 2048:
            raise ValueError("Memory limit must be between 64MB and 2GB")
        if self.max_cpu_percent < 10 or self.max_cpu_percent > 100:
            raise ValueError("CPU limit must be between 10% and 100%")


@dataclass
class PluginResult:
    """Result from plugin execution."""

    status: PluginStatus
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0
    memory_used_mb: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == PluginStatus.SUCCESS

    @property
    def is_error(self) -> bool:
        """Check if execution failed."""
        return self.status in (PluginStatus.FAILED, PluginStatus.TIMEOUT)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "memory_used_mb": self.memory_used_mb,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class IPlugin(ABC):
    """
    Base interface for all Ironclaw plugins.

    All plugins must inherit from this class and implement the required methods.
    Plugins are executed in isolated sandboxes with resource limits.
    """

    def __init__(self, metadata: PluginMetadata) -> None:
        """
        Initialize plugin with metadata.

        Args:
            metadata: Plugin metadata and configuration
        """
        self.metadata = metadata
        self._on_load_hooks: list[Callable[[], None]] = []
        self._on_unload_hooks: list[Callable[[], None]] = []
        self._on_error_hooks: list[Callable[[Exception], None]] = []

    @abstractmethod
    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Execute the plugin's main functionality.

        Args:
            **kwargs: Plugin-specific arguments

        Returns:
            PluginResult with execution status and data
        """
        pass

    @abstractmethod
    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate input parameters before execution.

        Args:
            **kwargs: Plugin-specific arguments to validate

        Returns:
            True if validation passes, False otherwise
        """
        pass

    async def cleanup(self) -> None:
        """
        Cleanup resources after execution.
        Override this method to implement custom cleanup logic.
        """
        pass

    async def on_load(self) -> None:
        """
        Hook called when plugin is loaded.
        Override this method to implement initialization logic.
        """
        for hook in self._on_load_hooks:
            hook()

    async def on_unload(self) -> None:
        """
        Hook called when plugin is unloaded.
        Override this method to implement teardown logic.
        """
        for hook in self._on_unload_hooks:
            hook()

    async def on_error(self, error: Exception) -> None:
        """
        Hook called when plugin execution fails.

        Args:
            error: The exception that occurred
        """
        for hook in self._on_error_hooks:
            hook(error)

    def register_on_load(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when plugin loads."""
        self._on_load_hooks.append(callback)

    def register_on_unload(self, callback: Callable[[], None]) -> None:
        """Register a callback to run when plugin unloads."""
        self._on_unload_hooks.append(callback)

    def register_on_error(self, callback: Callable[[Exception], None]) -> None:
        """Register a callback to run when plugin encounters an error."""
        self._on_error_hooks.append(callback)

    def get_info(self) -> dict[str, Any]:
        """Get plugin information as dictionary."""
        return {
            "name": self.metadata.name,
            "version": self.metadata.version,
            "description": self.metadata.description,
            "author": self.metadata.author,
            "dependencies": self.metadata.dependencies,
            "enabled": self.metadata.enabled,
            "tags": self.metadata.tags,
            "requirements": {
                "max_execution_time_seconds": self.metadata.max_execution_time_seconds,
                "max_memory_mb": self.metadata.max_memory_mb,
                "max_cpu_percent": self.metadata.max_cpu_percent,
                "requires_network": self.metadata.requires_network,
                "allowed_domains": self.metadata.allowed_domains,
                "requires_permissions": self.metadata.requires_permissions,
            },
        }
