"""Ollama adapter for local model inference."""
import json
import logging
import subprocess

from .base import BaseAdapter

LOGGER = logging.getLogger(__name__)


class OllamaAdapter(BaseAdapter):
    """Adapter for interacting with local Ollama instance."""

    name = "ollama"

    def complete(self, prompt: str) -> str:
        model = self.config.get("ollama_model") or self.config.get("model", "llama3")
        LOGGER.info("Using Ollama model: %s", model)

        timeout = float(self.config.get("timeout") or self.config.get("ollama_timeout", 180))
        LOGGER.info("Using timeout: %s", timeout)

        keep_alive = self.config.get("keep_alive", "30m")
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if keep_alive is not None:
            payload["keep_alive"] = keep_alive

        response = subprocess.run(
            ["curl", "-s", "-X", "POST", "http://localhost:11434/api/generate",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout
        )

        if response.returncode == 0:
            data = json.loads(response.stdout)
            output = data.get("response", "")
            LOGGER.info("Ollama response received (%d chars)", len(output))
            LOGGER.info("Ollama raw response: %s", output[:500])
            return output
        else:
            LOGGER.error("Ollama API error: %s", response.stderr)
            raise RuntimeError(f"Ollama API error: {response.stderr}")
