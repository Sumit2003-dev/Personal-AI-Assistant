r"""
SAM Configuration Manager — persistent user preferences
Reads/writes a JSON config from %APPDATA%\SAM\config\sam_config.json.
Never overwrites existing user values — only fills missing keys.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

import tempfile

logger = logging.getLogger("sam.launcher.config_manager")

def _resolve_config_dir() -> Path:
    env_root = os.environ.get("SAM_DATA_ROOT")
    if env_root:
        base = Path(env_root) / "config"
    else:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "SAM" / "config"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError):
        base = Path(tempfile.gettempdir()) / "SAM" / "config"
        base.mkdir(parents=True, exist_ok=True)
    return base

_CONFIG_DIR = _resolve_config_dir()
_CONFIG_FILE = _CONFIG_DIR / "sam_config.json"
_BACKUP_FILE = _CONFIG_DIR / "sam_config.backup.json"


@dataclass
class SAMUserConfig:
    """
    Persistent user preferences.  Schema version is bumped when new
    required keys are added so migrate() can fill defaults safely.
    """
    schema_version: int = 2
    ui_host: str = "127.0.0.1"
    ui_port: int = 8765
    ollama_host: str = "http://127.0.0.1:11434"
    primary_model: str = "qwen3:4b"
    fallback_model: str = "qwen2.5:3b"
    ollama_models_dir: str = "D:/Ollama/models"
    whisper_models_dir: str = "D:/Whisper/models"
    preferred_mic: str = "boAt Airdopes 131"
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    open_browser_on_start: bool = True
    theme: str = "dark_futuristic"
    app_version: str = "7.0.0"
    extra: Dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """
    Load, save, migrate, and backup user configuration.
    Thread-safe single-writer via atomic rename pattern.
    """

    def __init__(self):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._config: SAMUserConfig = self._load()

    # ------------------------------------------------------------------
    @property
    def config(self) -> SAMUserConfig:
        return self._config

    # ------------------------------------------------------------------
    def _load(self) -> SAMUserConfig:
        if not _CONFIG_FILE.exists():
            cfg = SAMUserConfig()
            self._save(cfg)
            logger.info("Created default config: %s", _CONFIG_FILE)
            return cfg

        try:
            raw = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            cfg = self._migrate(raw)
            logger.info("Loaded config v%d from %s", cfg.schema_version, _CONFIG_FILE)
            return cfg
        except Exception as exc:
            logger.error("Failed to load config (%s) — using defaults.", exc)
            return SAMUserConfig()

    def _migrate(self, raw: dict) -> SAMUserConfig:
        """
        Fill any keys missing from older config files without touching
        keys the user has already set.
        """
        defaults = asdict(SAMUserConfig())
        merged = {**defaults, **{k: v for k, v in raw.items() if k in defaults}}
        # Bump schema version
        merged["schema_version"] = defaults["schema_version"]
        return SAMUserConfig(**{k: merged[k] for k in defaults if k != "extra"},
                             extra=raw.get("extra", {}))

    def _save(self, cfg: SAMUserConfig) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _CONFIG_FILE.with_suffix(".tmp")
        data = asdict(cfg)
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Atomic rename
        if _CONFIG_FILE.exists():
            _BACKUP_FILE.write_bytes(_CONFIG_FILE.read_bytes())
        tmp.replace(_CONFIG_FILE)

    def save(self) -> None:
        try:
            self._save(self._config)
            logger.debug("Config saved.")
        except Exception as exc:
            logger.error("Failed to save config: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self._config, key, default)

    def set(self, key: str, value: Any) -> None:
        if hasattr(self._config, key):
            setattr(self._config, key, value)
            self.save()
        else:
            self._config.extra[key] = value
            self.save()

    def restore_from_backup(self) -> bool:
        if _BACKUP_FILE.exists():
            _CONFIG_FILE.write_bytes(_BACKUP_FILE.read_bytes())
            self._config = self._load()
            logger.info("Config restored from backup.")
            return True
        return False


# Global singleton
config_manager = ConfigManager()
