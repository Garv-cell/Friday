import json
import os
import urllib.error
import urllib.request
from typing import Optional

from .config import DEFAULT_MODEL, OLLAMA_URL


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = OLLAMA_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str) -> Optional[str]:
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise RuntimeError("Ollama returned an invalid response.")
                text = result.get("response")
                if not isinstance(text, str):
                    raise RuntimeError("Ollama returned a response without text.")
                return text.strip() or None
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc


PROVIDER_DEFAULTS = {
    "ollama": DEFAULT_MODEL,
    "openai": "gpt-6-astra",
    "anthropic": "claude-3-5-haiku-latest",
    "google": "gemini-2.0-flash",
    "openai-compatible": "local-model",
}


class ModelClient:
    def __init__(self, provider: str = "ollama", model: Optional[str] = None):
        if provider not in PROVIDER_DEFAULTS:
            raise ValueError(f"Unsupported model provider: {provider}")
        self.provider = provider
        self.model = model or PROVIDER_DEFAULTS[provider]

    def generate(self, prompt: str) -> Optional[str]:
        if self.provider == "ollama":
            return OllamaClient(self.model).generate(prompt)
        if self.provider == "openai":
            return self._openai(
                "https://api.openai.com/v1/chat/completions",
                os.getenv("OPENAI_API_KEY"),
                prompt,
            )
        if self.provider == "openai-compatible":
            base_url = os.getenv("FRIDAY_API_BASE", "http://127.0.0.1:1234/v1").rstrip("/")
            return self._openai(
                f"{base_url}/chat/completions",
                os.getenv("FRIDAY_API_KEY"),
                prompt,
            )
        if self.provider == "anthropic":
            return self._anthropic(prompt)
        return self._google(prompt)

    def _post_json(self, url: str, payload: dict, headers: dict) -> dict:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Model provider returned an invalid response.")
        return data

    def _openai(self, url: str, api_key: Optional[str], prompt: str) -> Optional[str]:
        if not api_key and self.provider != "openai-compatible":
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        data = self._post_json(url, {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }, headers)
        choices = data.get("choices")
        if not choices or not isinstance(choices[0], dict):
            raise RuntimeError("OpenAI-compatible provider returned no completion choices.")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise RuntimeError("OpenAI-compatible provider returned an invalid message.")
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("OpenAI-compatible provider returned an invalid message.")
        return content.strip() or None

    def _anthropic(self, prompt: str) -> Optional[str]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured.")
        data = self._post_json(
            "https://api.anthropic.com/v1/messages",
            {"model": self.model, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]},
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        return "".join(
            item.get("text", "") for item in data.get("content", [])
            if item.get("type") == "text"
        ).strip()

    def _google(self, prompt: str) -> Optional[str]:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is not configured.")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        data = self._post_json(url, {
            "contents": [{"parts": [{"text": prompt}]}],
        }, {"x-goog-api-key": api_key})
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        return "".join(
            part.get("text", "") for part in candidates[0].get("content", {}).get("parts", [])
        ).strip()
