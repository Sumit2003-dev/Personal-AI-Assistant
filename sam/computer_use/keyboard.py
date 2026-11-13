"""
SAM - Windows Native Keyboard Automation
Direct Win32 SendInput controller supporting Unicode text input, hotkeys, and modifier sequences.
"""

import ctypes
from ctypes import wintypes
import time
from typing import List

user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Standard Virtual Key Codes
VK_MAP = {
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "escape": 0x1B,
    "esc": 0x1B,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "delete": 0x2E,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]


class KeyboardController:
    """Sends keystrokes, typing, and hotkeys via Windows SendInput API."""

    def _send_inputs(self, inputs: List[INPUT]):
        n = len(inputs)
        arr = (INPUT * n)(*inputs)
        user32.SendInput(n, arr, ctypes.sizeof(INPUT))

    def key_down(self, key: str):
        key_lower = key.lower()
        vk = VK_MAP.get(key_lower)
        if vk is None and len(key) == 1:
            vk = ord(key.upper())

        if vk is not None:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=None)
            self._send_inputs([inp])

    def key_up(self, key: str):
        key_lower = key.lower()
        vk = VK_MAP.get(key_lower)
        if vk is None and len(key) == 1:
            vk = ord(key.upper())

        if vk is not None:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            self._send_inputs([inp])

    def press_key(self, key: str, delay: float = 0.05):
        self.key_down(key)
        time.sleep(delay)
        self.key_up(key)

    def write_text(self, text: str, delay_per_char: float = 0.01):
        """Types unicode string using KEYEVENTF_UNICODE."""
        for char in text:
            code = ord(char)
            # Key down
            down = INPUT(type=INPUT_KEYBOARD)
            down.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)
            # Key up
            up = INPUT(type=INPUT_KEYBOARD)
            up.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)
            self._send_inputs([down, up])
            if delay_per_char > 0:
                time.sleep(delay_per_char)

    def hotkey(self, *keys: str, delay: float = 0.05):
        """Executes a hotkey sequence, e.g. hotkey('ctrl', 'c')."""
        for k in keys:
            self.key_down(k)
            time.sleep(0.02)
        time.sleep(delay)
        for k in reversed(keys):
            self.key_up(k)
            time.sleep(0.02)


keyboard_controller = KeyboardController()

