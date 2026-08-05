"""ANSI full and differential serializers."""

from ansiradar.render.buffer import Cell, ScreenBuffer


def _style(cell: Cell, color: bool) -> str:
    if not color:
        return ""
    codes = ["0"]
    if cell.bold:
        codes.append("1")
    if cell.dim:
        codes.append("2")
    if cell.inverse:
        codes.append("7")
    if cell.foreground is not None:
        codes.append(str(30 + cell.foreground % 8))
    if cell.background is not None:
        codes.append(str(40 + cell.background % 8))
    return "\x1b[" + ";".join(codes) + "m"


def serialize_full(
    buffer: ScreenBuffer, *, color: bool = False, clear: bool = True
) -> str:
    prefix = "\x1b[2J\x1b[H" if clear else "\x1b[H"
    body = "\n".join(
        "".join(_style(cell, color) + cell.char for cell in row) for row in buffer.cells
    )
    return prefix + body + "\x1b[0m"


def serialize_diff(
    current: ScreenBuffer, previous: ScreenBuffer | None, *, color: bool = False
) -> str:
    changed = current.diff(previous)
    if previous is None or (previous.width, previous.height) != (
        current.width,
        current.height,
    ):
        return serialize_full(current, color=color)
    output: list[str] = []
    for x, y, cell in changed:
        output.append(f"\x1b[{y + 1};{x + 1}H{_style(cell, color)}{cell.char}")
    return "".join(output) + ("\x1b[0m" if output else "")
