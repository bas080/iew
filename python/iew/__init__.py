"""iew - AI code review tool."""

from .agent import Agent
from .format import parse_coordinate
from .lsp_server import SimpleLSP

# IewLSP alias for backward compatibility
class IewLSP(SimpleLSP):
    """IewLSP is the main LSP class for the iew tool."""
    pass

__all__ = ["Agent", "parse_coordinate", "IewLSP", "SimpleLSP"]