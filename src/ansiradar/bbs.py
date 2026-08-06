"""BBS terminal profile and explicit caller-output encoding policy."""

from dataclasses import dataclass

from ansiradar.sanity import sanitize_text
from ansiradar.transport import InteractiveTransport


@dataclass(frozen=True, slots=True)
class BBSTerminalProfile:
    width: int = 80
    height: int = 24
    charset: str = "cp437"
    color: bool = True
    newline: bytes = b"\r\n"

    def __post_init__(self) -> None:
        if not 20 <= self.width <= 240:
            raise ValueError("BBS width must be between 20 and 240")
        if not 10 <= self.height <= 100:
            raise ValueError("BBS height must be between 10 and 100")
        if self.charset not in {"ascii", "cp437", "unicode"}:
            raise ValueError("unsupported BBS charset")

    def encode(self, text: str) -> bytes:
        safe = sanitize_text(text, limit=64 * 1024)
        if self.charset == "cp437":
            return safe.encode("cp437", "replace")
        if self.charset == "ascii":
            return safe.encode("ascii", "replace")
        return safe.encode("utf-8", "replace")

    def trusted_encode(self, ansi_text: str) -> bytes:
        """Encode renderer-owned ANSI text without sanitizing escape sequences."""
        ansi_text = ansi_text.replace("\r\n", "\n").replace("\n", "\r\n")
        if self.charset == "cp437":
            return ansi_text.encode("cp437", "replace")
        if self.charset == "ascii":
            return ansi_text.encode("ascii", "replace")
        return ansi_text.encode("utf-8", "replace")

    def startup(self) -> bytes:
        return b"\x1b[2J\x1b[H\x1b[?25l"

    def shutdown(self, *, clear: bool = True) -> bytes:
        suffix = b"\x1b[2J\x1b[H" if clear else b""
        return b"\x1b[0m\x1b[?25h" + suffix


def write_profile(transport: InteractiveTransport, data: bytes) -> None:
    transport.write(data)
    transport.flush()
