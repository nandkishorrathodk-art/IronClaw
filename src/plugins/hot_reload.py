"""
Plugin Hot Reload System
Watches plugin files and reloads them automatically on changes
"""
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .registry import PluginRegistry


class PluginBackup:
    """Manages plugin backups for rollback functionality."""

    def __init__(self, backup_dir: str = "data/plugin_backups") -> None:
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory to store backups
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, plugin_path: Path) -> Path:
        """
        Create a backup of plugin file.

        Args:
            plugin_path: Path to plugin file

        Returns:
            Path to backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        plugin_name = plugin_path.parent.name
        backup_name = f"{plugin_name}_{timestamp}.py"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(plugin_path, backup_path)
        logger.info(f"Created backup for {plugin_name}: {backup_path}")

        return backup_path

    def restore_backup(self, plugin_name: str, backup_path: Path) -> bool:
        """
        Restore plugin from backup.

        Args:
            plugin_name: Name of plugin to restore
            backup_path: Path to backup file

        Returns:
            True if restored successfully, False otherwise
        """
        if not backup_path.exists():
            logger.error(f"Backup file not found: {backup_path}")
            return False

        try:
            plugin_path = Path("plugins") / plugin_name / "plugin.py"
            shutil.copy2(backup_path, plugin_path)
            logger.info(f"Restored {plugin_name} from backup: {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to restore backup for {plugin_name}: {e}")
            return False

    def list_backups(self, plugin_name: str) -> list[Path]:
        """
        List all backups for a plugin.

        Args:
            plugin_name: Name of plugin

        Returns:
            List of backup file paths
        """
        return sorted(
            self.backup_dir.glob(f"{plugin_name}_*.py"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def cleanup_old_backups(self, plugin_name: str, keep_last: int = 5) -> int:
        """
        Clean up old backups, keeping only the most recent.

        Args:
            plugin_name: Name of plugin
            keep_last: Number of backups to keep

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups(plugin_name)
        to_delete = backups[keep_last:]

        deleted = 0
        for backup_path in to_delete:
            try:
                backup_path.unlink()
                deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete backup {backup_path}: {e}")

        if deleted > 0:
            logger.info(f"Deleted {deleted} old backups for {plugin_name}")

        return deleted


class PluginFileWatcher(FileSystemEventHandler):
    """Watches plugin files for changes and triggers reloads."""

    def __init__(
        self,
        registry: PluginRegistry,
        backup_manager: PluginBackup,
        on_reload_success: Optional[Callable[[str], None]] = None,
        on_reload_failure: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Initialize file watcher.

        Args:
            registry: Plugin registry to reload plugins
            backup_manager: Backup manager for rollback
            on_reload_success: Callback on successful reload
            on_reload_failure: Callback on failed reload
        """
        self.registry = registry
        self.backup_manager = backup_manager
        self.on_reload_success = on_reload_success
        self.on_reload_failure = on_reload_failure
        self._reload_tasks: dict[str, asyncio.Task] = {}

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Handle file modification events.

        Args:
            event: File system event
        """
        if event.is_directory or not event.src_path.endswith("plugin.py"):
            return

        plugin_path = Path(event.src_path)
        plugin_name = plugin_path.parent.name

        logger.info(f"Detected change in plugin: {plugin_name}")

        # Cancel any pending reload task
        if plugin_name in self._reload_tasks and not self._reload_tasks[plugin_name].done():
            self._reload_tasks[plugin_name].cancel()

        # Schedule new reload (debounced by 1 second)
        loop = asyncio.get_event_loop()
        self._reload_tasks[plugin_name] = loop.create_task(
            self._reload_plugin_delayed(plugin_name, plugin_path)
        )

    async def _reload_plugin_delayed(self, plugin_name: str, plugin_path: Path) -> None:
        """
        Reload plugin after a delay (debouncing).

        Args:
            plugin_name: Name of plugin to reload
            plugin_path: Path to plugin file
        """
        # Wait 1 second to debounce rapid changes
        await asyncio.sleep(1.0)

        # Create backup before reload
        backup_path = self.backup_manager.create_backup(plugin_path)

        # Attempt reload
        success = await self.registry.reload_plugin(plugin_name)

        if success:
            logger.info(f"Successfully hot reloaded plugin: {plugin_name}")
            if self.on_reload_success:
                self.on_reload_success(plugin_name)

            # Cleanup old backups
            self.backup_manager.cleanup_old_backups(plugin_name, keep_last=5)

        else:
            logger.error(f"Failed to reload plugin: {plugin_name}, rolling back...")

            # Rollback to backup
            if self.backup_manager.restore_backup(plugin_name, backup_path):
                # Try reloading the old version
                rollback_success = await self.registry.reload_plugin(plugin_name)

                if rollback_success:
                    logger.info(f"Successfully rolled back {plugin_name}")
                else:
                    logger.error(f"Rollback failed for {plugin_name}")

            if self.on_reload_failure:
                self.on_reload_failure(plugin_name, "Reload failed, rolled back to previous version")


class PluginHotReloadManager:
    """
    Manages hot reloading of plugins with file watching and rollback.

    Features:
    - Automatic file watching
    - Debounced reloads (waits 1s after last change)
    - Automatic backups before reload
    - Rollback on failure
    - Configurable callbacks
    """

    def __init__(
        self,
        registry: PluginRegistry,
        plugins_dir: str = "plugins",
        backup_dir: str = "data/plugin_backups",
    ) -> None:
        """
        Initialize hot reload manager.

        Args:
            registry: Plugin registry
            plugins_dir: Directory to watch for plugin changes
            backup_dir: Directory to store backups
        """
        self.registry = registry
        self.plugins_dir = Path(plugins_dir)
        self.backup_manager = PluginBackup(backup_dir)
        self.observer: Optional[Observer] = None
        self._event_handler: Optional[PluginFileWatcher] = None
        self._is_watching = False

    def start_watching(
        self,
        on_reload_success: Optional[Callable[[str], None]] = None,
        on_reload_failure: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        """
        Start watching plugin files for changes.

        Args:
            on_reload_success: Callback called on successful reload (plugin_name)
            on_reload_failure: Callback called on failed reload (plugin_name, error)
        """
        if self._is_watching:
            logger.warning("Hot reload watcher already running")
            return

        if not self.plugins_dir.exists():
            logger.warning(f"Plugins directory does not exist: {self.plugins_dir}")
            self.plugins_dir.mkdir(parents=True, exist_ok=True)

        # Create event handler
        self._event_handler = PluginFileWatcher(
            registry=self.registry,
            backup_manager=self.backup_manager,
            on_reload_success=on_reload_success,
            on_reload_failure=on_reload_failure,
        )

        # Create observer
        self.observer = Observer()
        self.observer.schedule(self._event_handler, str(self.plugins_dir), recursive=True)
        self.observer.start()

        self._is_watching = True
        logger.info(f"Started watching plugins directory: {self.plugins_dir}")

    def stop_watching(self) -> None:
        """Stop watching plugin files."""
        if not self._is_watching or self.observer is None:
            logger.warning("Hot reload watcher not running")
            return

        self.observer.stop()
        self.observer.join(timeout=5)

        self._is_watching = False
        logger.info("Stopped watching plugins directory")

    async def manual_reload(self, plugin_name: str) -> bool:
        """
        Manually trigger a plugin reload.

        Args:
            plugin_name: Name of plugin to reload

        Returns:
            True if reload successful, False otherwise
        """
        plugin_path = self.plugins_dir / plugin_name / "plugin.py"

        if not plugin_path.exists():
            logger.error(f"Plugin file not found: {plugin_path}")
            return False

        # Create backup
        backup_path = self.backup_manager.create_backup(plugin_path)

        # Attempt reload
        success = await self.registry.reload_plugin(plugin_name)

        if not success:
            logger.error(f"Manual reload failed for {plugin_name}, rolling back...")
            self.backup_manager.restore_backup(plugin_name, backup_path)
            await self.registry.reload_plugin(plugin_name)

        return success

    @property
    def is_watching(self) -> bool:
        """Check if file watcher is active."""
        return self._is_watching

    def get_backup_info(self, plugin_name: str) -> list[dict[str, str]]:
        """
        Get backup information for a plugin.

        Args:
            plugin_name: Name of plugin

        Returns:
            List of dictionaries with backup info
        """
        backups = self.backup_manager.list_backups(plugin_name)

        return [
            {
                "path": str(backup),
                "timestamp": datetime.fromtimestamp(backup.stat().st_mtime).isoformat(),
                "size_bytes": backup.stat().st_size,
            }
            for backup in backups
        ]
