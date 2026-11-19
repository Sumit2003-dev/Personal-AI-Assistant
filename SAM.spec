# SAM.spec — PyInstaller build specification
# Generated for SAM v7.0.0
# Target: Windows 11, Python 3.14, x64
#
# Build with:
#   pyinstaller SAM.spec --noconfirm
#
# Output: dist\SAM\SAM.exe  (one-folder build)
# Installer input: dist\SAM\

from PyInstaller.building.api import PYZ, EXE, COLLECT
from PyInstaller.building.build_main import Analysis
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
import sys
import os

block_cipher = None

# ---------------------------------------------------------------------------
# Data files to bundle (read-only assets)
# ---------------------------------------------------------------------------

datas = [
    # Frontend assets
    ("sam/desktop/templates",   "sam/desktop/templates"),
    ("sam/desktop/static",      "sam/desktop/static"),
    # Configuration defaults
    ("sam/config",              "sam/config"),
    # Application icon
    ("packaging/assets/sam_icon.ico",  "packaging/assets"),
    ("packaging/assets/sam_icon.png",  "packaging/assets"),
    # Backend runner
    ("sam_backend_runner.py",   "."),
]

# Include uvicorn static files and templates
datas += collect_data_files("uvicorn")
datas += collect_data_files("starlette")
datas += collect_data_files("fastapi")
datas += collect_data_files("pystray")

# ---------------------------------------------------------------------------
# Hidden imports — modules that PyInstaller misses via static analysis
# ---------------------------------------------------------------------------

hidden_imports = [
    # FastAPI / Starlette / uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "starlette.middleware.cors",
    "starlette.routing",
    "starlette.staticfiles",
    "starlette.templating",
    "fastapi.middleware.cors",
    # Pydantic
    "pydantic",
    "pydantic.v1",
    # SAM modules
    "sam",
    "sam_backend_runner",
    "sam.launcher",
    "sam.launcher.app_launcher",
    "sam.launcher.runtime_check",
    "sam.launcher.config_manager",
    "sam.launcher.startup_manager",
    "sam.config.settings",
    "sam.desktop.web_desktop",
    "sam.agent.models_provider",
    "sam.browser.browser_agent",
    "sam.coding.coding_agent",
    "sam.computer_use.operator",
    "sam.documents.doc_engine",
    "sam.executor.task_executor",
    "sam.integrations.app_registry",
    "sam.memory.sqlite_memory",
    "sam.monitoring.system_monitor",
    "sam.planner.task_planner",
    "sam.security.permissions",
    "sam.security.audit",
    "sam.tools.tool_registry",
    "sam.video.video_pipeline",
    "sam.vision.screen_observer",
    "sam.voice.voice_interface",
    # Optional / conditional
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    # Windows system
    "winreg",
    "ctypes",
    "ctypes.wintypes",
    "socket",
    "sqlite3",
    "pydoc",
    # Scientific
    "numpy",
    "psutil",
    "httpx",
]

# SAM submodules
hidden_imports += collect_submodules("sam")

# ---------------------------------------------------------------------------
# Excludes — large optional packages not needed in the bundle
# ---------------------------------------------------------------------------

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow",
    "tensorboard",
    "keras",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "tkinter",
    "test",
    "unittest",
    "doctest",
    "pdb",
]

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    ["sam_main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=["packaging/hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX compression can break some DLLs on Windows
    console=False,      # No console window (Windows GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="packaging/assets/sam_icon.ico",
    version="packaging/version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SAM",
)
