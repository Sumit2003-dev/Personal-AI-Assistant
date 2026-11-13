"""
SAM - Model Provider Abstraction & Local-First Intelligence
Interfaces with Ollama (qwen3:4b) on HP OMEN 16 (RTX 4050 6GB VRAM).
Transparently reports when local inference is offline without misleading simulated fallbacks.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx
import logging
from sam.config.settings import settings

logger = logging.getLogger("sam.models_provider")


class BaseModelProvider(ABC):
    """Abstract interface for LLM inference providers."""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: str = "", **kwargs: Any) -> str:
        """Generate a single text response synchronously."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider endpoint and model are ready."""
        pass


class OllamaProvider(BaseModelProvider):
    """Local Ollama client for Qwen3 4B and compatible local models."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ):
        self.host = (host or settings.model.ollama_host).rstrip("/")
        self.model = model or settings.model.primary_model
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self.host}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    def list_available_models(self) -> list[str]:
        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.host}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def generate(self, prompt: str, system_prompt: str = "", **kwargs: Any) -> str:
        available = self.list_available_models()
        target_model = kwargs.get("model") or self.model
        if target_model not in available and available:
            target_model = available[0]

        payload = {
            "model": target_model,
            "prompt": prompt,
            "system": system_prompt or "You are SAM, an autonomous AI computer operator for Windows 11.",
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", settings.model.temperature),
                "num_ctx": kwargs.get("context_window", settings.model.context_window),
                "num_predict": kwargs.get("max_tokens", 400),
            }
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.host}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    response_text = data.get("response", "").strip()
                    thinking_text = data.get("thinking", "").strip()
                    return response_text or thinking_text
                else:
                    raise RuntimeError(f"Ollama error {res.status_code}: {res.text}")
        except Exception as e:
            logger.error(f"Ollama generation failed: {e}")
            raise


class ModelManager:
    """Manages the local inference runtime and provides truthful status reporting."""

    def __init__(self):
        self.ollama = OllamaProvider()

    def is_available(self) -> bool:
        return self.ollama.is_available()

    def get_status(self) -> Dict[str, Any]:
        online = self.is_available()
        models = self.ollama.list_available_models() if online else []
        model_downloaded = any(self.ollama.model in m for m in models)
        return {
            "ollama_online": online,
            "ollama_host": self.ollama.host,
            "configured_model": self.ollama.model,
            "model_downloaded": model_downloaded,
            "available_models": models,
            "status": "ONLINE" if (online and model_downloaded) else "UNAVAILABLE",
            "message": (
                f"Ollama connected with model '{self.ollama.model}'"
                if (online and model_downloaded)
                else "Local LLM inference runtime is UNAVAILABLE. Ollama is offline or qwen3:4b is not downloaded."
            ),
        }

    def generate_plan(self, objective: str, tools_schema: List[Dict[str, Any]]) -> Optional[tuple[str, str]]:
        """Requests a task plan from the local LLM if online. Returns (raw_plan, model_name)."""
        if not self.is_available():
            logger.warning("Cannot generate LLM plan: Ollama is offline.")
            return None

        available = self.ollama.list_available_models()
        # Prefer fast instruction model for structured JSON decomposition
        planning_model = "qwen2.5:3b" if any("qwen2.5:3b" in m for m in available) else self.ollama.model

        tool_names = [t["name"] for t in tools_schema]
        prompt = (
            f"Objective: {objective}\n"
            f"Available tools: {tool_names}\n"
            f"Decompose this objective into an ordered JSON list of step objects.\n"
            f"Format example:\n"
            f"[\n"
            f'  {{"title": "Step title", "description": "Details", "tool_name": "tool_name_from_list", "tool_args": {{}}, "risk_level": "LOW"}}\n'
            f"]\n"
            f"Output the JSON array now:"
        )
        system_prompt = (
            "You are SAM's task planner on Windows 11. Be concise. "
            "Output ONLY the valid JSON list of steps."
        )
        try:
            raw = self.ollama.generate(prompt, system_prompt=system_prompt, model=planning_model, max_tokens=400)
            return (raw, planning_model) if raw else None
        except Exception as e:
            logger.error(f"LLM plan generation failed: {e}")
            return None


model_manager = ModelManager()
