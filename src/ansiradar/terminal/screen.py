"""ANSI screen lifecycle primitives."""

import sys


def enter_alt_screen(stream: object = sys.stdout) -> None:
    stream.write("\x1b[?1049h\x1b[?25l")  # type: ignore[attr-defined]
    stream.flush()  # type: ignore[attr-defined]


def leave_alt_screen(stream: object = sys.stdout) -> None:
    stream.write("\x1b[?25h\x1b[0m\x1b[?1049l")  # type: ignore[attr-defined]
    stream.flush()  # type: ignore[attr-defined]
