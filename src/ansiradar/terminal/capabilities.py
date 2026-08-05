"""Terminal capability and charset resolution."""

import os
import shutil
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TerminalCapabilities:
    width: int
    height: int
    color: bool
    charset: str


def resolve_capabilities(
    *, charset: str = "ascii", color: str = "auto", stream: object = sys.stdout
) -> TerminalCapabilities:
    size = shutil.get_terminal_size((80, 24))
    is_tty = bool(getattr(stream, "isatty", lambda: False)())
    term = os.environ.get("TERM", "")
    use_color = color == "always" or (color == "auto" and is_tty and term != "dumb")
    return TerminalCapabilities(size.columns, size.lines, use_color, charset)
