"""
PyInstaller runtime hook for SAM — executed inside the frozen process
immediately after the bootloader starts, before any user code runs.
Sets up sys.path and environment variables needed by SAM in the bundle.
"""
import os
import sys
from pathlib import Path

# In a frozen bundle, sys._MEIPASS is the temp directory where PyInstaller
# extracts bundled files.  We add it to sys.path so SAM package imports work.
_base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
if str(_base) not in sys.path:
    sys.path.insert(0, str(_base))

# Default writable paths to APPDATA\SAM
_sam_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM"
os.environ.setdefault("SAM_DATA_ROOT", str(_sam_data))
os.environ.setdefault("SAM_UI_HOST", "127.0.0.1")
os.environ.setdefault("SAM_UI_PORT", "8765")
