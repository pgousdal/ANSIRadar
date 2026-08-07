"""Transport abstractions for local terminals and Mystic door connections."""

import errno
import os
import select
import socket
import sys
from collections.abc import Callable
from typing import Protocol

from ansiradar.door import InvalidDescriptor


class TransportError(ConnectionError):
    """A transport could not read or write its connection."""


class TransportDisconnected(TransportError):
    """The peer or descriptor has definitively disconnected."""


class InteractiveTransport(Protocol):
    def read(self, size: int, timeout: float | None = None) -> bytes: ...

    def write(self, data: bytes) -> None: ...

    def flush(self) -> None: ...

    def is_connected(self) -> bool: ...

    def close(self) -> None: ...


class MemoryTransport:
    """Deterministic in-memory transport for session and parser tests."""

    def __init__(self, incoming: bytes = b"") -> None:
        self.incoming = bytearray(incoming)
        self.outgoing = bytearray()
        self.connected = True
        self.reads = 0

    def read(self, size: int, timeout: float | None = None) -> bytes:
        del timeout
        self.reads += 1
        if not self.connected:
            return b""
        if not self.incoming:
            return b""
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result

    def write(self, data: bytes) -> None:
        if not self.connected:
            raise TransportDisconnected("memory transport is disconnected")
        self.outgoing.extend(data)

    def flush(self) -> None:
        return

    def is_connected(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.connected = False


class LocalTTYTransport:
    """Byte transport over local stdin/stdout; no encoding is done here."""

    def __init__(
        self, input_stream: object = sys.stdin, output_stream: object = sys.stdout
    ):
        self.input_stream = input_stream
        self.output_stream = output_stream
        self.connected = True

    def read(self, size: int, timeout: float | None = None) -> bytes:
        fileno = _fileno(self.input_stream)
        if fileno < 0:
            return b""
        wait = timeout if timeout is not None else None
        try:
            ready, _, _ = select.select([fileno], [], [], wait)
            if not ready:
                return b""
            data = os.read(fileno, max(1, size))
        except (OSError, ValueError) as error:
            self.connected = False
            raise TransportError(str(error)) from error
        if not data:
            self.connected = False
        return data

    def write(self, data: bytes) -> None:
        target = getattr(self.output_stream, "buffer", self.output_stream)
        if not self.connected:
            raise TransportDisconnected("local transport is disconnected")
        try:
            _write_filelike(target, data)
        except (OSError, ValueError) as error:
            self.connected = False
            raise TransportError(str(error)) from error

    def flush(self) -> None:
        flush = getattr(self.output_stream, "flush", None)
        if flush is not None:
            flush()

    def is_connected(self) -> bool:
        return self.connected

    def close(self) -> None:
        self.connected = False


class DescriptorSocketTransport:
    """Transport over a descriptor supplied by DOOR32.SYS.

    The descriptor is duplicated before wrapping, so closing this transport
    never closes Mystic's original descriptor or an unrelated process handle.
    """

    def __init__(self, descriptor: int) -> None:
        if descriptor < 0:
            raise InvalidDescriptor("descriptor must be non-negative")
        try:
            duplicate = os.dup(descriptor)
            self.socket = socket.socket(fileno=duplicate)
            self.socket.setblocking(False)
            self.socket.getpeername()
        except (OSError, ValueError) as error:
            try:
                os.close(locals().get("duplicate", -1))
            except OSError:
                pass
            raise InvalidDescriptor(
                f"descriptor {descriptor} is not a connected socket: {error}"
            ) from error
        self.connected = True
        self._debug: Callable[[str], None] | None = None
        self._last_event: str | None = None

    def set_debug(self, callback: Callable[[str], None] | None) -> None:
        self._debug = callback

    def read(self, size: int, timeout: float | None = None) -> bytes:
        if not self.connected:
            return b""
        try:
            readable, _, _ = select.select([self.socket], [], [], timeout)
            if not readable:
                self._event("read_timeout")
                return b""
            data = self.socket.recv(max(1, size))
        except InterruptedError:
            self._event("read_interrupted")
            return b""
        except BlockingIOError as error:
            if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                self._event(f"read_would_block errno={error.errno}")
                return b""
            self.connected = False
            self._event(_error_event("read_error", error))
            self._event("disconnect source=read_error")
            raise TransportDisconnected(str(error)) from error
        except (OSError, ValueError) as error:
            if _disconnect_errno(error):
                self.connected = False
                self._event(_error_event("read_error", error))
                self._event("disconnect source=read_error")
                raise TransportDisconnected(str(error)) from error
            self._event(_error_event("read_error", error))
            raise TransportError(str(error)) from error
        if not data:
            self.connected = False
            self._event("read_eof")
            self._event("disconnect source=read_eof")
        else:
            self._last_event = None
        return data

    def write(self, data: bytes) -> None:
        if not self.connected:
            raise TransportDisconnected("socket is disconnected")
        view = memoryview(data)
        while view:
            try:
                _, writable, _ = select.select([], [self.socket], [], 1.0)
                if not writable:
                    raise TransportError("socket write timed out")
                sent = self.socket.send(view)
                if sent == 0:
                    self.connected = False
                    raise TransportError("socket closed during write")
                view = view[sent:]
            except InterruptedError:
                continue
            except (BrokenPipeError, ConnectionResetError) as error:
                self.connected = False
                self._event(_error_event("write_error", error))
                self._event("disconnect source=write_error")
                raise TransportDisconnected(str(error)) from error
            except OSError as error:
                if _disconnect_errno(error):
                    self.connected = False
                    self._event(_error_event("write_error", error))
                    self._event("disconnect source=write_error")
                    raise TransportDisconnected(str(error)) from error
                self._event(_error_event("write_error", error))
                raise

    def flush(self) -> None:
        return

    def is_connected(self) -> bool:
        return self.connected

    def close(self) -> None:
        if self.connected:
            self.connected = False
        try:
            self.socket.close()
        except OSError:
            pass

    def _event(self, message: str) -> None:
        if self._debug is None:
            return
        if message == self._last_event and message == "read_timeout":
            return
        self._last_event = message
        try:
            self._debug(message)
        except Exception:  # noqa: BLE001 - diagnostics must never affect I/O
            pass


def _fileno(stream: object) -> int:
    try:
        return int(getattr(stream, "fileno", lambda: -1)())
    except (OSError, ValueError, TypeError):
        return -1


def _write_filelike(target: object, data: bytes) -> None:
    write = getattr(target, "write", None)
    if write is None:
        raise OSError("output stream is not writable")
    offset = 0
    while offset < len(data):
        written = write(data[offset:])
        if written is None:
            offset = len(data)
        elif written <= 0:
            raise OSError("output stream made no progress")
        else:
            offset += written


def _disconnect_errno(error: BaseException) -> bool:
    return getattr(error, "errno", None) in {
        errno.EBADF,
        errno.ECONNRESET,
        errno.EPIPE,
        errno.ENOTCONN,
        errno.ECONNABORTED,
        errno.ESHUTDOWN,
    }


def _error_event(kind: str, error: BaseException) -> str:
    return f"{kind} errno={getattr(error, 'errno', None)} message={error}"
