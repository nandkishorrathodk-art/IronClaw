"""
Plugin Management REST API Endpoints
"""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from src.plugins.base import PluginResult
from src.plugins.hot_reload import PluginHotReloadManager
from src.plugins.registry import PluginRegistry
from src.plugins.sandbox import PluginSandbox

router = APIRouter(prefix="/plugins", tags=["plugins"])

# Global instances (will be initialized in lifespan)
plugin_registry: PluginRegistry | None = None
plugin_sandbox: PluginSandbox | None = None
hot_reload_manager: PluginHotReloadManager | None = None


# Request/Response Models
class PluginExecuteRequest(BaseModel):
    """Request model for plugin execution."""

    plugin_name: str = Field(..., description="Name of plugin to execute")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Plugin-specific parameters"
    )
    timeout_override: int | None = Field(
        None, description="Override plugin's default timeout (seconds)"
    )
    validate_first: bool = Field(True, description="Validate parameters before execution")


class PluginExecuteResponse(BaseModel):
    """Response model for plugin execution."""

    status: str
    data: Any = None
    error: str | None = None
    execution_time_ms: int
    memory_used_mb: float


class PluginEnableRequest(BaseModel):
    """Request model for enabling/disabling plugin."""

    enabled: bool = Field(..., description="Enable or disable plugin")


class PluginInfoResponse(BaseModel):
    """Response model for plugin information."""

    name: str
    version: str
    description: str
    author: str
    enabled: bool
    dependencies: list[str]
    tags: list[str]
    requirements: Dict[str, Any]


# API Endpoints


@router.get("", response_model=Dict[str, PluginInfoResponse])
async def list_plugins(enabled_only: bool = False) -> Dict[str, PluginInfoResponse]:
    """
    List all registered plugins.

    Args:
        enabled_only: Only return enabled plugins

    Returns:
        Dictionary of plugin name to plugin info
    """
    if plugin_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    plugins_info = plugin_registry.list_plugins(enabled_only=enabled_only)
    return plugins_info


@router.get("/{plugin_name}", response_model=PluginInfoResponse)
async def get_plugin(plugin_name: str) -> PluginInfoResponse:
    """
    Get information about a specific plugin.

    Args:
        plugin_name: Name of plugin

    Returns:
        Plugin information
    """
    if plugin_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    plugin = plugin_registry.get_plugin(plugin_name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    plugin_info = plugin.get_info()
    plugin_info["enabled"] = plugin_registry._enabled.get(plugin_name, False)

    return plugin_info


@router.post("/{plugin_name}/execute", response_model=PluginExecuteResponse)
async def execute_plugin(plugin_name: str, request: PluginExecuteRequest) -> PluginExecuteResponse:
    """
    Execute a plugin with given parameters.

    Args:
        plugin_name: Name of plugin to execute
        request: Execution request with parameters

    Returns:
        Plugin execution result
    """
    if plugin_registry is None or plugin_sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    plugin = plugin_registry.get_plugin(plugin_name)
    if plugin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    # Execute in sandbox
    result = await plugin_sandbox.execute(
        plugin=plugin,
        timeout_override=request.timeout_override,
        **request.parameters,
    )

    return PluginExecuteResponse(
        status=result.status.value,
        data=result.data,
        error=result.error,
        execution_time_ms=result.execution_time_ms,
        memory_used_mb=result.memory_used_mb,
    )


@router.put("/{plugin_name}/enable")
async def enable_plugin(plugin_name: str, request: PluginEnableRequest) -> Dict[str, str]:
    """
    Enable or disable a plugin.

    Args:
        plugin_name: Name of plugin
        request: Enable request

    Returns:
        Success message
    """
    if plugin_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    if request.enabled:
        success = await plugin_registry.enable_plugin(plugin_name)
        action = "enabled"
    else:
        success = await plugin_registry.disable_plugin(plugin_name)
        action = "disabled"

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found: {plugin_name}",
        )

    return {"message": f"Plugin {plugin_name} {action} successfully"}


@router.post("/{plugin_name}/reload")
async def reload_plugin(plugin_name: str) -> Dict[str, str]:
    """
    Hot reload a plugin (unload and load again).

    Args:
        plugin_name: Name of plugin to reload

    Returns:
        Success message
    """
    if hot_reload_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hot reload not enabled",
        )

    success = await hot_reload_manager.manual_reload(plugin_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload plugin: {plugin_name}",
        )

    return {"message": f"Plugin {plugin_name} reloaded successfully"}


@router.post("/reload-all")
async def reload_all_plugins() -> Dict[str, Any]:
    """
    Reload all plugins.

    Returns:
        Dictionary with reload results
    """
    if plugin_registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    plugins = list(plugin_registry._plugins.keys())
    results = {"succeeded": [], "failed": []}

    for plugin_name in plugins:
        success = await plugin_registry.reload_plugin(plugin_name)
        if success:
            results["succeeded"].append(plugin_name)
        else:
            results["failed"].append(plugin_name)

    return {
        "message": "Reload completed",
        "total": len(plugins),
        "succeeded": len(results["succeeded"]),
        "failed": len(results["failed"]),
        "results": results,
    }


@router.get("/{plugin_name}/stats")
async def get_plugin_stats(plugin_name: str) -> Dict[str, Any]:
    """
    Get resource usage statistics for a running plugin.

    Args:
        plugin_name: Name of plugin

    Returns:
        Resource usage statistics
    """
    if plugin_sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    stats = plugin_sandbox.get_plugin_stats(plugin_name)

    if stats is None:
        return {
            "plugin_name": plugin_name,
            "status": "not_running",
        }

    return {
        "plugin_name": plugin_name,
        "status": "running",
        **stats,
    }


@router.post("/{plugin_name}/cancel")
async def cancel_plugin(plugin_name: str) -> Dict[str, str]:
    """
    Cancel a running plugin.

    Args:
        plugin_name: Name of plugin to cancel

    Returns:
        Success message
    """
    if plugin_sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    success = await plugin_sandbox.cancel_plugin(plugin_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not running: {plugin_name}",
        )

    return {"message": f"Plugin {plugin_name} cancelled successfully"}


@router.get("/system/active")
async def get_active_plugins() -> Dict[str, Any]:
    """
    Get list of currently running plugins.

    Returns:
        List of active plugin names
    """
    if plugin_sandbox is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Plugin system not initialized",
        )

    active = plugin_sandbox.get_active_plugins()

    return {
        "active_plugins": active,
        "count": len(active),
    }


@router.get("/system/hot-reload")
async def get_hot_reload_status() -> Dict[str, Any]:
    """
    Get hot reload system status.

    Returns:
        Hot reload status
    """
    if hot_reload_manager is None:
        return {
            "enabled": False,
            "watching": False,
        }

    return {
        "enabled": True,
        "watching": hot_reload_manager.is_watching,
    }


@router.get("/{plugin_name}/backups")
async def get_plugin_backups(plugin_name: str) -> Dict[str, Any]:
    """
    Get list of backups for a plugin.

    Args:
        plugin_name: Name of plugin

    Returns:
        List of backup information
    """
    if hot_reload_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hot reload not enabled",
        )

    backups = hot_reload_manager.get_backup_info(plugin_name)

    return {
        "plugin_name": plugin_name,
        "backups": backups,
        "count": len(backups),
    }
