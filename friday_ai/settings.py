import json
import os
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from .llm import PROVIDER_DEFAULTS


class FridaySettings:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.values: Dict[str, str] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self.values = {
                    key: str(value) for key, value in data.items()
                    if key in {"provider", "model"}
                }

    def public(self) -> Dict[str, Any]:
        provider = self.values.get("provider", os.getenv("FRIDAY_PROVIDER", "ollama"))
        model = self.values.get("model", os.getenv("FRIDAY_MODEL", PROVIDER_DEFAULTS.get(provider, "llama3.2")))
        configured = {
            "ollama": True,
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "google": bool(os.getenv("GOOGLE_API_KEY")),
            "openai-compatible": True,
        }
        compatible_url = os.getenv("FRIDAY_API_BASE", "http://127.0.0.1:1234/v1")
        compatible_host = (urlparse(compatible_url).hostname or "").lower()
        compatible_is_local = compatible_host in {"localhost", "127.0.0.1", "::1"}
        return {
            "provider": provider,
            "model": model,
            "providers": [
                {"id": name, "model": default, "configured": configured[name]}
                for name, default in PROVIDER_DEFAULTS.items()
            ],
            "cloud_provider_active": (
                provider in {"openai", "anthropic", "google"}
                or (provider == "openai-compatible" and not compatible_is_local)
            ),
            "provider_endpoint": compatible_url if provider == "openai-compatible" else None,
        }

    def update(self, provider: str, model: str | None = None) -> Dict[str, Any]:
        if provider not in PROVIDER_DEFAULTS:
            raise ValueError("Unsupported provider.")
        if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Set OPENAI_API_KEY before selecting OpenAI.")
        if provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("Set ANTHROPIC_API_KEY before selecting Anthropic.")
        if provider == "google" and not os.getenv("GOOGLE_API_KEY"):
            raise ValueError("Set GOOGLE_API_KEY before selecting Google.")
        selected_model = (model or PROVIDER_DEFAULTS[provider]).strip()
        if not selected_model or len(selected_model) > 160:
            raise ValueError("Model name must be between 1 and 160 characters.")
        self.values = {"provider": provider, "model": selected_model}
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return self.public()
