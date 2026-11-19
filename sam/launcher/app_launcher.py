"""
SAM Application Launcher — Windows Desktop Entry Point
Manages:
  - Duplicate-instance prevention (Windows named mutex)
  - Runtime / dependency checks
  - User data directory setup
  - Settings migration from previous versions
  - FastAPI backend server startup (subprocess)
  - Browser window opening
  - System tray icon (optional, via pystray)
  - Graceful shutdown on exit / OS signal

This module is the main entry point for the packaged SAM.exe.
It has NO hard dependency on FastAPI, uvicorn or any heavy AI library at import time.
"""

from __future__ import annotations

import ctypes
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging — write to both console and rotating file in APPDATA\SAM\logs
# ---------------------------------------------------------------------------

def _resolve_log_dir() -> Path:
    env_root = os.environ.get("SAM_DATA_ROOT")
    if env_root:
        base = Path(env_root) / "logs"
    else:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM" / "logs"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        import tempfile
        base = Path(tempfile.gettempdir()) / "SAM" / "logs"
        base.mkdir(parents=True, exist_ok=True)
    return base

_LOG_DIR = _resolve_log_dir()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_LOG_DIR / "launcher.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("sam.launcher")

from enum import Enum

# ---------------------------------------------------------------------------
# Launcher States
# ---------------------------------------------------------------------------

class LauncherState(str, Enum):
    INITIALIZING = "INITIALIZING"
    CHECKING_DEPENDENCIES = "CHECKING_DEPENDENCIES"
    STARTING_BACKEND = "STARTING_BACKEND"
    WAITING_FOR_HEALTH = "WAITING_FOR_HEALTH"
    READY = "READY"
    STARTUP_FAILED = "STARTUP_FAILED"
    SHUTTING_DOWN = "SHUTTING_DOWN"


_current_state: LauncherState = LauncherState.INITIALIZING


def get_launcher_state() -> LauncherState:
    """Returns the current state of the application launcher."""
    return _current_state


def _set_state(new_state: LauncherState) -> None:
    global _current_state
    logger.info("Launcher state transition: %s -> %s", _current_state.value, new_state.value)
    _current_state = new_state


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
APP_NAME = "SAM"
APP_VERSION = "7.0.0"
MUTEX_NAME = "Global\\SAM_DesktopApp_SingleInstance_7"
UI_HOST = "127.0.0.1"
UI_PORT = 8765
UI_URL = f"http://{UI_HOST}:{UI_PORT}"
STARTUP_TIMEOUT_S = 30  # seconds to wait for backend to respond


# ---------------------------------------------------------------------------
# Single-instance guard (Windows named mutex)
# ---------------------------------------------------------------------------

def _acquire_single_instance_mutex() -> Optional[int]:
    """
    Creates a Windows named mutex.  Returns the handle on success, None if SAM
    is already running (mutex already owned by another process).
    """
    if sys.platform != "win32":
        return -1  # non-Windows: skip guard

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    last_err = kernel32.GetLastError()

    ERROR_ALREADY_EXISTS = 183
    if last_err == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def _release_mutex(handle: Optional[int]) -> None:
    if sys.platform == "win32" and handle and handle != -1:
        ctypes.windll.kernel32.ReleaseMutex(handle)  # type: ignore[attr-defined]
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Backend server management
# ---------------------------------------------------------------------------

_server_proc: Optional[subprocess.Popen] = None
_shutdown_event = threading.Event()


def _resolve_backend_script() -> str:
    """
    Returns the path to the backend entry-point.
    Works both in PyInstaller bundles (sys._MEIPASS) and from source.
    """
    # PyInstaller frozen bundle
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent  # repo root

    # Prefer a dedicated backend runner script
    candidate = base / "sam_backend_runner.py"
    if candidate.exists():
        return str(candidate)

    # Fallback: run web_desktop directly
    return str(base / "sam" / "desktop" / "web_desktop.py")


def _start_backend() -> subprocess.Popen:
    """
    Launches the FastAPI uvicorn server as a subprocess.
    Streams stdout/stderr to the launcher log file.
    """
    script = _resolve_backend_script()
    log_file = _LOG_DIR / "backend.log"
    logger.info("Starting SAM backend: %s", script)

    env = os.environ.copy()
    # Pass user data root so the backend can redirect writable paths
    env["SAM_DATA_ROOT"] = str(
        Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM"
    )
    env["SAM_UI_HOST"] = UI_HOST
    env["SAM_UI_PORT"] = str(UI_PORT)

    with open(log_file, "a", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=fh,
            stderr=fh,
            env=env,
            stdin=subprocess.DEVNULL,
            cwd=str(Path(script).parent.parent.parent),  # repo / bundle root
        )

    logger.info("Backend process PID: %d", proc.pid)
    return proc


def _wait_for_backend(timeout: float = STARTUP_TIMEOUT_S) -> bool:
    """
    Polls the backend health endpoint until it responds or times out.
    Returns True if the server is ready.
    """
    import socket

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _server_proc and _server_proc.poll() is not None:
            logger.error("Backend exited prematurely with code %d", _server_proc.returncode)
            return False
        try:
            with socket.create_connection((UI_HOST, UI_PORT), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _stop_backend() -> None:
    global _server_proc
    if _server_proc is None:
        return
    logger.info("Stopping SAM backend (PID %d)…", _server_proc.pid)
    _server_proc.terminate()
    try:
        _server_proc.wait(timeout=8.0)
    except subprocess.TimeoutExpired:
        _server_proc.kill()
        _server_proc.wait(timeout=2.0)
    _server_proc = None
    logger.info("Backend stopped.")


# ---------------------------------------------------------------------------
# System tray (pystray — optional)
# ---------------------------------------------------------------------------

def _is_port_in_use(host: str, port: int) -> bool:
    """Checks whether the specified TCP host:port is already listening."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def _tray_action_open_ui(_icon=None, _item=None):
    webbrowser.open(UI_URL)


def _tray_action_status(_icon=None, _item=None):
    status_msg = (
        f"SAM Desktop v{APP_VERSION}\n"
        f"Launcher State: {get_launcher_state().value}\n"
        f"Interface URL: {UI_URL}\n"
        f"Backend PID: {_server_proc.pid if _server_proc else 'None'}\n"
        f"Logs Location: {_LOG_DIR}"
    )
    _show_info_dialog("SAM Status", status_msg)


def _tray_action_open_logs(_icon=None, _item=None):
    if sys.platform == "win32" and hasattr(os, "startfile"):
        os.startfile(str(_LOG_DIR))
    else:
        webbrowser.open(f"file://{_LOG_DIR}")


def _tray_action_restart_backend(_icon=None, _item=None):
    logger.info("Restart requested via tray.")
    _set_state(LauncherState.SHUTTING_DOWN)
    _stop_backend()
    global _server_proc
    _set_state(LauncherState.STARTING_BACKEND)
    _server_proc = _start_backend()
    _set_state(LauncherState.WAITING_FOR_HEALTH)
    if _wait_for_backend():
        _set_state(LauncherState.READY)
        logger.info("Backend restarted successfully.")
    else:
        _set_state(LauncherState.STARTUP_FAILED)
        logger.error("Backend restart failed.")


def _tray_action_exit_app(icon=None, _item=None):
    if icon:
        icon.stop()
    _shutdown_event.set()


def _build_tray_icon():
    """
    Returns a pystray.Icon instance. If pystray is not available returns None.
    """
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    # Generate a simple 64×64 icon programmatically (cyan circle on dark)
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=(0, 200, 255, 255))
    draw.ellipse([18, 18, size - 18, size - 18], fill=(15, 20, 30, 255))

    # Prefer a real icon if present
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "sam_icon.png"
    if icon_path.exists():
        try:
            img = Image.open(icon_path).convert("RGBA").resize((size, size))
        except Exception:
            pass

    menu = pystray.Menu(
        pystray.MenuItem("Open SAM", _tray_action_open_ui, default=True),
        pystray.MenuItem("Show Application Status", _tray_action_status),
        pystray.MenuItem("Open Logs Folder", _tray_action_open_logs),
        pystray.MenuItem("Restart SAM", _tray_action_restart_backend),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit SAM", _tray_action_exit_app),
    )
    return pystray.Icon(APP_NAME, img, f"{APP_NAME} v{APP_VERSION} ({get_launcher_state().value})", menu=menu)


# ---------------------------------------------------------------------------
# User data migration / setup
# ---------------------------------------------------------------------------

def _migrate_user_data() -> None:
    r"""
    Migrates SQLite memory, task history, and configuration from the old
    in-repo data directory into %APPDATA%\SAM if not already migrated.
    Existing files are never overwritten — only missing files are copied.
    """
    new_root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM"

    # Try to find old in-repo data location
    if getattr(sys, "frozen", False):
        return  # In a frozen build the in-repo path doesn't exist

    old_root = Path(__file__).resolve().parent.parent.parent / "sam" / "data"
    if not old_root.exists():
        return

    import shutil

    for src in old_root.rglob("*"):
        if src.is_file():
            rel = src.relative_to(old_root)
            dst = new_root / "data" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                try:
                    shutil.copy2(src, dst)
                    logger.info("Migrated: %s → %s", src, dst)
                except Exception as exc:
                    logger.warning("Could not migrate %s: %s", src, exc)


def _show_info_dialog(title: str, message: str) -> None:
    logger.info("[%s] %s", title, message)
    if os.environ.get("SAM_HEADLESS") == "1" or "unittest" in sys.modules or "pytest" in sys.modules:
        return
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)  # MB_ICONINFORMATION
        except Exception:
            pass
    else:
        print(f"\n[{title}]\n{message}\n", file=sys.stdout)


def _show_error_dialog(title: str, message: str) -> None:
    logger.error("[%s] %s", title, message)
    if os.environ.get("SAM_HEADLESS") == "1" or "unittest" in sys.modules or "pytest" in sys.modules:
        return
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)  # type: ignore[attr-defined]
        except Exception:
            pass
    else:
        print(f"\n[{title}]\n{message}\n", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    global _server_proc

    _set_state(LauncherState.INITIALIZING)
    logger.info("SAM Desktop Launcher v%s starting…", APP_VERSION)

    # --- Single-instance guard ---
    mutex = _acquire_single_instance_mutex()
    if mutex is None:
        logger.warning("SAM is already running. Opening the existing window.")
        webbrowser.open(UI_URL)
        return 0

    # --- Runtime checks ---
    _set_state(LauncherState.CHECKING_DEPENDENCIES)
    try:
        from sam.launcher.runtime_check import run_checks
        checks = run_checks()
        logger.info("Runtime check:\n%s", checks.summary())
        for w in checks.warnings:
            logger.warning(w)
        if not checks.can_launch:
            _set_state(LauncherState.STARTUP_FAILED)
            errs = "\n".join(checks.critical_errors())
            _show_error_dialog(
                "SAM — Startup Error",
                f"SAM cannot start due to missing requirements:\n\n{errs}\n\n"
                "Please check the installer documentation.",
            )
            _release_mutex(mutex)
            return 2
    except Exception as exc:
        logger.warning("Runtime check failed (non-fatal): %s", exc)

    # --- User data migration ---
    try:
        _migrate_user_data()
    except Exception as exc:
        logger.warning("User data migration failed (non-fatal): %s", exc)

    # --- Port conflict verification ---
    if _is_port_in_use(UI_HOST, UI_PORT):
        # Probe if it's already a responsive SAM backend
        try:
            import socket
            with socket.create_connection((UI_HOST, UI_PORT), timeout=1.0):
                logger.info("Port %d is already open and responsive.", UI_PORT)
        except OSError:
            pass

    # --- Start backend ---
    _set_state(LauncherState.STARTING_BACKEND)
    try:
        _server_proc = _start_backend()
    except Exception as exc:
        _set_state(LauncherState.STARTUP_FAILED)
        _show_error_dialog("SAM — Backend Error", f"Could not start the SAM backend:\n\n{exc}")
        _release_mutex(mutex)
        return 3

    # --- Wait for backend readiness ---
    _set_state(LauncherState.WAITING_FOR_HEALTH)
    if not _wait_for_backend():
        _set_state(LauncherState.STARTUP_FAILED)
        _show_error_dialog(
            "SAM — Connection Error",
            f"The SAM backend did not start within {STARTUP_TIMEOUT_S} seconds.\n"
            f"Check {_LOG_DIR / 'backend.log'} for details.",
        )
        _stop_backend()
        _release_mutex(mutex)
        return 4

    _set_state(LauncherState.READY)
    logger.info("Backend ready at %s", UI_URL)

    # --- Open browser ---
    try:
        webbrowser.open(UI_URL)
    except Exception as exc:
        logger.warning("Could not open browser: %s", exc)

    # --- System tray ---
    tray = _build_tray_icon()

    def _signal_handler(sig, frame):
        logger.info("Signal %s received — shutting down.", sig)
        _shutdown_event.set()
        if tray:
            tray.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    if tray:
        tray_thread = threading.Thread(target=tray.run, daemon=True, name="tray")
        tray_thread.start()
        logger.info("System tray active.")

    # --- Main wait loop ---
    try:
        while not _shutdown_event.is_set():
            # Check if backend exited unexpectedly
            if _server_proc and _server_proc.poll() is not None:
                logger.error("Backend exited unexpectedly (code %d).", _server_proc.returncode)
                _set_state(LauncherState.STARTUP_FAILED)
                _shutdown_event.set()
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        _set_state(LauncherState.SHUTTING_DOWN)
        logger.info("Shutting down SAM…")
        _stop_backend()
        _release_mutex(mutex)

    logger.info("SAM exited cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
