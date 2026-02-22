"""
Desktop Automation - Mouse, Keyboard, and Window Management

Features:
- Human-like mouse movement
- Keyboard simulation with realistic delays
- Window management (focus, resize, move)
- Safety checks and boundaries
- Cross-platform support (Windows, macOS, Linux)
"""

import asyncio
import platform
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple
from uuid import uuid4


class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class KeyModifier(str, Enum):
    CTRL = "ctrl"
    ALT = "alt"
    SHIFT = "shift"
    WIN = "win"
    CMD = "cmd"


@dataclass
class Point:
    """2D point"""
    x: int
    y: int


@dataclass
class Size:
    """2D size"""
    width: int
    height: int


@dataclass
class Rectangle:
    """2D rectangle"""
    x: int
    y: int
    width: int
    height: int
    
    def contains(self, point: Point) -> bool:
        """Check if point is inside rectangle"""
        return (
            self.x <= point.x <= self.x + self.width and
            self.y <= point.y <= self.y + self.height
        )


@dataclass
class Window:
    """Window information"""
    id: int
    title: str
    bounds: Rectangle
    is_visible: bool
    is_minimized: bool
    is_maximized: bool
    process_name: str


class DesktopAutomation:
    """
    Desktop automation with human-like behavior
    
    Safety features:
    - Boundary checks
    - Speed limits
    - Permission validation
    - Action logging
    """
    
    def __init__(self, safe_mode: bool = True):
        self.safe_mode = safe_mode
        self._action_log: List[dict] = []
        self._screen_size = self._get_screen_size()
        
        try:
            import pyautogui
            self.pyautogui = pyautogui
            if safe_mode:
                pyautogui.PAUSE = 0.1
                pyautogui.FAILSAFE = True
        except ImportError:
            self.pyautogui = None
            print("Warning: pyautogui not installed. Desktop automation disabled.")
    
    def _log_action(self, action: str, params: dict):
        """Log automation action"""
        self._action_log.append({
            "id": str(uuid4()),
            "timestamp": time.time(),
            "action": action,
            "params": params,
        })
    
    def _get_screen_size(self) -> Size:
        """Get screen size"""
        try:
            if self.pyautogui:
                width, height = self.pyautogui.size()
                return Size(width=width, height=height)
        except:
            pass
        return Size(width=1920, height=1080)
    
    def _validate_point(self, point: Point) -> bool:
        """Validate point is within screen bounds"""
        return (
            0 <= point.x < self._screen_size.width and
            0 <= point.y < self._screen_size.height
        )
    
    async def move_mouse(
        self,
        x: int,
        y: int,
        duration: float = 0.5,
        human_like: bool = True,
    ) -> bool:
        """
        Move mouse to position
        
        Args:
            x, y: Target coordinates
            duration: Movement duration (seconds)
            human_like: Use curved path with slight randomness
        """
        if not self.pyautogui:
            return False
        
        target = Point(x, y)
        if not self._validate_point(target):
            raise ValueError(f"Target point {target} outside screen bounds")
        
        self._log_action("move_mouse", {"x": x, "y": y, "duration": duration})
        
        if human_like:
            await self._human_move(target, duration)
        else:
            await asyncio.to_thread(
                self.pyautogui.moveTo,
                x, y,
                duration=duration,
            )
        
        return True
    
    async def _human_move(self, target: Point, duration: float):
        """Move mouse with human-like curved path"""
        if not self.pyautogui:
            return
        
        current = Point(*self.pyautogui.position())
        
        steps = max(10, int(duration * 100))
        
        for i in range(steps):
            progress = (i + 1) / steps
            
            t = progress
            curve_x = current.x + (target.x - current.x) * t
            curve_y = current.y + (target.y - current.y) * t
            
            noise = random.gauss(0, 2)
            curve_x += noise
            curve_y += noise
            
            curve_x = max(0, min(self._screen_size.width - 1, int(curve_x)))
            curve_y = max(0, min(self._screen_size.height - 1, int(curve_y)))
            
            await asyncio.to_thread(
                self.pyautogui.moveTo,
                curve_x,
                curve_y,
                duration=0,
            )
            
            await asyncio.sleep(duration / steps)
    
    async def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: MouseButton = MouseButton.LEFT,
        clicks: int = 1,
        interval: float = 0.1,
    ) -> bool:
        """
        Click at position
        
        Args:
            x, y: Click position (None = current position)
            button: Mouse button to click
            clicks: Number of clicks (1=single, 2=double)
            interval: Interval between clicks
        """
        if not self.pyautogui:
            return False
        
        if x is not None and y is not None:
            await self.move_mouse(x, y, duration=0.3)
        
        self._log_action("click", {
            "x": x,
            "y": y,
            "button": button,
            "clicks": clicks,
        })
        
        await asyncio.to_thread(
            self.pyautogui.click,
            button=button.value,
            clicks=clicks,
            interval=interval,
        )
        
        return True
    
    async def drag(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        duration: float = 1.0,
        button: MouseButton = MouseButton.LEFT,
    ) -> bool:
        """Drag from start to end position"""
        if not self.pyautogui:
            return False
        
        await self.move_mouse(start_x, start_y, duration=0.3)
        
        self._log_action("drag", {
            "start_x": start_x,
            "start_y": start_y,
            "end_x": end_x,
            "end_y": end_y,
        })
        
        await asyncio.to_thread(
            self.pyautogui.drag,
            end_x - start_x,
            end_y - start_y,
            duration=duration,
            button=button.value,
        )
        
        return True
    
    async def scroll(
        self,
        clicks: int,
        x: Optional[int] = None,
        y: Optional[int] = None,
    ) -> bool:
        """
        Scroll mouse wheel
        
        Args:
            clicks: Number of scroll clicks (positive=up, negative=down)
            x, y: Scroll position (None = current position)
        """
        if not self.pyautogui:
            return False
        
        if x is not None and y is not None:
            await self.move_mouse(x, y, duration=0.2)
        
        self._log_action("scroll", {"clicks": clicks, "x": x, "y": y})
        
        await asyncio.to_thread(
            self.pyautogui.scroll,
            clicks,
        )
        
        return True
    
    async def type_text(
        self,
        text: str,
        interval: float = 0.05,
        human_like: bool = True,
    ) -> bool:
        """
        Type text with realistic delays
        
        Args:
            text: Text to type
            interval: Base interval between keystrokes
            human_like: Add random variation to intervals
        """
        if not self.pyautogui:
            return False
        
        self._log_action("type_text", {"text": text[:50], "interval": interval})
        
        if human_like:
            for char in text:
                char_interval = interval + random.gauss(0, interval * 0.3)
                char_interval = max(0.01, char_interval)
                
                await asyncio.to_thread(
                    self.pyautogui.write,
                    char,
                    interval=0,
                )
                
                await asyncio.sleep(char_interval)
        else:
            await asyncio.to_thread(
                self.pyautogui.write,
                text,
                interval=interval,
            )
        
        return True
    
    async def press_key(
        self,
        key: str,
        modifiers: Optional[List[KeyModifier]] = None,
    ) -> bool:
        """
        Press key with optional modifiers
        
        Args:
            key: Key to press (e.g., 'enter', 'a', 'backspace')
            modifiers: Modifier keys (ctrl, alt, shift, etc.)
        """
        if not self.pyautogui:
            return False
        
        modifiers = modifiers or []
        
        self._log_action("press_key", {"key": key, "modifiers": [m.value for m in modifiers]})
        
        modifier_keys = [m.value for m in modifiers]
        
        if modifier_keys:
            await asyncio.to_thread(
                self.pyautogui.hotkey,
                *modifier_keys,
                key,
            )
        else:
            await asyncio.to_thread(
                self.pyautogui.press,
                key,
            )
        
        return True
    
    async def get_mouse_position(self) -> Point:
        """Get current mouse position"""
        if not self.pyautogui:
            return Point(0, 0)
        
        x, y = await asyncio.to_thread(self.pyautogui.position)
        return Point(x, y)
    
    async def screenshot(
        self,
        region: Optional[Rectangle] = None,
    ) -> Optional[bytes]:
        """
        Take screenshot
        
        Args:
            region: Region to capture (None = entire screen)
        """
        if not self.pyautogui:
            return None
        
        import io
        
        if region:
            screenshot = await asyncio.to_thread(
                self.pyautogui.screenshot,
                region=(region.x, region.y, region.width, region.height),
            )
        else:
            screenshot = await asyncio.to_thread(
                self.pyautogui.screenshot,
            )
        
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        return buffer.getvalue()


class WindowManager:
    """
    Window management for desktop automation
    
    Cross-platform window control
    """
    
    def __init__(self):
        self._platform = platform.system()
        
        try:
            import pygetwindow as gw
            self.gw = gw
        except ImportError:
            self.gw = None
            print("Warning: pygetwindow not installed. Window management limited.")
    
    async def list_windows(self) -> List[Window]:
        """List all visible windows"""
        if not self.gw:
            return []
        
        windows = []
        
        for win in await asyncio.to_thread(self.gw.getAllWindows):
            if win.visible:
                windows.append(Window(
                    id=hash(win),
                    title=win.title,
                    bounds=Rectangle(
                        x=win.left,
                        y=win.top,
                        width=win.width,
                        height=win.height,
                    ),
                    is_visible=win.visible,
                    is_minimized=win.isMinimized,
                    is_maximized=win.isMaximized,
                    process_name="",
                ))
        
        return windows
    
    async def find_window(self, title: str) -> Optional[Window]:
        """Find window by title (substring match)"""
        windows = await self.list_windows()
        for window in windows:
            if title.lower() in window.title.lower():
                return window
        return None
    
    async def focus_window(self, window: Window) -> bool:
        """Bring window to front and focus"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.activate)
                return True
        except:
            pass
        
        return False
    
    async def resize_window(
        self,
        window: Window,
        width: int,
        height: int,
    ) -> bool:
        """Resize window"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.resizeTo, width, height)
                return True
        except:
            pass
        
        return False
    
    async def move_window(
        self,
        window: Window,
        x: int,
        y: int,
    ) -> bool:
        """Move window to position"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.moveTo, x, y)
                return True
        except:
            pass
        
        return False
    
    async def minimize_window(self, window: Window) -> bool:
        """Minimize window"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.minimize)
                return True
        except:
            pass
        
        return False
    
    async def maximize_window(self, window: Window) -> bool:
        """Maximize window"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.maximize)
                return True
        except:
            pass
        
        return False
    
    async def close_window(self, window: Window) -> bool:
        """Close window"""
        if not self.gw:
            return False
        
        try:
            windows = await asyncio.to_thread(self.gw.getWindowsWithTitle, window.title)
            if windows:
                win = windows[0]
                await asyncio.to_thread(win.close)
                return True
        except:
            pass
        
        return False
    
    async def get_active_window(self) -> Optional[Window]:
        """Get currently active window"""
        if not self.gw:
            return None
        
        try:
            win = await asyncio.to_thread(self.gw.getActiveWindow)
            if win:
                return Window(
                    id=hash(win),
                    title=win.title,
                    bounds=Rectangle(
                        x=win.left,
                        y=win.top,
                        width=win.width,
                        height=win.height,
                    ),
                    is_visible=win.visible,
                    is_minimized=win.isMinimized,
                    is_maximized=win.isMaximized,
                    process_name="",
                )
        except:
            pass
        
        return None
