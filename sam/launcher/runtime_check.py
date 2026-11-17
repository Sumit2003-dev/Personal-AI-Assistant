"""
SAM Runtime Environment Checker
Validates dependencies, Ollama availability and model presence before launch.
Provides structured results so the launcher / UI can present clear error messages.
"""

from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class DependencyStatus:
    name: str
    available: bool
    version: str = ""
    error: str = ""
    critical: bool = True


@dataclass
class OllamaStatus:
    installed: bool = False
    api_online: bool = False
    executable: str = ""
    models_found: List[str] = field(default_factory=list)
    required_models: List[str] = field(default_factory=lambda: ["qwen2.5:3b", "qwen3:4b"])
    missing_models: List[str] = field(default_factory=list)
    model_dir: str = ""
    error: str = ""


@dataclass
class RuntimeCheckResult:
    python_ok: bool = False
    python_version: str = ""
    dependencies: List[DependencyStatus] = field(default_factory=list)
    ollama: OllamaStatus = field(default_factory=OllamaStatus)
    user_data_dir: Path = field(default_factory=Path)
    can_launch: bool = False
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def critical_errors(self) -> List[str]:
        errs = list(self.errors)
        for d in self.dependencies:
            if not d.available and d.critical:
                errs.append(f"Missing required dependency: {d.name}")
        return errs

    def summary(self) -> str:
        lines = [f"Python {self.python_version} — {'OK' if self.python_ok else 'FAIL'}"]
        for dep in self.dependencies:
            status = f"v{dep.version}" if dep.available else f"MISSING — {dep.error}"
            lines.append(f"  {'✓' if dep.available else '✗'} {dep.name}: {status}")
        lines.append(f"Ollama installed: {'yes' if self.ollama.installed else 'no'}")
        lines.append(f"Ollama API online: {'yes' if self.ollama.api_online else 'no'}")
        if self.ollama.missing_models:
            lines.append(f"  Missing models: {', '.join(self.ollama.missing_models)}")
        lines.append(f"Can launch: {'YES' if self.can_launch else 'NO'}")
        for w in self.warnings:
            lines.append(f"  ⚠ {w}")
        for e in self.errors:
            lines.append(f"  ✗ {e}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

REQUIRED_MODULES = [
    ("fastapi", "fastapi", True),
    ("uvicorn", "uvicorn", True),
    ("pydantic", "pydantic", True),
    ("httpx", "httpx", True),
    ("psutil", "psutil", True),
    ("numpy", "numpy", True),
    ("PIL", "pillow", True),
    ("sounddevice", "sounddevice", False),
    ("cv2", "opencv-python", False),
    ("faster_whisper", "faster-whisper", False),
    ("pystray", "pystray", False),
]

OLLAMA_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    Path("C:/Program Files/Ollama/ollama.exe"),
    Path(shutil.which("ollama") or ""),
]

OLLAMA_API = "http://127.0.0.1:11434"


def _check_python() -> tuple[bool, str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    ok = sys.version_info >= (3, 11)
    return ok, version


def _check_modules() -> List[DependencyStatus]:
    results = []
    for import_name, pkg_name, critical in REQUIRED_MODULES:
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "?")
            results.append(DependencyStatus(name=pkg_name, available=True, version=version, critical=critical))
        except ImportError as exc:
            results.append(DependencyStatus(name=pkg_name, available=False, error=str(exc), critical=critical))
    return results


def _find_ollama_executable() -> str:
    for path in OLLAMA_CANDIDATES:
        if path and path.exists():
            return str(path)
    # Try PATH
    found = shutil.which("ollama")
    return found or ""


def _check_ollama_api(timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=timeout):
            return True
    except OSError:
        return False


def _list_ollama_models(exe: str) -> List[str]:
    try:
        result = subprocess.run(
            [exe, "list"],
            capture_output=True,
            text=True,
            timeout=5.0,
            stdin=subprocess.DEVNULL,
        )
        models = []
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if parts:
                models.append(parts[0].strip())
        return models
    except Exception:
        return []


def _get_model_dir() -> str:
    env = os.environ.get("OLLAMA_MODELS", "")
    if env and Path(env).exists():
        return env
    candidate = Path("D:/Ollama/models")
    if candidate.exists():
        return str(candidate)
    default = Path(os.environ.get("USERPROFILE", Path.home())) / ".ollama" / "models"
    return str(default)


def _ensure_user_data_dir() -> Path:
    """
    User-writable persistent data directory, outside the application install tree.
    %APPDATA%\\SAM is stable across application upgrades.
    Falls back gracefully if APPDATA is read-only / restricted in sandbox.
    """
    env_root = os.environ.get("SAM_DATA_ROOT")
    if env_root:
        base = Path(env_root)
    else:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM"
    try:
        for sub in ["data", "logs", "config", "workspaces", "exports", "screenshots"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        import tempfile
        base = Path(tempfile.gettempdir()) / "SAM"
        for sub in ["data", "logs", "config", "workspaces", "exports", "screenshots"]:
            (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def run_checks(require_ollama: bool = False) -> RuntimeCheckResult:
    result = RuntimeCheckResult()

    # Python version
    result.python_ok, result.python_version = _check_python()
    if not result.python_ok:
        result.errors.append(f"Python 3.11+ required; found {result.python_version}")

    # Module availability
    result.dependencies = _check_modules()

    # Optional missing
    for dep in result.dependencies:
        if not dep.available and not dep.critical:
            result.warnings.append(
                f"{dep.name} is not installed — related features will be disabled."
            )

    # Ollama
    exe = _find_ollama_executable()
    result.ollama.installed = bool(exe)
    result.ollama.executable = exe
    result.ollama.model_dir = _get_model_dir()

    if exe:
        result.ollama.api_online = _check_ollama_api()
        if result.ollama.api_online:
            result.ollama.models_found = _list_ollama_models(exe)
        result.ollama.missing_models = [
            m for m in result.ollama.required_models
            if not any(
                found == m or found.startswith(m + ":") or found.split(":")[0] == m.split(":")[0]
                for found in result.ollama.models_found
            )
        ]
    else:
        result.ollama.error = (
            "Ollama is not installed. Download from https://ollama.com and install it, "
            "then run: ollama pull qwen2.5:3b"
        )
        result.warnings.append("Ollama not found — AI planning and chat require Ollama.")

    if not result.ollama.api_online:
        result.warnings.append(
            "Ollama API is not reachable on 127.0.0.1:11434. "
            "Start Ollama before using AI features."
        )

    if result.ollama.missing_models:
        for m in result.ollama.missing_models:
            result.warnings.append(f"Ollama model '{m}' not found — run: ollama pull {m}")

    # User data directory
    result.user_data_dir = _ensure_user_data_dir()

    # Launch decision — only hard Python + critical deps block startup
    critical_missing = [d for d in result.dependencies if not d.available and d.critical]
    result.can_launch = result.python_ok and not critical_missing
    if require_ollama and not result.ollama.api_online:
        result.can_launch = False

    return result


if __name__ == "__main__":
    r = run_checks()
    print(r.summary())
    sys.exit(0 if r.can_launch else 1)
