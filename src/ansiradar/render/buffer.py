"""Clipped character-cell screen buffer."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Cell:
    char: str = " "
    foreground: int | None = None
    background: int | None = None
    bold: bool = False
    dim: bool = False
    inverse: bool = False


class ScreenBuffer:
    def __init__(self, width: int, height: int, fill: Cell | None = None) -> None:
        self.width = max(0, width)
        self.height = max(0, height)
        self._fill = fill or Cell()
        self.cells = [
            [self._fill for _ in range(self.width)] for _ in range(self.height)
        ]

    def clear(self, cell: Cell | None = None) -> None:
        fill = cell or self._fill
        self.cells = [[fill for _ in range(self.width)] for _ in range(self.height)]

    def set_cell(self, x: int, y: int, cell: Cell | str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.cells[y][x] = Cell(cell) if isinstance(cell, str) else cell

    def get_cell(self, x: int, y: int) -> Cell:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.cells[y][x]
        return self._fill

    def draw_text(
        self, x: int, y: int, text: str, *, clip: int | None = None, **style: object
    ) -> None:
        if clip is not None:
            text = text[: max(0, clip)]
        foreground = style.get("foreground")
        background = style.get("background")
        template = Cell(
            foreground=foreground if isinstance(foreground, int) else None,
            background=background if isinstance(background, int) else None,
            bold=bool(style.get("bold", False)),
            dim=bool(style.get("dim", False)),
            inverse=bool(style.get("inverse", False)),
        )
        for offset, char in enumerate(text):
            self.set_cell(
                x + offset,
                y,
                Cell(
                    char,
                    template.foreground,
                    template.background,
                    template.bold,
                    template.dim,
                    template.inverse,
                ),
            )

    def hline(self, x: int, y: int, length: int, char: str = "-") -> None:
        for offset in range(max(0, length)):
            self.set_cell(x + offset, y, char)

    def vline(self, x: int, y: int, length: int, char: str = "|") -> None:
        for offset in range(max(0, length)):
            self.set_cell(x, y + offset, char)

    def box(
        self, x: int, y: int, width: int, height: int, charset: str = "ascii"
    ) -> None:
        if width <= 0 or height <= 0:
            return
        chars = {
            "ascii": ("+", "+", "+", "+", "-", "|"),
            "unicode": ("┌", "┐", "└", "┘", "─", "│"),
            "cp437": ("┌", "┐", "└", "┘", "─", "│"),
        }.get(charset, ("+", "+", "+", "+", "-", "|"))
        tl, tr, bl, br, horizontal, vertical = chars
        self.set_cell(x, y, tl)
        self.set_cell(x + width - 1, y, tr)
        self.set_cell(x, y + height - 1, bl)
        self.set_cell(x + width - 1, y + height - 1, br)
        self.hline(x + 1, y, width - 2, horizontal)
        self.hline(x + 1, y + height - 1, width - 2, horizontal)
        self.vline(x, y + 1, height - 2, vertical)
        self.vline(x + width - 1, y + 1, height - 2, vertical)

    def clipped_text(self, x: int, y: int, text: str, width: int) -> None:
        self.draw_text(x, y, text, clip=width)

    def diff(self, previous: "ScreenBuffer | None") -> list[tuple[int, int, Cell]]:
        if (
            previous is None
            or previous.width != self.width
            or previous.height != self.height
        ):
            return [
                (x, y, self.cells[y][x])
                for y in range(self.height)
                for x in range(self.width)
            ]
        return [
            (x, y, self.cells[y][x])
            for y in range(self.height)
            for x in range(self.width)
            if self.cells[y][x] != previous.cells[y][x]
        ]

    def serialize(self) -> str:
        return "\n".join("".join(cell.char for cell in row) for row in self.cells)
