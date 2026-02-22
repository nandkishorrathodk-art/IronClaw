"""
Plugin Registry and Discovery System
Manages plugin lifecycle, dependencies, and versions
"""
import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from .base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class PluginRegistry:
    """
    Plugin registry for discovery, loading, and management.

    Features:
    - Auto-discovery of plugins in plugins directory
    - Version compatibility checking
    - Dependency resolution
    - Enable/disable plugins dynamically
    """

    def __init__(self, plugins_dir: str = "plugins") -> None:
        """
        Initialize plugin registry.

        Args:
            plugins_dir: Directory to search for plugins
        """
        self.plugins_dir = Path(plugins_dir)
        self._plugins: dict[str, IPlugin] = {}
        self._metadata: dict[str, PluginMetadata] = {}
        self._enabled: dict[str, bool] = {}

    async def discover_plugins(self) -> list[str]:
        """
        Auto-discover all plugins in the plugins directory.

        Returns:
            List of discovered plugin names
        """
        discovered = []

        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            return discovered

        for plugin_path in self.plugins_dir.glob("*/plugin.py"):
            try:
                plugin_name = plugin_path.parent.name
                await self._load_plugin_from_file(plugin_name, plugin_path)
                discovered.append(plugin_name)
                logger.info(f"Discovered plugin: {plugin_name}")
            except Exception as e:
                logger.error(f"Failed to discover plugin {plugin_path}: {e}")

        return discovered

    async def _load_plugin_from_file(self, name: str, path: Path) -> None:
        """
        Load a plugin from a file path.

        Args:
            name: Plugin name
            path: Path to plugin.py file
        """
        spec = importlib.util.spec_from_file_location(f"plugins.{name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin from {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"plugins.{name}"] = module
        spec.loader.exec_module(module)

        # Find plugin class (must inherit from IPlugin)
        plugin_class = None
        for item_name, item in inspect.getmembers(module, inspect.isclass):
            if issubclass(item, IPlugin) and item != IPlugin:
                plugin_class = item
                break

        if plugin_class is None:
            raise ValueError(f"No plugin class found in {path}")

        # Instantiate plugin
        plugin_instance = plugin_class()
        self._plugins[name] = plugin_instance
        self._metadata[name] = plugin_instance.metadata
        self._enabled[name] = plugin_instance.metadata.enabled

        # Call on_load hook
        await plugin_instance.on_load()

    async def register_plugin(self, plugin: IPlugin) -> None:
        """
        Manually register a plugin instance.

        Args:
            plugin: Plugin instance to register
        """
        name = plugin.metadata.name

        # Check if plugin already exists
        if name in self._plugins:
            logger.warning(f"Plugin {name} already registered, unloading old version")
            await self.unload_plugin(name)

        # Validate dependencies
        if not await self._check_dependencies(plugin):
            raise ValueError(f"Plugin {name} has unmet dependencies")

        # Register plugin
        self._plugins[name] = plugin
        self._metadata[name] = plugin.metadata
        self._enabled[name] = plugin.metadata.enabled

        # Call on_load hook
        await plugin.on_load()

        logger.info(f"Registered plugin: {name} v{plugin.metadata.version}")

    async def unload_plugin(self, name: str) -> None:
        """
        Unload a plugin and clean up resources.

        Args:
            name: Plugin name to unload
        """
        if name not in self._plugins:
            logger.warning(f"Plugin {name} not found in registry")
            return

        plugin = self._plugins[name]

        # Call on_unload hook
        await plugin.on_unload()

        # Cleanup
        await plugin.cleanup()

        # Remove from registry
        del self._plugins[name]
        del self._metadata[name]
        del self._enabled[name]

        logger.info(f"Unloaded plugin: {name}")

    async def reload_plugin(self, name: str) -> bool:
        """
        Reload a plugin (unload then load).

        Args:
            name: Plugin name to reload

        Returns:
            True if reload successful, False otherwise
        """
        if name not in self._plugins:
            logger.error(f"Cannot reload plugin {name}: not found")
            return False

        try:
            # Get plugin path
            plugin_path = self.plugins_dir / name / "plugin.py"
            if not plugin_path.exists():
                logger.error(f"Plugin file not found: {plugin_path}")
                return False

            # Unload current version
            await self.unload_plugin(name)

            # Reload module
            if f"plugins.{name}" in sys.modules:
                del sys.modules[f"plugins.{name}"]

            # Load new version
            await self._load_plugin_from_file(name, plugin_path)

            logger.info(f"Reloaded plugin: {name}")
            return True

        except Exception as e:
            logger.error(f"Failed to reload plugin {name}: {e}")
            return False

    async def execute_plugin(
        self, name: str, validate_first: bool = True, **kwargs: Any
    ) -> PluginResult:
        """
        Execute a plugin with given arguments.

        Args:
            name: Plugin name to execute
            validate_first: Validate inputs before execution
            **kwargs: Plugin-specific arguments

        Returns:
            PluginResult with execution status and data
        """
        if name not in self._plugins:
            return PluginResult(
                status=PluginStatus.FAILED, error=f"Plugin {name} not found in registry"
            )

        if not self._enabled.get(name, False):
            return PluginResult(status=PluginStatus.FAILED, error=f"Plugin {name} is disabled")

        plugin = self._plugins[name]

        # Validate inputs
        if validate_first:
            try:
                is_valid = await plugin.validate(**kwargs)
                if not is_valid:
                    return PluginResult(
                        status=PluginStatus.FAILED, error="Validation failed for plugin inputs"
                    )
            except Exception as e:
                logger.error(f"Validation error for plugin {name}: {e}")
                return PluginResult(
                    status=PluginStatus.FAILED, error=f"Validation error: {str(e)}"
                )

        # Execute plugin
        try:
            result = await plugin.execute(**kwargs)
            return result
        except Exception as e:
            logger.error(f"Execution error for plugin {name}: {e}")
            await plugin.on_error(e)
            return PluginResult(status=PluginStatus.FAILED, error=f"Execution error: {str(e)}")

    def get_plugin(self, name: str) -> Optional[IPlugin]:
        """Get plugin instance by name."""
        return self._plugins.get(name)

    def get_metadata(self, name: str) -> Optional[PluginMetadata]:
        """Get plugin metadata by name."""
        return self._metadata.get(name)

    def list_plugins(self, enabled_only: bool = False) -> dict[str, dict[str, Any]]:
        """
        List all registered plugins.

        Args:
            enabled_only: Only include enabled plugins

        Returns:
            Dictionary of plugin name to plugin info
        """
        plugins_info = {}

        for name, plugin in self._plugins.items():
            if enabled_only and not self._enabled.get(name, False):
                continue

            plugins_info[name] = {
                **plugin.get_info(),
                "enabled": self._enabled.get(name, False),
            }

        return plugins_info

    async def enable_plugin(self, name: str) -> bool:
        """
        Enable a plugin.

        Args:
            name: Plugin name to enable

        Returns:
            True if successful, False otherwise
        """
        if name not in self._plugins:
            logger.error(f"Cannot enable plugin {name}: not found")
            return False

        self._enabled[name] = True
        logger.info(f"Enabled plugin: {name}")
        return True

    async def disable_plugin(self, name: str) -> bool:
        """
        Disable a plugin.

        Args:
            name: Plugin name to disable

        Returns:
            True if successful, False otherwise
        """
        if name not in self._plugins:
            logger.error(f"Cannot disable plugin {name}: not found")
            return False

        self._enabled[name] = False
        logger.info(f"Disabled plugin: {name}")
        return True

    async def _check_dependencies(self, plugin: IPlugin) -> bool:
        """
        Check if plugin dependencies are met.

        Args:
            plugin: Plugin to check dependencies for

        Returns:
            True if all dependencies are met, False otherwise
        """
        for dependency in plugin.metadata.dependencies:
            if dependency not in self._plugins:
                logger.error(f"Unmet dependency for {plugin.metadata.name}: {dependency}")
                return False

            if not self._enabled.get(dependency, False):
                logger.error(
                    f"Dependency {dependency} is disabled for plugin {plugin.metadata.name}"
                )
                return False

        return True

    def check_version_compatibility(
        self, plugin_name: str, required_version: str
    ) -> bool:
        """
        Check if plugin version is compatible with required version.

        Args:
            plugin_name: Name of plugin to check
            required_version: Required version string (e.g., ">=1.0.0")

        Returns:
            True if compatible, False otherwise
        """
        if plugin_name not in self._metadata:
            return False

        plugin_version = self._metadata[plugin_name].version

        # Simple version comparison (can be enhanced with packaging.version)
        if required_version.startswith(">="):
            required = required_version[2:].strip()
            return plugin_version >= required
        elif required_version.startswith(">"):
            required = required_version[1:].strip()
            return plugin_version > required
        elif required_version.startswith("<="):
            required = required_version[2:].strip()
            return plugin_version <= required
        elif required_version.startswith("<"):
            required = required_version[1:].strip()
            return plugin_version < required
        elif required_version.startswith("=="):
            required = required_version[2:].strip()
            return plugin_version == required
        else:
            return plugin_version == required_version

    async def cleanup_all(self) -> None:
        """Cleanup all plugins and unload them."""
        plugin_names = list(self._plugins.keys())
        for name in plugin_names:
            await self.unload_plugin(name)

        logger.info("Cleaned up all plugins")
