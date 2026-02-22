"""
Screen Capture System - Multi-Monitor Support
Optimized for <100ms capture time on Acer Swift Neo
"""
import asyncio
import base64
import io
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mss
import mss.tools
from PIL import Image
from loguru import logger


class CaptureMode(str, Enum):
    """Screen capture modes."""

    ALL_MONITORS = "all_monitors"
    PRIMARY = "primary"
    MONITOR = "monitor"
    REGION = "region"
    WINDOW = "window"


@dataclass
class Monitor:
    """Monitor information."""

    id: int
    left: int
    top: int
    width: int
    height: int
    is_primary: bool = False

    @property
    def bounds(self) -> Dict[str, int]:
        """Get monitor bounds for MSS."""
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}

    def __str__(self) -> str:
        """String representation."""
        primary = " (Primary)" if self.is_primary else ""
        return f"Monitor {self.id}{primary}: {self.width}x{self.height} at ({self.left}, {self.top})"


@dataclass
class Screenshot:
    """Screenshot data."""

    image: Image.Image
    timestamp: datetime
    monitor_id: Optional[int] = None
    region: Optional[Dict[str, int]] = None
    capture_time_ms: float = 0.0

    def save(self, path: Path, format: str = "PNG") -> Path:
        """Save screenshot to file."""
        self.image.save(path, format=format)
        logger.debug(f"Screenshot saved to {path}")
        return path

    def to_base64(self, format: str = "PNG") -> str:
        """Convert screenshot to base64 string."""
        buffer = io.BytesIO()
        self.image.save(buffer, format=format)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    def to_bytes(self, format: str = "PNG") -> bytes:
        """Convert screenshot to bytes."""
        buffer = io.BytesIO()
        self.image.save(buffer, format=format)
        buffer.seek(0)
        return buffer.read()

    @property
    def size(self) -> Tuple[int, int]:
        """Get image dimensions."""
        return self.image.size

    @property
    def width(self) -> int:
        """Get image width."""
        return self.image.size[0]

    @property
    def height(self) -> int:
        """Get image height."""
        return self.image.size[1]


class ScreenCapture:
    """
    High-performance screen capture system.
    Supports multi-monitor, region selection, and fast screenshots.
    Target: <100ms capture time.
    """

    def __init__(self, screenshot_dir: Optional[Path] = None):
        """
        Initialize screen capture system.

        Args:
            screenshot_dir: Directory to save screenshots (optional)
        """
        self.screenshot_dir = screenshot_dir or Path("data/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        self._sct: Optional[mss.mss] = None
        self._monitors: List[Monitor] = []
        self._monitor_cache_time: float = 0.0
        self._cache_ttl: float = 60.0  # Refresh monitors every 60 seconds

        logger.info("ScreenCapture initialized")

    def _get_sct(self) -> mss.mss:
        """Get or create MSS instance."""
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def _refresh_monitors(self) -> None:
        """Refresh monitor information (cached)."""
        current_time = time.time()
        if current_time - self._monitor_cache_time < self._cache_ttl:
            return

        sct = self._get_sct()
        self._monitors = []

        # MSS monitor 0 is all monitors combined, skip it
        for i, monitor in enumerate(sct.monitors[1:], start=1):
            self._monitors.append(
                Monitor(
                    id=i,
                    left=monitor["left"],
                    top=monitor["top"],
                    width=monitor["width"],
                    height=monitor["height"],
                    is_primary=(i == 1),  # First monitor is usually primary
                )
            )

        self._monitor_cache_time = current_time
        logger.debug(f"Refreshed monitor info: {len(self._monitors)} monitors detected")

    def get_monitors(self) -> List[Monitor]:
        """
        Get list of available monitors.

        Returns:
            List of Monitor objects
        """
        self._refresh_monitors()
        return self._monitors.copy()

    def get_primary_monitor(self) -> Monitor:
        """
        Get primary monitor.

        Returns:
            Primary Monitor object
        """
        self._refresh_monitors()
        for monitor in self._monitors:
            if monitor.is_primary:
                return monitor
        return self._monitors[0] if self._monitors else Monitor(1, 0, 0, 1920, 1080, True)

    def capture_all_monitors(self) -> List[Screenshot]:
        """
        Capture screenshots of all monitors.

        Returns:
            List of Screenshot objects (one per monitor)
        """
        start_time = time.time()
        self._refresh_monitors()
        sct = self._get_sct()

        screenshots = []
        for monitor in self._monitors:
            monitor_data = sct.monitors[monitor.id]
            sct_img = sct.grab(monitor_data)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            screenshot = Screenshot(
                image=img,
                timestamp=datetime.now(),
                monitor_id=monitor.id,
                region=monitor.bounds,
                capture_time_ms=(time.time() - start_time) * 1000,
            )
            screenshots.append(screenshot)

        total_time = (time.time() - start_time) * 1000
        logger.debug(
            f"Captured {len(screenshots)} monitors in {total_time:.2f}ms "
            f"({total_time/len(screenshots):.2f}ms per monitor)"
        )

        return screenshots

    def capture_primary(self) -> Screenshot:
        """
        Capture screenshot of primary monitor.

        Returns:
            Screenshot object
        """
        start_time = time.time()
        primary = self.get_primary_monitor()
        sct = self._get_sct()

        monitor_data = sct.monitors[primary.id]
        sct_img = sct.grab(monitor_data)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        capture_time = (time.time() - start_time) * 1000
        screenshot = Screenshot(
            image=img,
            timestamp=datetime.now(),
            monitor_id=primary.id,
            region=primary.bounds,
            capture_time_ms=capture_time,
        )

        logger.debug(f"Captured primary monitor in {capture_time:.2f}ms")
        return screenshot

    def capture_monitor(self, monitor_id: int) -> Screenshot:
        """
        Capture screenshot of specific monitor.

        Args:
            monitor_id: Monitor ID (1-indexed)

        Returns:
            Screenshot object
        """
        start_time = time.time()
        self._refresh_monitors()

        if monitor_id < 1 or monitor_id > len(self._monitors):
            raise ValueError(f"Invalid monitor_id: {monitor_id}. Available: 1-{len(self._monitors)}")

        sct = self._get_sct()
        monitor_data = sct.monitors[monitor_id]
        sct_img = sct.grab(monitor_data)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        capture_time = (time.time() - start_time) * 1000
        screenshot = Screenshot(
            image=img,
            timestamp=datetime.now(),
            monitor_id=monitor_id,
            region=self._monitors[monitor_id - 1].bounds,
            capture_time_ms=capture_time,
        )

        logger.debug(f"Captured monitor {monitor_id} in {capture_time:.2f}ms")
        return screenshot

    def capture_region(
        self, x: int, y: int, width: int, height: int, monitor_id: Optional[int] = None
    ) -> Screenshot:
        """
        Capture screenshot of specific region.

        Args:
            x: Left coordinate
            y: Top coordinate
            width: Region width
            height: Region height
            monitor_id: Optional monitor ID (defaults to primary)

        Returns:
            Screenshot object
        """
        start_time = time.time()
        sct = self._get_sct()

        region = {"left": x, "top": y, "width": width, "height": height}
        sct_img = sct.grab(region)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        capture_time = (time.time() - start_time) * 1000
        screenshot = Screenshot(
            image=img,
            timestamp=datetime.now(),
            monitor_id=monitor_id,
            region=region,
            capture_time_ms=capture_time,
        )

        logger.debug(f"Captured region {width}x{height} at ({x}, {y}) in {capture_time:.2f}ms")
        return screenshot

    async def capture_async(
        self,
        mode: CaptureMode = CaptureMode.PRIMARY,
        monitor_id: Optional[int] = None,
        region: Optional[Dict[str, int]] = None,
    ) -> Screenshot | List[Screenshot]:
        """
        Async wrapper for screenshot capture.

        Args:
            mode: Capture mode
            monitor_id: Monitor ID (for MONITOR mode)
            region: Region dict with left, top, width, height (for REGION mode)

        Returns:
            Screenshot or list of Screenshots (for ALL_MONITORS mode)
        """
        loop = asyncio.get_event_loop()

        if mode == CaptureMode.ALL_MONITORS:
            return await loop.run_in_executor(None, self.capture_all_monitors)
        elif mode == CaptureMode.PRIMARY:
            return await loop.run_in_executor(None, self.capture_primary)
        elif mode == CaptureMode.MONITOR:
            if monitor_id is None:
                raise ValueError("monitor_id required for MONITOR mode")
            return await loop.run_in_executor(None, self.capture_monitor, monitor_id)
        elif mode == CaptureMode.REGION:
            if region is None:
                raise ValueError("region required for REGION mode")
            return await loop.run_in_executor(
                None,
                self.capture_region,
                region["left"],
                region["top"],
                region["width"],
                region["height"],
                region.get("monitor_id"),
            )
        else:
            raise ValueError(f"Unsupported capture mode: {mode}")

    def save_screenshot(
        self, screenshot: Screenshot, filename: Optional[str] = None, format: str = "PNG"
    ) -> Path:
        """
        Save screenshot to file.

        Args:
            screenshot: Screenshot object
            filename: Optional filename (auto-generated if None)
            format: Image format (PNG, JPEG, etc.)

        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = screenshot.timestamp.strftime("%Y%m%d_%H%M%S_%f")
            monitor_suffix = f"_m{screenshot.monitor_id}" if screenshot.monitor_id else ""
            filename = f"screenshot_{timestamp}{monitor_suffix}.{format.lower()}"

        filepath = self.screenshot_dir / filename
        screenshot.save(filepath, format=format)
        return filepath

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._sct is not None:
            self._sct.close()
            self._sct = None
        logger.debug("ScreenCapture cleaned up")

    def __enter__(self) -> "ScreenCapture":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.cleanup()


# Global instance for convenience
_screen_capture_instance: Optional[ScreenCapture] = None


def get_screen_capture() -> ScreenCapture:
    """
    Get global ScreenCapture instance.

    Returns:
        Global ScreenCapture instance
    """
    global _screen_capture_instance
    if _screen_capture_instance is None:
        _screen_capture_instance = ScreenCapture()
    return _screen_capture_instance
