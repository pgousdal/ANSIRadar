"""Exception-safe terminal session context manager."""

import signal
import sys
import termios
import tty
from types import FrameType
from typing import Any, cast

from ansiradar.terminal.screen import enter_alt_screen, leave_alt_screen


class TerminalSession:
    def __init__(
        self,
        *,
        alternate: bool = True,
        stream: object = sys.stdout,
        input_stream: object = sys.stdin,
    ) -> None:
        self.alternate, self.stream, self.input_stream = alternate, stream, input_stream
        self._attrs: list[Any] | None = None
        self._old_handlers: dict[int, Any] = {}

    def __enter__(self) -> "TerminalSession":
        if self.alternate:
            enter_alt_screen(self.stream)
        fileno = getattr(self.input_stream, "fileno", lambda: -1)()
        if fileno >= 0:
            try:
                self._attrs = termios.tcgetattr(fileno)
                tty.setcbreak(fileno)
            except termios.error:
                self._attrs = None
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._old_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, self._signal)
        return self

    def _signal(self, signum: int, frame: FrameType | None) -> None:
        self.close()
        raise KeyboardInterrupt

    def close(self) -> None:
        fileno = getattr(self.input_stream, "fileno", lambda: -1)()
        if self._attrs is not None and fileno >= 0:
            termios.tcsetattr(fileno, termios.TCSADRAIN, self._attrs)
            self._attrs = None
        if self.alternate:
            leave_alt_screen(self.stream)
        for signum, handler in self._old_handlers.items():
            signal.signal(signum, cast(Any, handler))
        self._old_handlers.clear()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
