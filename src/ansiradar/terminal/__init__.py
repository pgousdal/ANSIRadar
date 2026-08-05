"""Small standard-library terminal abstraction."""

from ansiradar.terminal.capabilities import TerminalCapabilities, resolve_capabilities
from ansiradar.terminal.session import TerminalSession

__all__ = ["TerminalCapabilities", "TerminalSession", "resolve_capabilities"]
