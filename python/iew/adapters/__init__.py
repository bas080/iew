"""Provider adapters module."""
from .base import BaseAdapter
from .ollama import OllamaAdapter
from .openrouter import OpenRouterAdapter

ADAPTERS = {
    "ollama": OllamaAdapter,
    "openrouter": OpenRouterAdapter,
}


def get_adapter(config: dict) -> BaseAdapter:
    """Factory function returning the adapter for the configured provider."""
    provider = config.get("provider", "ollama")
    adapter_cls = ADAPTERS.get(provider.lower())
    if not adapter_cls:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {', '.join(ADAPTERS.keys())}")
    return adapter_cls(config)


__all__ = [
    "BaseAdapter",
    "OllamaAdapter",
    "OpenRouterAdapter",
    "get_adapter",
]
