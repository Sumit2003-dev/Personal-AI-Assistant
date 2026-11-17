"""
SAM Windows Startup Registration
Manages the optional "Start with Windows" feature via the HKCU Run registry key.
Never writes to HKLM (no admin rights required).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger("sam.launcher.startup_manager")

_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_REG_NAME = "SAMDesktopApp"


def _get_winreg():
    if sys.platform != "win32":
        return None
    try:
        import winreg
        return winreg
    except ImportError:
        return None


def is_startup_enabled() -> bool:
    winreg = _get_winreg()
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH, 0, winreg.KEY_READ)
        with key:
            winreg.QueryValueEx(key, _REG_NAME)
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.warning("Could not read startup registry: %s", exc)
        return False


def enable_startup(executable_path: str) -> bool:
    """
    Adds SAM to the user's Windows startup via HKCU Run.
    Uses the given executable path (must be the launcher .exe).
    """
    winreg = _get_winreg()
    if winreg is None:
        logger.info("Not on Windows — startup registration skipped.")
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_WRITE,
        )
        with key:
            winreg.SetValueEx(key, _REG_NAME, 0, winreg.REG_SZ, f'"{executable_path}"')
        logger.info("SAM startup enabled: %s", executable_path)
        return True
    except Exception as exc:
        logger.error("Could not set startup registry: %s", exc)
        return False


def disable_startup() -> bool:
    """Removes the SAM Windows startup entry."""
    winreg = _get_winreg()
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_PATH, 0,
            winreg.KEY_SET_VALUE | winreg.KEY_WRITE,
        )
        with key:
            winreg.DeleteValue(key, _REG_NAME)
        logger.info("SAM startup disabled.")
        return True
    except FileNotFoundError:
        return True  # Already not set
    except Exception as exc:
        logger.error("Could not remove startup registry: %s", exc)
        return False
