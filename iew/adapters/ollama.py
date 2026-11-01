"""Ollama adapter for local model inference."""
import json
import logging
import urllib.request
import urllib.error

from .base import BaseAdapter

LOGGER = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """Adapter for interacting with local Ollama instance."""

    name = "ollama"

    def complete(self, prompt: str) -> str:
        # Sane defaults for Ollama /api/generate
        payload = {
            "model": "llama3",
            "stream": False,
        }

        # Merge user's configured request dictionary as-is
        user_request = self.config.get("request", {})
        if isinstance(user_request, dict):
            payload.update({k: v for k, v in user_request.items() if v is not None})

        # Backwards compatibility: fallback to root model if not in request
        if "model" not in payload and "model" in self.config:
            payload["model"] = self.config["model"]

        # Support 'thinking' alias for 'think'
        if "thinking" in payload:
            thinking = payload.pop("thinking")
            if "think" not in payload and thinking is not None:
                payload["think"] = thinking

        # Set the prompt to complete
        payload["prompt"] = prompt

        LOGGER.info("Using Ollama model: %s", payload.get("model"))

        timeout = float(self.config.get("timeout", 180))
        LOGGER.info("Using timeout: %s", timeout)

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        max_retries = int(self.config.get("max_retries", 3))
        backoff = 2
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    output = data.get("response", "")
                    thinking_trace = data.get("thinking")
                    if thinking_trace:
                        LOGGER.info("Ollama thinking trace: %s", thinking_trace[:500])
                    LOGGER.info("Ollama response received (%d chars)", len(output))
                    LOGGER.info("Ollama raw response: %s", output[:500])
                    return output
            except urllib.error.HTTPError as e:
                LOGGER.error("Ollama HTTP error: %s", e)
                raise RuntimeError(f"Ollama HTTP error: {e}")
            except urllib.error.URLError as e:
                LOGGER.error("Ollama request error: %s", e)
                raise RuntimeError(f"Ollama request failed: {e}")
            except Exception as e:
                LOGGER.error("Ollama error: %s", e)
                raise

        return ""
