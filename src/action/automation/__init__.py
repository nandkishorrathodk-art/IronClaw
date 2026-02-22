"""
Automation Module - Workflow, Execution, and Desktop Control

This module provides comprehensive automation capabilities:
- Workflow orchestration with DAG execution
- Docker sandbox for code execution
- Desktop automation (mouse, keyboard, windows)
- Browser automation with Playwright
- Permission system for security
- Rollback capabilities for safety
"""

from .browser import (
    BrowserAutomation,
    BrowserContext,
    BrowserType,
    ExtractionRule,
    FormField,
    NavigationResult,
    WaitCondition,
)
from .desktop import (
    DesktopAutomation,
    KeyModifier,
    MouseButton,
    Point,
    Rectangle,
    Size,
    Window,
    WindowManager,
)
from .executor import (
    DockerSandboxExecutor,
    ExecutionLanguage,
    ExecutionResult,
    ExecutionStatus,
    ResourceLimits,
)
from .permissions import (
    ActionType,
    AuditLog,
    PermissionDecision,
    PermissionManager,
    PermissionRule,
    RiskLevel,
)
from .rollback import (
    RollbackManager,
    RollbackPoint,
    Transaction,
    with_rollback,
)
from .workflow import (
    ConditionOperator,
    TaskCondition,
    TaskStatus,
    Workflow,
    WorkflowBuilder,
    WorkflowEngine,
    WorkflowTask,
    create_workflow_from_dict,
)

__all__ = [
    "BrowserAutomation",
    "BrowserContext",
    "BrowserType",
    "ExtractionRule",
    "FormField",
    "NavigationResult",
    "WaitCondition",
    "DesktopAutomation",
    "KeyModifier",
    "MouseButton",
    "Point",
    "Rectangle",
    "Size",
    "Window",
    "WindowManager",
    "DockerSandboxExecutor",
    "ExecutionLanguage",
    "ExecutionResult",
    "ExecutionStatus",
    "ResourceLimits",
    "ActionType",
    "AuditLog",
    "PermissionDecision",
    "PermissionManager",
    "PermissionRule",
    "RiskLevel",
    "RollbackManager",
    "RollbackPoint",
    "Transaction",
    "with_rollback",
    "ConditionOperator",
    "TaskCondition",
    "TaskStatus",
    "Workflow",
    "WorkflowBuilder",
    "WorkflowEngine",
    "WorkflowTask",
    "create_workflow_from_dict",
]
