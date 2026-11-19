"""
SAM - Configuration & Hardware Specification Settings
Optimized for HP OMEN 16, Windows 11, NVIDIA RTX 4050 6GB VRAM, 16GB RAM.
"""

from dataclasses import dataclass, field
from pathlib import Path
import os
import sys

# Root directories
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

SAM_DIR = BASE_DIR / "sam"


def _resolve_runtime_data_dir() -> Path:
    env_root = os.environ.get("SAM_DATA_ROOT")
    if env_root:
        p = Path(env_root) / "data"
    elif getattr(sys, "frozen", False):
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM" / "data"
    else:
        p = SAM_DIR / "data"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        p = SAM_DIR / "data"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            pass
    return p


def _resolve_runtime_logs_dir() -> Path:
    env_root = os.environ.get("SAM_DATA_ROOT")
    if env_root:
        p = Path(env_root) / "logs"
    elif getattr(sys, "frozen", False):
        p = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM" / "logs"
    else:
        p = SAM_DIR / "logs"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        p = SAM_DIR / "logs"
        try:
            p.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            pass
    return p


DATA_DIR = _resolve_runtime_data_dir()
LOGS_DIR = _resolve_runtime_logs_dir()
TESTS_DIR = SAM_DIR / "tests"
STATIC_DIR = SAM_DIR / "desktop" / "static"
TEMPLATES_DIR = SAM_DIR / "desktop" / "templates"


@dataclass
class HardwareConfig:
    device_name: str = "HP OMEN 16"
    os_name: str = "Windows 11"
    gpu_name: str = "NVIDIA GeForce RTX 4050 Laptop GPU"
    total_vram_mb: int = 6144
    safe_vram_limit_mb: int = 5000  # Avoid OOM on 6GB VRAM
    system_ram_gb: int = 16
    driver_version: str = "621.24"
    max_concurrent_llms: int = 1  # Avoid loading multiple simultaneous LLMs into 6GB VRAM


@dataclass
class ModelConfig:
    ollama_host: str = os.getenv("SAM_OLLAMA_HOST", "http://127.0.0.1:11434")
    primary_model: str = os.getenv("SAM_PRIMARY_MODEL", "qwen3:4b")
    fallback_model: str = os.getenv("SAM_FALLBACK_MODEL", "qwen2.5:3b")
    temperature: float = 0.2
    max_tokens: int = 2048
    context_window: int = 4096
    cloud_enabled: bool = False  # Cloud LLMs strictly disabled by default
    cloud_provider: str = "none"


@dataclass
class SecurityConfig:
    strict_permissions: bool = True
    require_confirmation_high_risk: bool = True
    require_confirmation_medium_risk: bool = False  # Logged and gated
    allowlisted_folders: list[str] = field(default_factory=lambda: [
        str(BASE_DIR),
        str(Path.home() / "Desktop"),
        str(Path.home() / "Documents"),
        str(Path.home() / "Downloads"),
    ])
    audit_log_path: Path = LOGS_DIR / "audit.jsonl"
    emergency_stop_triggered: bool = False


@dataclass
class VoiceConfig:
    wake_phrase: str = "Hey SAM"
    wake_word_enabled: bool = False  # Default to push-to-talk for safety
    sample_rate: int = 16000
    stt_model: str = "faster-whisper-tiny.en"  # Low VRAM footprint
    tts_engine: str = "local"
    push_to_talk_key: str = "ctrl+space"
    preferred_device_name: str = "boAt Airdopes 131"
    silence_rms_threshold: float = 0.008
    min_peak_amplitude: float = 0.025
    clipping_threshold: float = 0.99
    max_no_speech_prob: float = 0.45
    min_avg_logprob: float = -1.1


@dataclass
class DesktopConfig:
    theme: str = "dark_futuristic"
    window_title: str = "SAM // Autonomous AI Computer Operator"
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    refresh_rate_hz: int = 30
    screenshot_capture_interval_s: float = 1.0


@dataclass
class Settings:
    hardware: HardwareConfig = field(default_factory=HardwareConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    desktop: DesktopConfig = field(default_factory=DesktopConfig)
    base_dir: Path = BASE_DIR
    data_dir: Path = DATA_DIR
    logs_dir: Path = LOGS_DIR


# Global singleton instance
settings = Settings()

