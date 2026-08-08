"""Mystic-native adapter; it deliberately does not use the DOOR32 transport."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ansiradar.poller import SourcePoller
from ansiradar.radar.engine import RadarEngine
from ansiradar.render.ansi import serialize_full
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import RadarRenderOptions, render_radar
from ansiradar.sources import AircraftSource, SourceSpec, build_source
from ansiradar.tracking import TrackManager


class MysticAPI(Protocol):
    def rwrite(self, text: str) -> object: ...

    def getkey(self) -> object: ...


@dataclass(frozen=True, slots=True)
class MysticTerminalProfile:
    """Conservative terminal contract for Mystic's embedded output path."""

    width: int = 80
    height: int = 25
    usable_width: int = 79
    usable_height: int = 24
    charset: str = "ascii"
    color: bool = True
    full_refresh: bool = True

    def __post_init__(self) -> None:
        if self.width != 80 or self.height != 25:
            raise ValueError("Mystic currently requires an 80x25 terminal")
        if self.usable_width > self.width - 1 or self.usable_height > self.height:
            raise ValueError("Mystic usable area exceeds nominal terminal")
        if self.charset != "ascii":
            raise ValueError("Mystic output currently supports ASCII only")


@dataclass(frozen=True, slots=True)
class MysticConfig:
    width: int = 80
    height: int = 25
    range_nm: float = 100.0
    charset: str = "ascii"
    color: bool = True
    label: str = "callsign"
    units: str = "aviation"
    poll_interval: float = 2.0
    idle_sleep: float = 0.05


class MysticTerminalAdapter:
    """Small boundary around the real Mystic Python API."""

    def __init__(self, api: MysticAPI) -> None:
        self.api = api
        self.last_raw_key: object = None

    def write_raw(self, text: str) -> None:
        # Mystic receives Python strings; explicitly keep this path ASCII-only.
        self.api.rwrite(text.encode("ascii", "replace").decode("ascii"))

    def flush(self) -> None:
        flush = getattr(self.api, "flush", None)
        if callable(flush):
            flush()

    def input_available(self) -> bool:
        available = getattr(self.api, "keypressed", False)
        if callable(available):
            available = available()
        return bool(available)

    def read_key(self, *, available: bool | None = None) -> str | None:
        if available is None:
            available = self.input_available()
        if not available:
            return None
        getkey = getattr(self.api, "getkey", None)
        if not callable(getkey):
            raise MysticInputError("Mystic getkey() is unavailable")
        self.last_raw_key = getkey()
        value = self.last_raw_key
        if isinstance(value, (tuple, list)) and value:
            value = value[0]
        return map_key(value)

    def term_size(self) -> tuple[int, int]:
        termsize = getattr(self.api, "termsize", None)
        if callable(termsize):
            value = termsize()
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                return int(value[0]), int(value[1])
        return 80, 25


@dataclass(slots=True)
class MysticState:
    range_nm: float
    label: str
    sort_mode: str = "distance"
    show_ground: bool = True
    paused: bool = False
    help_overlay: bool = False
    selection_index: int = 0


class MysticStartupError(RuntimeError):
    """A source or engine could not be initialized for an embedded session."""


class MysticInputError(RuntimeError):
    """Mystic cannot provide a nonblocking queued-key reader."""


def build_mystic_engine(
    spec: SourceSpec,
    *,
    receiver_lat: float,
    receiver_lon: float,
    poll_interval: float = 2.0,
) -> tuple[RadarEngine, AircraftSource]:
    """Build and seed one engine, turning source startup into a controlled error."""
    try:
        source = build_source(spec)
        startup = source.poll()
        engine = RadarEngine(
            SourcePoller(source, poll_interval=poll_interval),
            TrackManager(),
            receiver_lat=receiver_lat,
            receiver_lon=receiver_lon,
            max_age=60,
        )
        engine.poller.seed(startup)
        engine.apply_manual(startup)
        return engine, source
    except Exception as error:
        raise MysticStartupError(str(error)) from error


def new_state(config: MysticConfig) -> MysticState:
    """Create all mutable state for one invocation."""
    return MysticState(range_nm=config.range_nm, label=config.label)


def map_key(value: object) -> str | None:
    """Normalize Mystic key values without interpreting terminal input bytes."""
    if isinstance(value, int):
        value = {
            13: "ENTER",
            27: "ESC",
            9: "TAB",
            256: "UP",
            257: "DOWN",
        }.get(value, chr(value) if 32 <= value <= 126 else "")
    if not isinstance(value, str):
        return None
    names = {
        "\x1b": "ESC",
        "\r": "ENTER",
        "\n": "ENTER",
        "\t": "TAB",
        "KEY_UP": "UP",
        "ARROW_UP": "UP",
        "KEY_DOWN": "DOWN",
        "ARROW_DOWN": "DOWN",
        "KEY_LEFT": "LEFT",
        "ARROW_LEFT": "LEFT",
        "KEY_RIGHT": "RIGHT",
        "ARROW_RIGHT": "RIGHT",
        "KEY_ENTER": "ENTER",
        "KEY_ESCAPE": "ESC",
    }
    return names.get(value.upper(), value if len(value) == 1 else value.upper())


def read_mystic_key(api: MysticAPI) -> str | None:
    """Compatibility wrapper for the isolated Mystic input adapter."""
    return MysticTerminalAdapter(api).read_key()


def apply_key(state: MysticState, key: str, item_count: int) -> str | None:
    """Apply a control and return a log-friendly action name, if any."""
    key = map_key(key) or ""
    lowered = key.casefold()
    if lowered == "q":
        return "quit"
    if lowered in {"h", "?"}:
        state.help_overlay = not state.help_overlay
        return "help"
    if key == "UP" or lowered == "k":
        state.selection_index = max(0, state.selection_index - 1)
        return "previous"
    if key == "DOWN" or lowered == "j":
        state.selection_index = min(state.selection_index + 1, max(0, item_count - 1))
        return "next"
    if lowered in {"+", "="}:
        state.range_nm = max(5.0, state.range_nm / 2)
        return "zoom_in"
    if key == "-":
        state.range_nm = min(500.0, state.range_nm * 2)
        return "zoom_out"
    if key in "1234":
        state.range_nm = {"1": 25.0, "2": 50.0, "3": 100.0, "4": 200.0}[key]
        return "range"
    if lowered == "g":
        state.show_ground = not state.show_ground
        return "ground"
    if lowered == "s":
        state.sort_mode = {
            "distance": "callsign",
            "callsign": "altitude",
            "altitude": "distance",
        }[state.sort_mode]
        return "sort"
    if lowered == "l":
        state.label = {
            "callsign": "icao",
            "icao": "none",
            "none": "callsign",
        }[state.label]
        return "labels"
    if lowered == "p":
        state.paused = not state.paused
        return "pause"
    if lowered == "r":
        return "refresh"
    return None


def run_mystic(
    api: MysticAPI,
    engine: RadarEngine,
    config: MysticConfig,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] | None = None,
) -> str:
    """Run one fresh Mystic session and return its controlled exit reason."""
    if config.width < 20 or config.height < 10:
        raise ValueError("Mystic screen is too small")
    profile = MysticTerminalProfile(
        width=config.width,
        height=config.height,
        charset=config.charset,
        color=config.color,
    )
    terminal = MysticTerminalAdapter(api)
    state = new_state(config)
    last_poll = -config.poll_interval
    last_available: bool | None = None
    try:
        terminal.write_raw("\x1b[2J\x1b[H\x1b[?25l")
        while True:
            available = terminal.input_available()
            if log is not None and available != last_available:
                log(f"key_available={available}")
            last_available = available
            key = terminal.read_key(available=available)
            if key is not None:
                if log is not None:
                    log(f"getkey raw={terminal.last_raw_key!r}")
                    log(f"key={key!r}")
                action = apply_key(state, key, len(engine.frame().items))
                if log is not None and action is not None:
                    log(f"action={action!r}")
                if action == "quit":
                    return "quit"
                if action == "refresh":
                    engine.poller.force_poll()
                if key == "ESC" and state.help_overlay:
                    state.help_overlay = False
            now = clock()
            if not state.paused and now - last_poll >= config.poll_interval:
                engine.step()
                last_poll = now
            frame = engine.frame()
            items = frame.items
            if state.sort_mode != "distance":
                from ansiradar.runtime import _sort_items

                items = _sort_items(items, state.sort_mode)
            selected = (
                items[state.selection_index].aircraft.icao
                if items and state.selection_index < len(items)
                else None
            )
            rendered = render_radar(
                items,
                width=profile.usable_width,
                height=profile.usable_height,
                options=RadarRenderOptions(
                    range_nm=state.range_nm,
                    charset=profile.charset,
                    color=profile.color,
                    label=state.label,
                    units=config.units,
                    ground=state.show_ground,
                    selected_icao=selected,
                    status=f"src {frame.source_status.kind}",
                ),
            )
            if state.help_overlay:
                _help(rendered)
            output = serialize_full(
                rendered,
                color=profile.color,
                clear=True,
                positioned=True,
            )
            terminal.write_raw(output)
            sleep(config.idle_sleep)
    finally:
        if log is not None:
            log("restoring_terminal")
        try:
            terminal.write_raw("\x1b[0m\x1b[?25h")
        except Exception as error:  # noqa: BLE001 - return to Mystic regardless
            if log is not None:
                log(f"terminal_restore_failed={error!r}")
        try:
            terminal.flush()
        except Exception as error:  # noqa: BLE001 - return to Mystic regardless
            if log is not None:
                log(f"flush_failed={error!r}")
        if log is not None:
            log("return_to_mystic")


def _help(buffer: ScreenBuffer) -> None:
    buffer.box(2, 2, min(buffer.width - 4, 56), min(buffer.height - 4, 17), "ascii")
    lines = (
        "ANSIRadar controls",
        "Q quit  Up/K previous  Down/J next",
        "H/? help  +/- zoom  1-4 range",
        "G ground  S sort  L labels",
        "P pause  R refresh",
    )
    for y, text in enumerate(lines, 3):
        buffer.clipped_text(4, y, text, min(48, buffer.width - 8))
