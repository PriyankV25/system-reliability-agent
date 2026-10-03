from __future__ import annotations

import json
import urllib.error
import urllib.request

from ai_config import load_config


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None, model: str | None = None,
                 timeout: int | None = None):
        config = load_config()["ollama"]
        self.base_url = (base_url or config["base_url"]).rstrip("/")
        self.model = model or config["model"]
        self.timeout = int(timeout or config["timeout_seconds"])

    def health(self) -> dict:
        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", [])]
            return {"ok": True, "model": self.model, "models": models}
        except Exception as exc:
            return {"ok": False, "model": self.model, "error": str(exc), "models": []}

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        if tools:
            payload["tools"] = tools

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. Start Ollama and verify the model is installed."
            ) from exc
        except Exception as exc:
            raise OllamaError(str(exc)) from exc
