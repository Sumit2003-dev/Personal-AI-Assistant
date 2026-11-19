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


class ModelUnavailableError(RuntimeError):
    """Raised when a requested LLM model is not available in the inference runtime."""
    pass


def resolve_ollama_model(requested: str, available: List[str]) -> Optional[str]:
    """
    Resolves a requested Ollama model string against the list of available models.
    Matching rules:
      1. Exact match (case-sensitive)
      2. Exact match (case-insensitive)
      3. Tag normalisation (:latest omitted or explicit):
         - If requested is 'qwen3:4b', matches 'qwen3:4b:latest' or 'qwen3:4b'
         - If requested ends with ':latest', matches without ':latest'
         - If requested has no tag (e.g. 'qwen3'), matches 'qwen3:latest'
      4. Strict tag/size preservation:
         - If requested has a specific size (e.g. '3b' or '4b'), it NEVER matches a different size (e.g. '7b' or '14b').
      5. Returns None if no safe match found. NEVER falls back to arbitrary available[0].
    """
    if not requested or not available:
        return None

    # 1. Exact match
    if requested in available:
        return requested

    # 2. Case-insensitive exact match
    req_lower = requested.lower()
    for m in available:
        if m.lower() == req_lower:
            return m

    # 3. Handle :latest suffix variations
    if ":" not in requested:
        target_latest = f"{req_lower}:latest"
        for m in available:
            if m.lower() == target_latest:
                return m
    else:
        if req_lower.endswith(":latest"):
            stripped = req_lower[:-7]
            for m in available:
                if m.lower() == stripped:
                    return m
        else:
            with_latest = f"{req_lower}:latest"
            for m in available:
                if m.lower() == with_latest:
                    return m

    # 4. Strict family & size prefix match
    if ":" in requested:
        req_family, req_tag = requested.split(":", 1)
        req_family_lower = req_family.lower()
        req_tag_lower = req_tag.lower()
        for m in available:
            if ":" in m:
                cand_family, cand_tag = m.split(":", 1)
                if cand_family.lower() == req_family_lower:
                    if cand_tag.lower() == req_tag_lower:
                        return m
                    if cand_tag.lower().startswith(req_tag_lower + "-") or cand_tag.lower().startswith(req_tag_lower + "_"):
                        return m
    else:
        for m in available:
            if ":" in m:
                cand_family, cand_tag = m.split(":", 1)
                if cand_family.lower() == req_lower and cand_tag.lower() == "latest":
                    return m

    return None


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
        if available:
            resolved = resolve_ollama_model(target_model, available)
            if not resolved:
                raise ModelUnavailableError(
                    f"Requested model '{target_model}' is not available in Ollama. "
                    f"Available models: {available}. Please run 'ollama pull {target_model}'."
                )
            target_model = resolved

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
        resolved_model = resolve_ollama_model(self.ollama.model, models) if (online and models) else None
        model_downloaded = resolved_model is not None
        effective_model = resolved_model or self.ollama.model
        return {
            "ollama_online": online,
            "ollama_host": self.ollama.host,
            "configured_model": self.ollama.model,
            "resolved_model": effective_model,
            "model_downloaded": model_downloaded,
            "available_models": models,
            "status": "ONLINE" if (online and model_downloaded) else "UNAVAILABLE",
            "message": (
                f"Ollama connected with model '{effective_model}'"
                if (online and model_downloaded)
                else f"Local LLM inference runtime is UNAVAILABLE. Ollama is offline or '{self.ollama.model}' is not downloaded."
            ),
        }

    def generate_plan(
        self,
        objective: str,
        tools_schema: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[tuple[str, str]]:
        """Requests a task plan from the local LLM if online. Returns (raw_plan, model_name)."""
        if not self.is_available():
            logger.warning("Cannot generate LLM plan: Ollama is offline.")
            return None

        available = self.ollama.list_available_models()
        # Prefer fast instruction model for structured JSON decomposition
        preferred_planning = "qwen2.5:3b"
        planning_model = resolve_ollama_model(preferred_planning, available)
        if not planning_model:
            planning_model = resolve_ollama_model(self.ollama.model, available)

        if not planning_model:
            logger.warning("Cannot generate LLM plan: Neither fast model nor configured model found in available models.")
            return None

        tool_names = [t["name"] for t in tools_schema]

        context_blocks = []
        if context:
            if context.get("retrieved_memories"):
                m_lines = [f"- {m.get('key')}: {m.get('value')}" for m in context["retrieved_memories"][:5]]
                context_blocks.append("Stored Preferences & Context:\n" + "\n".join(m_lines))
            if context.get("recent_history"):
                h_lines = [f"- {msg.get('role')}: {msg.get('content')}" for msg in context["recent_history"][-3:]]
                context_blocks.append("Recent Conversation History:\n" + "\n".join(h_lines))

        ctx_prompt = ("\n\n" + "\n\n".join(context_blocks)) if context_blocks else ""

        prompt = (
            f"Objective: {objective}\n"
            f"{ctx_prompt}\n"
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

    def generate_chat_reply(
        self,
        message: str | List[Dict[str, Any]],
        history: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        """Generates a direct conversational response using the local model."""
        if not self.is_available():
            return None

        if isinstance(message, list):
            user_msg = ""
            extracted_history = []
            for item in message:
                if isinstance(item, dict):
                    if item.get("role") == "user":
                        user_msg = item.get("content", "")
                    extracted_history.append(item)
            message = user_msg or (message[-1].get("content", "") if message and isinstance(message[-1], dict) else str(message))
            if not history and len(extracted_history) > 1:
                history = extracted_history[:-1]
        available = self.ollama.list_available_models()
        preferred_chat = "qwen2.5:3b"
        chat_model = resolve_ollama_model(preferred_chat, available)
        if not chat_model:
            chat_model = resolve_ollama_model(self.ollama.model, available)

        if not chat_model:
            logger.warning("Cannot generate chat reply: Configured model not found in available models.")
            return None

        context_lines = []
        if memories:
            m_items = [f"- {m.get('key')}: {m.get('value')}" for m in memories[:5]]
            context_lines.append("User Memory & Context:\n" + "\n".join(m_items))
        if history:
            h_items = [f"{m.get('role').capitalize()}: {m.get('content')}" for m in history[-4:]]
            context_lines.append("Recent Conversation:\n" + "\n".join(h_items))

        prompt_body = "\n\n".join(context_lines) + f"\n\nUser: {message}\nAssistant:" if context_lines else message
        system_prompt = (
            "You are SAM, an intelligent personal AI workstation assistant for Windows 11 on an HP OMEN 16. "
            "Provide helpful, concise, professional assistance."
        )
        try:
            return self.ollama.generate(prompt_body, system_prompt=system_prompt, model=chat_model, max_tokens=300)
        except Exception as e:
            logger.error(f"Chat generation failed: {e}")
            return None


model_manager = ModelManager()
