"""
Screen capture system for Ironclaw
Fast multi-monitor screen capture with MSS
"""
import time
from typing import List, Optional, Tuple, Dict
from pathlib import Path
import mss
import numpy as np
from PIL import Image
import base64
from io import BytesIO

from src.utils.logging import get_logger

logger = get_logger(__name__)


class ScreenCapture:
    """Fast screen capture with multi-monitor support."""
    
    def __init__(self):
        """Initialize screen capture."""
        self.sct = mss.mss()
        self.monitors = self.sct.monitors
        logger.info(f"Initialized screen capture with {len(self.monitors) - 1} monitors")
    
    def get_monitors(self) -> List[Dict]:
        """
        Get list of available monitors.
        
        Returns:
            List of monitor dictionaries with position and size
        """
        # Skip index 0 (all monitors combined)
        return [
            {
                "id": i,
                "left": mon["left"],
                "top": mon["top"],
                "width": mon["width"],
                "height": mon["height"],
            }
            for i, mon in enumerate(self.monitors[1:], start=1)
        ]
    
    def capture_monitor(
        self,
        monitor_id: int = 1,
        region: Optional[Tuple[int, int, int, int]] = None
    ) -> Image.Image:
        """
        Capture screenshot from specific monitor.
        
        Args:
            monitor_id: Monitor number (1-indexed)
            region: Optional (x, y, width, height) to capture specific region
        
        Returns:
            PIL Image of the screenshot
        """
        start_time = time.time()
        
        try:
            if region:
                # Capture specific region
                x, y, width, height = region
                monitor = {"left": x, "top": y, "width": width, "height": height}
            else:
                # Capture entire monitor
                if monitor_id >= len(self.monitors):
                    logger.warning(f"Monitor {monitor_id} not found, using monitor 1")
                    monitor_id = 1
                monitor = self.monitors[monitor_id]
            
            # Capture screenshot
            screenshot = self.sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            duration = (time.time() - start_time) * 1000  # ms
            logger.debug(f"Captured monitor {monitor_id} in {duration:.2f}ms")
            
            return img
        
        except Exception as e:
            logger.error(f"Failed to capture monitor {monitor_id}: {e}")
            raise
    
    def capture_all_monitors(self) -> List[Image.Image]:
        """
        Capture screenshots from all monitors.
        
        Returns:
            List of PIL Images, one per monitor
        """
        start_time = time.time()
        
        screenshots = []
        for i in range(1, len(self.monitors)):
            try:
                img = self.capture_monitor(monitor_id=i)
                screenshots.append(img)
            except Exception as e:
                logger.error(f"Failed to capture monitor {i}: {e}")
        
        duration = (time.time() - start_time) * 1000  # ms
        logger.info(f"Captured {len(screenshots)} monitors in {duration:.2f}ms")
        
        return screenshots
    
    def capture_region(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        monitor_id: int = 1
    ) -> Image.Image:
        """
        Capture specific region of screen.
        
        Args:
            x: Left coordinate
            y: Top coordinate
            width: Region width
            height: Region height
            monitor_id: Monitor to capture from
        
        Returns:
            PIL Image of the region
        """
        # Get monitor offset
        monitor = self.monitors[monitor_id]
        absolute_x = monitor["left"] + x
        absolute_y = monitor["top"] + y
        
        return self.capture_monitor(region=(absolute_x, absolute_y, width, height))
    
    def save_screenshot(
        self,
        img: Image.Image,
        filepath: str,
        format: str = "PNG"
    ) -> Path:
        """
        Save screenshot to file.
        
        Args:
            img: PIL Image to save
            filepath: Path to save to
            format: Image format (PNG, JPEG, etc.)
        
        Returns:
            Path object of saved file
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        img.save(str(path), format=format)
        logger.info(f"Saved screenshot to {path}")
        
        return path
    
    def image_to_base64(self, img: Image.Image, format: str = "PNG") -> str:
        """
        Convert PIL Image to base64 string.
        
        Args:
            img: PIL Image
            format: Image format
        
        Returns:
            Base64 encoded string
        """
        buffer = BytesIO()
        img.save(buffer, format=format)
        img_bytes = buffer.getvalue()
        return base64.b64encode(img_bytes).decode('utf-8')
    
    def image_to_numpy(self, img: Image.Image) -> np.ndarray:
        """
        Convert PIL Image to numpy array.
        
        Args:
            img: PIL Image
        
        Returns:
            Numpy array (H, W, C)
        """
        return np.array(img)
    
    def numpy_to_image(self, arr: np.ndarray) -> Image.Image:
        """
        Convert numpy array to PIL Image.
        
        Args:
            arr: Numpy array (H, W, C)
        
        Returns:
            PIL Image
        """
        return Image.fromarray(arr.astype('uint8'))
    
    def get_screen_resolution(self, monitor_id: int = 1) -> Tuple[int, int]:
        """
        Get screen resolution.
        
        Args:
            monitor_id: Monitor number
        
        Returns:
            Tuple of (width, height)
        """
        if monitor_id >= len(self.monitors):
            monitor_id = 1
        
        monitor = self.monitors[monitor_id]
        return (monitor["width"], monitor["height"])
    
    def close(self):
        """Close screen capture resources."""
        self.sct.close()
        logger.info("Screen capture closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
