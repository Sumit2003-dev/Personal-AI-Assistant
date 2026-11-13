"""
SAM - Windows Native Mouse Automation
Direct Win32 mouse controller providing high-precision movement, clicks, drags, and scrolling.
"""

import ctypes
from ctypes import wintypes
import time
import math
from typing import Tuple

user32 = ctypes.windll.user32

# Mouse Event Constants
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MouseController:
    """Provides native Windows mouse interaction."""

    def __init__(self):
        self.screen_width = user32.GetSystemMetrics(0)
        self.screen_height = user32.GetSystemMetrics(1)

    def get_position(self) -> Tuple[int, int]:
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return (pt.x, pt.y)

    def move_to(self, x: int, y: int, smooth: bool = True, duration: float = 0.2):
        """Moves cursor to (x, y) with optional smooth interpolation."""
        target_x = max(0, min(x, self.screen_width - 1))
        target_y = max(0, min(y, self.screen_height - 1))

        if not smooth or duration <= 0:
            user32.SetCursorPos(target_x, target_y)
            return

        start_x, start_y = self.get_position()
        steps = max(10, int(duration * 60))
        for i in range(1, steps + 1):
            t = i / steps
            # Smooth cubic ease-in-out
            ease = t * t * (3.0 - 2.0 * t)
            cur_x = int(start_x + (target_x - start_x) * ease)
            cur_y = int(start_y + (target_y - start_y) * ease)
            user32.SetCursorPos(cur_x, cur_y)
            time.sleep(duration / steps)

        user32.SetCursorPos(target_x, target_y)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left"):
        """Clicks at current or specified coordinate."""
        if x is not None and y is not None:
            self.move_to(x, y, smooth=False)

        if button.lower() == "left":
            user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif button.lower() == "right":
            user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        elif button.lower() == "middle":
            user32.mouse_event(MOUSEEVENTF_MIDDLEDOWN, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(MOUSEEVENTF_MIDDLEUP, 0, 0, 0, 0)

    def double_click(self, x: int | None = None, y: int | None = None):
        """Performs a double-click at current or specified coordinate."""
        self.click(x, y, button="left")
        time.sleep(0.08)
        self.click(button="left")

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.4):
        """Drags mouse from (start_x, start_y) to (end_x, end_y)."""
        self.move_to(start_x, start_y, smooth=False)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        time.sleep(0.05)
        self.move_to(end_x, end_y, smooth=True, duration=duration)
        time.sleep(0.05)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def scroll(self, clicks: int):
        """Scrolls mouse wheel. Positive = up, negative = down."""
        delta = clicks * 120
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)


mouse_controller = MouseController()

