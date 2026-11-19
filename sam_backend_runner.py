"""
SAM Backend Runner — standalone entry point for the FastAPI server
Executed as a subprocess by the launcher (or directly for development).
Handles APPDATA path redirection so user data lives outside the install dir.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — must happen before any SAM import
# ---------------------------------------------------------------------------

def _bootstrap_paths() -> None:
    r"""
    When running from a PyInstaller bundle, insert the bundle base path so
    SAM package imports resolve correctly. Also redirect writable paths to
    %APPDATA%\SAM so the bundle directory stays read-only.
    """
    if getattr(sys, "frozen", False):
        bundle_root = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        bundle_root = Path(__file__).resolve().parent

    if str(bundle_root) not in sys.path:
        sys.path.insert(0, str(bundle_root))

    # Redirect SAM writable paths to APPDATA\SAM
    sam_data_root = os.environ.get(
        "SAM_DATA_ROOT",
        str(Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM"),
    )

    # Patch settings before importing them
    os.environ.setdefault("SAM_DATA_ROOT", sam_data_root)
    os.environ.setdefault("SAM_OLLAMA_HOST", "http://127.0.0.1:11434")
    os.environ.setdefault("SAM_UI_HOST", "127.0.0.1")
    os.environ.setdefault("SAM_UI_PORT", "8765")


_bootstrap_paths()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def _resolve_backend_log_dir() -> Path:
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

_log_dir = _resolve_backend_log_dir()
logger = logging.getLogger("sam.backend_runner")

if not logger.handlers:
    try:
        _handler = logging.FileHandler(_log_dir / "backend.log", encoding="utf-8")
        _formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        _handler.setFormatter(_formatter)
        logger.addHandler(_handler)
    except Exception:
        pass
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Settings path override — patch before importing sam.config.settings
# ---------------------------------------------------------------------------

def _patch_settings() -> None:
    """
    Override SAM's BASE_DIR / DATA_DIR to use the APPDATA location
    when running from an installed application.
    """
    try:
        import sam.config.settings as _settings_mod
        from pathlib import Path as _P

        sam_data_root = _P(os.environ["SAM_DATA_ROOT"])
        target_data = sam_data_root / "data"
        target_logs = sam_data_root / "logs"
        try:
            target_data.mkdir(parents=True, exist_ok=True)
            target_logs.mkdir(parents=True, exist_ok=True)
            _settings_mod.DATA_DIR = target_data
            _settings_mod.LOGS_DIR = target_logs
            _settings_mod.settings.data_dir = target_data
            _settings_mod.settings.logs_dir = target_logs
            logger.info("Data root: %s", sam_data_root)
        except (PermissionError, OSError) as pe:
            logger.warning("Could not create requested data root %s: %s; retaining default.", sam_data_root, pe)
    except Exception as exc:
        logger.warning("Settings patch skipped: %s", exc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    logger.info("SAM Backend Runner starting…")
    _patch_settings()

    try:
        import uvicorn
        from sam.desktop.web_desktop import app
        from sam.config.settings import settings

        host = os.environ.get("SAM_UI_HOST", settings.desktop.ui_host)
        port = int(os.environ.get("SAM_UI_PORT", settings.desktop.ui_port))

        logger.info("Listening on http://%s:%d", host, port)
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
        )
    except Exception as exc:
        logger.critical("Backend startup failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
