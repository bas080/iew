"""Base adapter interface for LLM providers."""
from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    """Abstract base class for model provider adapters."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send prompt to the provider and return model response text."""
        pass
