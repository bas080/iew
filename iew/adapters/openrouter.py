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
        api_key = (
            self.config.get("api_key")
            or self.config.get("key")
            or self.config.get("openrouter_key")
            or os.environ.get("OPENROUTER_API_KEY")
        )
        if not api_key:
            LOGGER.error("API key missing: set api_key in config or OPENROUTER_API_KEY env")
            raise ValueError("OpenRouter API key missing")

        # Sane defaults for OpenRouter request
        payload = {
            "model": "deepseek/deepseek-chat-v3-0324:free",
            "temperature": 0.0,
        }

        # Merge user's configured request dictionary as-is
        user_request = self.config.get("request", {})
        if isinstance(user_request, dict):
            payload.update({k: v for k, v in user_request.items() if v is not None})

        # Ensure header credentials or prompt templates are never sent in the JSON body
        payload.pop("api_key", None)
        payload.pop("key", None)
        payload.pop("openrouter_key", None)
        payload.pop("prompt", None)

        # Thinking / reasoning mode mapping
        if "thinking" in payload:
            thinking = payload.pop("thinking")
            if "reasoning" not in payload and thinking is not None:
                if isinstance(thinking, bool):
                    payload["reasoning"] = {"effort": "medium"} if thinking else {"effort": "none"}
                elif isinstance(thinking, str):
                    payload["reasoning"] = {"effort": thinking}
                elif isinstance(thinking, int):
                    payload["reasoning"] = {"max_tokens": thinking}
                elif isinstance(thinking, dict):
                    payload["reasoning"] = thinking

        # Set or append messages
        if "messages" in payload and isinstance(payload["messages"], list):
            payload["messages"] = list(payload["messages"]) + [{"role": "user", "content": prompt}]
        else:
            payload["messages"] = [{"role": "user", "content": prompt}]

        LOGGER.info("Using OpenRouter model: %s", payload.get("model"))

        timeout = float(self.config.get("timeout", 180))
        LOGGER.info("Using timeout: %s", timeout)

        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
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
                    msg = choices[0]["message"] if choices and "message" in choices[0] else {}
                    reasoning_trace = msg.get("reasoning") or msg.get("reasoning_content")
                    if reasoning_trace:
                        LOGGER.info("OpenRouter reasoning trace: %s", reasoning_trace[:500])
                    if msg and "content" in msg:
                        output = msg["content"]
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
