"""Transport-byte keyboard and defensive Telnet/IAC decoding."""

from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ansiradar.transport import (
    InteractiveTransport,
    TransportDisconnected,
    TransportError,
)

MAX_ESCAPE_BYTES = 16
MAX_TELNET_BYTES = 256


class InputDisconnected(Exception):
    """The remote input channel reached EOF or failed."""


class InputDebugSink(Protocol):
    def raw(self, data: bytes) -> None: ...

    def key(self, value: str) -> None: ...


class KeyDecoder:
    """Decode common ANSI/BBS keys without depending on termios or TTYs."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._ready: deque[str] = deque()

    def feed(self, data: bytes) -> list[str]:
        self._buffer.extend(data)
        decoded = self._parse()
        self._ready.extend(decoded)
        return decoded

    def pop_key(self) -> str | None:
        return self._ready.popleft() if self._ready else None

    def pending_escape(self) -> bool:
        return bool(self._buffer and self._buffer[0] == 0x1B)

    def flush_escape(self) -> str | None:
        if self.pending_escape():
            self._buffer.clear()
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
    debug: InputDebugSink | None = None,
) -> str | None:
    """Read one decoded key, returning None on timeout and raising on EOF."""
    key = decoder.pop_key()
    if key is not None:
        if debug is not None:
            debug.key(key)
        return key
    try:
        data = transport.read(64, timeout)
    except TransportDisconnected as error:
        raise InputDisconnected(str(error)) from error
    except TransportError as error:
        raise InputTransportError(str(error)) from error
    if not data:
        if not transport.is_connected():
            raise InputDisconnected("remote connection closed")
        if decoder.pending_escape():
            try:
                more = transport.read(64, min(max(timeout, 0.0), 0.05))
            except TransportDisconnected as error:
                raise InputDisconnected(str(error)) from error
            except TransportError as error:
                raise InputTransportError(str(error)) from error
            if more:
                if debug is not None:
                    debug.raw(more)
                decoder.feed(more)
                key = decoder.pop_key()
                if key is not None:
                    if debug is not None:
                        debug.key(key)
                    return key
            key = decoder.flush_escape()
            if key is not None and debug is not None:
                debug.key(key)
            return key
        return None
    if debug is not None:
        debug.raw(data)
    decoder.feed(data)
    key = decoder.pop_key()
    if key is not None and debug is not None:
        debug.key(key)
    return key


class InputTransportError(Exception):
    """An unexpected transport error, distinct from a remote disconnect."""


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


class InputDebugLog:
    """Best-effort bounded append log for door input diagnostics."""

    MAX_BYTES = 1024 * 1024

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._handle = None
        try:
            if self.path.exists() and self.path.stat().st_size >= self.MAX_BYTES:
                self._handle = self.path.open("w", encoding="ascii")
            else:
                self._handle = self.path.open("a", encoding="ascii")
        except OSError:
            self._handle = None

    def raw(self, data: bytes) -> None:
        self._write(f"raw={data.hex()}\n")

    def key(self, value: str) -> None:
        self._write(f"key={value!r}\n")

    def exit(self, reason: str) -> None:
        self._write(f"exit={reason!r}\n")

    def event(self, message: str) -> None:
        self._write(f"event={message}\n")

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None

    def _write(self, line: str) -> None:
        if self._handle is None:
            return
        try:
            if self._handle.tell() + len(line.encode("ascii")) > self.MAX_BYTES:
                self._handle.close()
                self._handle = None
                return
            self._handle.write(line)
            self._handle.flush()
        except OSError:
            self.close()
