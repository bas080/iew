"""OpenRouter adapter for hosted model inference."""
import json
import logging
import os
import time
import urllib.error
import urllib.request

from .base import BaseAdapter

LOGGER = logging.getLogger(__name__)


class OpenRouterAdapter(BaseAdapter):
    """Adapter for interacting with OpenRouter API."""

    name = "openrouter"

    def complete(self, prompt: str) -> str:
        openrouter_key = self.config.get("openrouter_key") or os.environ.get("OPENROUTER_API_KEY")
        if not openrouter_key:
            LOGGER.error("OpenRouter API key missing: set openrouter_key in iew.toml or OPENROUTER_API_KEY env")
            raise ValueError("OpenRouter API key missing")

        openrouter_model = (
            self.config.get("openrouter_model")
            or self.config.get("model")
            or "deepseek/deepseek-chat-v3-0324:free"
        )
        LOGGER.info("Using OpenRouter model: %s", openrouter_model)

        timeout = float(self.config.get("timeout") or self.config.get("ollama_timeout", 180))
        LOGGER.info("Using timeout: %s", timeout)

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": openrouter_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openrouter_key}",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        max_retries = int(self.config.get("max_retries", 3))
        backoff = 2
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    choices = data.get("choices", [])
                    if choices and "message" in choices[0] and "content" in choices[0]["message"]:
                        output = choices[0]["message"]["content"]
                    else:
                        output = data.get("response") or ""
                    LOGGER.info("OpenRouter response received (%d chars)", len(output))
                    LOGGER.info("OpenRouter raw response: %s", output[:500])
                    return output
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < max_retries - 1:
                    wait = backoff * (2 ** attempt)
                    LOGGER.warning("OpenRouter rate limit (429), retrying in %ds...", wait)
                    time.sleep(wait)
                    continue
                LOGGER.error("OpenRouter HTTP error: %s", e)
                raise RuntimeError(f"OpenRouter HTTP error: {e}")
            except urllib.error.URLError as e:
                LOGGER.error("OpenRouter request error: %s", e)
                raise RuntimeError(f"OpenRouter request failed: {e}")
            except Exception as e:
                LOGGER.error("OpenRouter error: %s", e)
                raise

        return ""
