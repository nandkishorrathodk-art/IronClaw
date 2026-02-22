"""
File Operations Plugin
Safe file read/write/search operations within user workspace
"""
import os
import time
from pathlib import Path
from typing import Any

import aiofiles

from src.plugins.base import IPlugin, PluginMetadata, PluginResult, PluginStatus


class FileOpsPlugin(IPlugin):
    """
    Safe file operations plugin.

    Features:
    - Read/write files (text only)
    - List directory contents
    - Search for files by name
    - Safety: Only operates within configured workspace
    - Protection against path traversal attacks
    """

    def __init__(self) -> None:
        """Initialize file operations plugin."""
        metadata = PluginMetadata(
            name="file_ops",
            version="1.0.0",
            description="Safe file read/write/search operations",
            author="Ironclaw Team",
            dependencies=[],
            max_execution_time_seconds=15,
            max_memory_mb=256,
            max_cpu_percent=30.0,
            requires_network=False,
            requires_permissions=["filesystem.read", "filesystem.write"],
            enabled=True,
            tags=["file", "filesystem", "utility"],
        )
        super().__init__(metadata)

        # Workspace directory (all operations restricted to this)
        self.workspace = Path("data/workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Maximum file size (10MB)
        self.max_file_size_bytes = 10 * 1024 * 1024

    async def execute(self, **kwargs: Any) -> PluginResult:
        """
        Execute file operation.

        Operations:
        - read: Read file contents
        - write: Write file contents
        - list: List directory contents
        - search: Search for files by name pattern
        - delete: Delete a file

        Args:
            operation: Operation to perform (required)
            path: Relative path within workspace (required for most ops)
            content: File content (required for write operation)
            pattern: Search pattern (required for search operation)
            recursive: Recursive search (default: False)

        Returns:
            PluginResult with operation result
        """
        start_time = time.time()

        try:
            operation = kwargs.get("operation", "").lower()

            if operation == "read":
                result = await self._read_file(kwargs)
            elif operation == "write":
                result = await self._write_file(kwargs)
            elif operation == "list":
                result = await self._list_directory(kwargs)
            elif operation == "search":
                result = await self._search_files(kwargs)
            elif operation == "delete":
                result = await self._delete_file(kwargs)
            else:
                return PluginResult(
                    status=PluginStatus.FAILED,
                    error=f"Unsupported operation: {operation}. "
                    f"Supported: read, write, list, search, delete",
                )

            execution_time_ms = int((time.time() - start_time) * 1000)
            result.execution_time_ms = execution_time_ms

            return result

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"File operation failed: {str(e)}",
                execution_time_ms=execution_time_ms,
            )

    async def validate(self, **kwargs: Any) -> bool:
        """
        Validate file operation parameters.

        Args:
            operation: Operation name
            path: File path (if applicable)

        Returns:
            True if valid, False otherwise
        """
        operation = kwargs.get("operation", "").lower()

        if operation not in ("read", "write", "list", "search", "delete"):
            return False

        # Validate path for operations that need it
        if operation in ("read", "write", "delete"):
            path = kwargs.get("path", "").strip()
            if not path:
                return False

            # Check for path traversal attempts
            if ".." in path or path.startswith("/") or path.startswith("\\"):
                return False

        # Validate write operation
        if operation == "write":
            content = kwargs.get("content")
            if content is None:
                return False

        # Validate search operation
        if operation == "search":
            pattern = kwargs.get("pattern", "").strip()
            if not pattern:
                return False

        return True

    async def _read_file(self, kwargs: dict[str, Any]) -> PluginResult:
        """
        Read file contents.

        Args:
            kwargs: Must contain 'path'

        Returns:
            PluginResult with file contents
        """
        path = kwargs.get("path", "").strip()
        safe_path = self._get_safe_path(path)

        if not safe_path.exists():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"File not found: {path}",
            )

        if not safe_path.is_file():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Path is not a file: {path}",
            )

        # Check file size
        file_size = safe_path.stat().st_size
        if file_size > self.max_file_size_bytes:
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"File too large: {file_size / 1024 / 1024:.1f}MB "
                f"(max: {self.max_file_size_bytes / 1024 / 1024:.1f}MB)",
            )

        # Read file
        async with aiofiles.open(safe_path, "r", encoding="utf-8") as f:
            content = await f.read()

        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={
                "path": path,
                "content": content,
                "size_bytes": file_size,
                "lines": len(content.splitlines()),
            },
        )

    async def _write_file(self, kwargs: dict[str, Any]) -> PluginResult:
        """
        Write content to file.

        Args:
            kwargs: Must contain 'path' and 'content'

        Returns:
            PluginResult with write confirmation
        """
        path = kwargs.get("path", "").strip()
        content = kwargs.get("content", "")

        safe_path = self._get_safe_path(path)

        # Create parent directories if needed
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        async with aiofiles.open(safe_path, "w", encoding="utf-8") as f:
            await f.write(content)

        file_size = safe_path.stat().st_size

        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={
                "path": path,
                "size_bytes": file_size,
                "lines": len(content.splitlines()),
            },
        )

    async def _list_directory(self, kwargs: dict[str, Any]) -> PluginResult:
        """
        List directory contents.

        Args:
            kwargs: May contain 'path' (defaults to root workspace)

        Returns:
            PluginResult with directory listing
        """
        path = kwargs.get("path", "").strip() or "."
        safe_path = self._get_safe_path(path)

        if not safe_path.exists():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Directory not found: {path}",
            )

        if not safe_path.is_dir():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Path is not a directory: {path}",
            )

        # List contents
        items = []
        for item in safe_path.iterdir():
            item_info = {
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": item.stat().st_size if item.is_file() else 0,
            }
            items.append(item_info)

        # Sort: directories first, then files
        items.sort(key=lambda x: (x["type"] == "file", x["name"]))

        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={
                "path": path,
                "items": items,
                "count": len(items),
            },
        )

    async def _search_files(self, kwargs: dict[str, Any]) -> PluginResult:
        """
        Search for files by name pattern.

        Args:
            kwargs: Must contain 'pattern', may contain 'recursive'

        Returns:
            PluginResult with matching files
        """
        pattern = kwargs.get("pattern", "").strip()
        recursive = kwargs.get("recursive", False)

        if recursive:
            glob_pattern = f"**/{pattern}"
            matching_files = list(self.workspace.glob(glob_pattern))
        else:
            glob_pattern = pattern
            matching_files = list(self.workspace.glob(glob_pattern))

        # Convert to relative paths
        results = []
        for file_path in matching_files:
            relative_path = file_path.relative_to(self.workspace)
            results.append(
                {
                    "path": str(relative_path),
                    "type": "directory" if file_path.is_dir() else "file",
                    "size_bytes": file_path.stat().st_size if file_path.is_file() else 0,
                }
            )

        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={
                "pattern": pattern,
                "recursive": recursive,
                "matches": results,
                "count": len(results),
            },
        )

    async def _delete_file(self, kwargs: dict[str, Any]) -> PluginResult:
        """
        Delete a file.

        Args:
            kwargs: Must contain 'path'

        Returns:
            PluginResult with deletion confirmation
        """
        path = kwargs.get("path", "").strip()
        safe_path = self._get_safe_path(path)

        if not safe_path.exists():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"File not found: {path}",
            )

        if not safe_path.is_file():
            return PluginResult(
                status=PluginStatus.FAILED,
                error=f"Path is not a file: {path}",
            )

        # Delete file
        safe_path.unlink()

        return PluginResult(
            status=PluginStatus.SUCCESS,
            data={
                "path": path,
                "deleted": True,
            },
        )

    def _get_safe_path(self, relative_path: str) -> Path:
        """
        Convert relative path to safe absolute path within workspace.

        Args:
            relative_path: Relative path from user

        Returns:
            Safe absolute path

        Raises:
            ValueError: If path attempts to escape workspace
        """
        # Normalize and resolve path
        safe_path = (self.workspace / relative_path).resolve()

        # Ensure path is within workspace
        try:
            safe_path.relative_to(self.workspace.resolve())
        except ValueError:
            raise ValueError(f"Path outside workspace: {relative_path}")

        return safe_path

    async def cleanup(self) -> None:
        """No cleanup needed for file operations."""
        pass
