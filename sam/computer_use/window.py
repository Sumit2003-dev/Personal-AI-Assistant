"""
SAM - Windows Window Management & Inspection
Direct Win32 window locator, foreground switcher, bounds inspector, and resizer.
"""

import ctypes
from ctypes import wintypes
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("sam.computer_use.window")
user32 = ctypes.windll.user32

SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
WM_CLOSE = 0x0010


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class WindowManager:
    """Manages active Windows desktop windows and focus."""

    @staticmethod
    def get_window_title(hwnd: int) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            return buff.value
        return ""

    @staticmethod
    def get_window_rect(hwnd: int) -> Dict[str, int]:
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "x": rect.left,
            "y": rect.top,
            "width": max(0, rect.right - rect.left),
            "height": max(0, rect.bottom - rect.top),
        }

    def get_foreground_window(self) -> Dict[str, Any]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"hwnd": 0, "title": "Desktop / Taskbar", "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080}}
        title = self.get_window_title(hwnd)
        rect = self.get_window_rect(hwnd)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return {
            "hwnd": hwnd,
            "title": title or "Unknown Window",
            "pid": pid.value,
            "rect": rect,
        }

    def list_windows(self) -> List[Dict[str, Any]]:
        windows = []

        def enum_callback(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                title = self.get_window_title(hwnd)
                if title and title != "Program Manager":
                    rect = self.get_window_rect(hwnd)
                    if rect["width"] > 50 and rect["height"] > 50:
                        windows.append({
                            "hwnd": hwnd,
                            "title": title,
                            "rect": rect,
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_callback)
        user32.EnumWindows(cb, 0)
        return windows

    def find_window(self, query: str) -> Optional[Dict[str, Any]]:
        q = query.lower()
        windows = self.list_windows()
        for w in windows:
            if q in w["title"].lower():
                return w
        return None

    def focus_window(self, hwnd: int) -> bool:
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            logger.warning(f"Failed to focus window {hwnd}: {e}")
            return False

    def resize_move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        try:
            return bool(user32.MoveWindow(hwnd, x, y, width, height, True))
        except Exception as e:
            logger.warning(f"Failed to MoveWindow {hwnd}: {e}")
            return False

    def close_window(self, hwnd: int) -> bool:
        try:
            return bool(user32.PostMessageW(hwnd, WM_CLOSE, 0, 0))
        except Exception as e:
            logger.warning(f"Failed to close window {hwnd}: {e}")
            return False


window_manager = WindowManager()

