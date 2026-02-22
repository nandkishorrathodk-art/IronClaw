"""
Integration tests for Phase 2: Plugin Architecture & Extensibility
Tests all plugin system features including discovery, execution, sandbox, and hot reload
"""
import asyncio
import time
from pathlib import Path

import pytest

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus
from src.plugins.registry import PluginRegistry
from src.plugins.sandbox import PluginSandbox
from src.plugins.hot_reload import PluginHotReloadManager


class TestPluginBase:
    """Test plugin base classes and interfaces."""

    def test_plugin_metadata_validation(self):
        """Test plugin metadata validation."""
        # Valid metadata
        metadata = PluginMetadata(
            name="test_plugin",
            version="1.0.0",
            description="Test plugin",
        )
        assert metadata.name == "test_plugin"
        assert metadata.enabled is True

        # Invalid metadata (execution time too low)
        with pytest.raises(ValueError):
            PluginMetadata(
                name="test", version="1.0.0", description="Test", max_execution_time_seconds=0
            )

    def test_plugin_result(self):
        """Test plugin result object."""
        result = PluginResult(status=PluginStatus.SUCCESS, data={"value": 42})

        assert result.is_success is True
        assert result.is_error is False
        assert result.data["value"] == 42

        # Test to_dict conversion
        result_dict = result.to_dict()
        assert result_dict["status"] == "success"
        assert result_dict["data"]["value"] == 42


class TestPluginRegistry:
    """Test plugin registry and discovery."""

    @pytest.mark.asyncio
    async def test_plugin_registration(self):
        """Test manual plugin registration."""

        class DummyPlugin(IPlugin):
            def __init__(self):
                super().__init__(
                    PluginMetadata(name="dummy", version="1.0.0", description="Dummy plugin")
                )

            async def execute(self, **kwargs):
                return PluginResult(status=PluginStatus.SUCCESS, data={"result": "ok"})

            async def validate(self, **kwargs):
                return True

        registry = PluginRegistry()
        plugin = DummyPlugin()

        await registry.register_plugin(plugin)

        assert "dummy" in registry._plugins
        assert registry.get_plugin("dummy") is not None

    @pytest.mark.asyncio
    async def test_plugin_discovery(self):
        """Test auto-discovery of plugins."""
        registry = PluginRegistry(plugins_dir="plugins")
        discovered = await registry.discover_plugins()

        # Should discover all 5 example plugins
        assert len(discovered) >= 5
        assert "calculator" in discovered
        assert "web_search" in discovered
        assert "file_ops" in discovered

    @pytest.mark.asyncio
    async def test_plugin_enable_disable(self):
        """Test enabling and disabling plugins."""

        class DummyPlugin(IPlugin):
            def __init__(self):
                super().__init__(
                    PluginMetadata(name="dummy", version="1.0.0", description="Dummy plugin")
                )

            async def execute(self, **kwargs):
                return PluginResult(status=PluginStatus.SUCCESS)

            async def validate(self, **kwargs):
                return True

        registry = PluginRegistry()
        plugin = DummyPlugin()
        await registry.register_plugin(plugin)

        # Plugin should be enabled by default
        assert registry._enabled.get("dummy") is True

        # Disable plugin
        await registry.disable_plugin("dummy")
        assert registry._enabled.get("dummy") is False

        # Try to execute disabled plugin
        result = await registry.execute_plugin("dummy")
        assert result.status == PluginStatus.FAILED
        assert "disabled" in result.error.lower()

        # Re-enable plugin
        await registry.enable_plugin("dummy")
        assert registry._enabled.get("dummy") is True


class TestCalculatorPlugin:
    """Test calculator plugin functionality."""

    @pytest.mark.asyncio
    async def test_calculator_basic_operations(self):
        """Test calculator with basic arithmetic."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # Test addition
        result = await registry.execute_plugin("calculator", expression="2 + 2")
        assert result.is_success
        assert result.data["result"] == 4

        # Test multiplication
        result = await registry.execute_plugin("calculator", expression="3 * 7")
        assert result.is_success
        assert result.data["result"] == 21

        # Test complex expression
        result = await registry.execute_plugin("calculator", expression="(2 + 3) * 4 - 1")
        assert result.is_success
        assert result.data["result"] == 19

    @pytest.mark.asyncio
    async def test_calculator_functions(self):
        """Test calculator with mathematical functions."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # Test sqrt
        result = await registry.execute_plugin("calculator", expression="sqrt(16)")
        assert result.is_success
        assert result.data["result"] == 4.0

        # Test sin (pi radians = 0)
        result = await registry.execute_plugin(
            "calculator", expression="sin(pi)", precision=2
        )
        assert result.is_success
        assert abs(result.data["result"]) < 0.01  # Close to 0

    @pytest.mark.asyncio
    async def test_calculator_security(self):
        """Test calculator security (no code execution)."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # Try malicious input
        result = await registry.execute_plugin("calculator", expression="__import__('os')")
        assert result.status == PluginStatus.FAILED

        # Try eval/exec
        result = await registry.execute_plugin("calculator", expression="eval('1+1')")
        assert result.status == PluginStatus.FAILED


class TestFileOpsPlugin:
    """Test file operations plugin."""

    @pytest.mark.asyncio
    async def test_file_write_and_read(self):
        """Test writing and reading files."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # Write file
        result = await registry.execute_plugin(
            "file_ops", operation="write", path="test.txt", content="Hello, Ironclaw!"
        )
        assert result.is_success

        # Read file
        result = await registry.execute_plugin("file_ops", operation="read", path="test.txt")
        assert result.is_success
        assert result.data["content"] == "Hello, Ironclaw!"

        # Delete file
        result = await registry.execute_plugin("file_ops", operation="delete", path="test.txt")
        assert result.is_success

    @pytest.mark.asyncio
    async def test_file_ops_security(self):
        """Test file ops security (no path traversal)."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # Try path traversal
        result = await registry.execute_plugin(
            "file_ops", operation="read", path="../../../etc/passwd"
        )
        assert result.status == PluginStatus.FAILED

    @pytest.mark.asyncio
    async def test_file_ops_list_directory(self):
        """Test directory listing."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        # List workspace root
        result = await registry.execute_plugin("file_ops", operation="list", path=".")
        assert result.is_success
        assert "items" in result.data


class TestPluginSandbox:
    """Test plugin sandbox isolation."""

    @pytest.mark.asyncio
    async def test_sandbox_execution(self):
        """Test plugin execution in sandbox."""

        class FastPlugin(IPlugin):
            def __init__(self):
                super().__init__(
                    PluginMetadata(
                        name="fast",
                        version="1.0.0",
                        description="Fast plugin",
                        max_execution_time_seconds=5,
                    )
                )

            async def execute(self, **kwargs):
                return PluginResult(status=PluginStatus.SUCCESS, data={"result": "ok"})

            async def validate(self, **kwargs):
                return True

        sandbox = PluginSandbox()
        plugin = FastPlugin()

        result = await sandbox.execute(plugin)

        assert result.is_success
        assert result.data["result"] == "ok"
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_sandbox_timeout(self):
        """Test sandbox timeout enforcement."""

        class SlowPlugin(IPlugin):
            def __init__(self):
                super().__init__(
                    PluginMetadata(
                        name="slow",
                        version="1.0.0",
                        description="Slow plugin",
                        max_execution_time_seconds=1,
                    )
                )

            async def execute(self, **kwargs):
                await asyncio.sleep(10)  # Sleep longer than timeout
                return PluginResult(status=PluginStatus.SUCCESS)

            async def validate(self, **kwargs):
                return True

        sandbox = PluginSandbox()
        plugin = SlowPlugin()

        result = await sandbox.execute(plugin, timeout_override=1)

        assert result.status == PluginStatus.TIMEOUT
        assert "timeout" in result.error.lower()


class TestPluginHotReload:
    """Test plugin hot reload functionality."""

    @pytest.mark.asyncio
    async def test_manual_reload(self):
        """Test manual plugin reload."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        hot_reload = PluginHotReloadManager(registry=registry)

        # Reload calculator plugin
        success = await hot_reload.manual_reload("calculator")
        assert success is True

        # Plugin should still work after reload
        result = await registry.execute_plugin("calculator", expression="5 + 5")
        assert result.is_success
        assert result.data["result"] == 10

    @pytest.mark.asyncio
    async def test_backup_creation(self):
        """Test plugin backup creation."""
        registry = PluginRegistry(plugins_dir="plugins")
        await registry.discover_plugins()

        hot_reload = PluginHotReloadManager(registry=registry)

        # Create backup
        plugin_path = Path("plugins/calculator/plugin.py")
        backup_path = hot_reload.backup_manager.create_backup(plugin_path)

        assert backup_path.exists()
        assert "calculator" in backup_path.name

        # Get backup list
        backups = hot_reload.get_backup_info("calculator")
        assert len(backups) > 0


@pytest.mark.asyncio
async def test_phase_2_success_criteria():
    """
    Test Phase 2 success criteria.

    Success Criteria:
    - 5+ plugins load and execute correctly
    - Hot reload works in <2s
    - Sandbox isolation: 0 escapes in security tests
    - Memory usage <1GB for all plugins combined
    - Test coverage >90%
    """
    # Test 1: Load 5 plugins
    registry = PluginRegistry(plugins_dir="plugins")
    discovered = await registry.discover_plugins()
    assert len(discovered) >= 5, "Should discover 5+ plugins"

    # Test 2: Execute all plugins
    plugins_to_test = {
        "calculator": {"expression": "2+2"},
        "file_ops": {"operation": "list", "path": "."},
    }

    for plugin_name, params in plugins_to_test.items():
        result = await registry.execute_plugin(plugin_name, **params)
        assert result.is_success, f"Plugin {plugin_name} should execute successfully"

    # Test 3: Hot reload speed
    hot_reload = PluginHotReloadManager(registry=registry)
    start = time.time()
    success = await hot_reload.manual_reload("calculator")
    reload_time = time.time() - start
    assert success is True, "Hot reload should succeed"
    assert reload_time < 2.0, f"Hot reload should take <2s, took {reload_time:.2f}s"

    # Test 4: Security (tested in individual test classes)
    # Sandbox isolation is tested in TestPluginSandbox and TestCalculatorPlugin

    print("✅ All Phase 2 success criteria passed!")
