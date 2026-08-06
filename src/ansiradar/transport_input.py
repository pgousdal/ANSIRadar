"""Transport-byte keyboard and defensive Telnet/IAC decoding."""

from collections.abc import Iterable

from ansiradar.transport import InteractiveTransport, TransportError

MAX_ESCAPE_BYTES = 16
MAX_TELNET_BYTES = 256


class InputDisconnected(Exception):
    """The remote input channel reached EOF or failed."""


class KeyDecoder:
    """Decode common ANSI/BBS keys without depending on termios or TTYs."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._telnet = bytearray()

    def feed(self, data: bytes) -> list[str]:
        self._buffer.extend(data)
        return self._parse()

    def pending_escape(self) -> bool:
        return bool(self._buffer and self._buffer[0] == 0x1B)

    def flush_escape(self) -> str | None:
        if self.pending_escape():
            del self._buffer[0]
            return "\x1b"
        return None

    def _parse(self) -> list[str]:
        keys: list[str] = []
        while self._buffer:
            if self._buffer[0] == 0xFF:
                if not self._strip_iac():
                    break
                continue
            if self._buffer[0] != 0x1B:
                value = self._buffer.pop(0)
                if value in (10, 13):
                    keys.append("ENTER")
                elif 32 <= value <= 126:
                    keys.append(chr(value))
                continue
            key = self._escape_key()
            if key is None:
                break
            if key:
                keys.append(key)
        return keys

    def _escape_key(self) -> str | None:
        if len(self._buffer) == 1:
            return None
        if self._buffer[1] in (10, 13):
            del self._buffer[:2]
            return "\x1b"
        if self._buffer[1] != ord("["):
            del self._buffer[0]
            return "\x1b"
        if len(self._buffer) > MAX_ESCAPE_BYTES:
            end = next(
                (
                    index
                    for index, value in enumerate(self._buffer[2:], start=2)
                    if 0x40 <= value <= 0x7E
                ),
                None,
            )
            if end is None:
                self._buffer.clear()
            else:
                del self._buffer[: end + 1]
            return "\x1b"
        end = None
        for index in range(2, len(self._buffer)):
            if 0x40 <= self._buffer[index] <= 0x7E:
                end = index
                break
        if end is None:
            return None
        sequence = bytes(self._buffer[: end + 1])
        del self._buffer[: end + 1]
        return {
            b"\x1b[A": "UP",
            b"\x1b[B": "DOWN",
            b"\x1b[C": "RIGHT",
            b"\x1b[D": "LEFT",
            b"\x1bOA": "UP",
            b"\x1bOB": "DOWN",
            b"\x1bOC": "RIGHT",
            b"\x1bOD": "LEFT",
        }.get(sequence)

    def _strip_iac(self) -> bool:
        if len(self._buffer) < 2:
            return False
        command = self._buffer[1]
        if command == 0xFF:
            del self._buffer[:2]
            return True
        if command == 250:  # SB: consume through IAC SE, bounded.
            end = self._buffer.find(b"\xff\xf0", 2, MAX_TELNET_BYTES + 2)
            if end < 0:
                if len(self._buffer) > MAX_TELNET_BYTES:
                    del self._buffer[:1]
                    return True
                return False
            del self._buffer[: end + 2]
            return True
        if command in (251, 252, 253, 254):
            if len(self._buffer) < 3:
                return False
            del self._buffer[:3]
            return True
        del self._buffer[:2]
        return True


def read_key(
    transport: InteractiveTransport,
    decoder: KeyDecoder,
    *,
    timeout: float,
) -> str | None:
    """Read one decoded key, returning None on timeout and raising on EOF."""
    keys = decoder._parse()
    if keys:
        return keys[0]
    try:
        data = transport.read(64, timeout)
    except TransportError as error:
        raise InputDisconnected(str(error)) from error
    if not data:
        if not transport.is_connected():
            raise InputDisconnected("remote connection closed")
        if decoder.pending_escape():
            return decoder.flush_escape()
        return None
    keys = decoder.feed(data)
    return keys[0] if keys else None


def decode_bytes(chunks: Iterable[bytes]) -> list[str]:
    """Deterministically decode chunks, flushing a final standalone Escape."""
    decoder = KeyDecoder()
    result: list[str] = []
    for chunk in chunks:
        result.extend(decoder.feed(chunk))
    final = decoder.flush_escape()
    if final is not None:
        result.append(final)
    return result
