"""Non-blocking terminal key reader."""

import os
import select
import sys


def read_key(stream: object = sys.stdin, timeout: float = 0.0) -> str | None:
    fileno = getattr(stream, "fileno", lambda: -1)()
    if fileno < 0 or not select.select([fileno], [], [], timeout)[0]:
        return None
    data = os.read(fileno, 16)
    if not data:
        return None
    return data.decode("utf-8", "replace")
