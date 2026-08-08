"""Mystic-native adapter; it deliberately does not use the DOOR32 transport."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ansiradar.poller import SourcePoller
from ansiradar.radar.engine import RadarEngine
from ansiradar.render.ansi import serialize_diff, serialize_full
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import RadarRenderOptions, render_radar
from ansiradar.sources import AircraftSource, SourceSpec, build_source
from ansiradar.tracking import TrackManager


class MysticAPI(Protocol):
    def rwrite(self, text: str) -> object: ...

    def keypressed(self) -> bool: ...

    def onekey(self, keys: str, echo: bool) -> str: ...


@dataclass(frozen=True, slots=True)
class MysticConfig:
    width: int = 80
    height: int = 25
    range_nm: float = 100.0
    charset: str = "cp437"
    color: bool = True
    label: str = "callsign"
    units: str = "aviation"
    poll_interval: float = 2.0
    idle_sleep: float = 0.05


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
        value = {13: "ENTER", 27: "ESC", 9: "TAB", 256: "UP", 257: "DOWN"}.get(
            value, ""
        )
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
    """Read one available key; Mystic owns the actual terminal input."""
    if not api.keypressed():
        return None
    getkey = getattr(api, "getkey", None)
    if callable(getkey):
        return map_key(getkey())
    # onekey is the documented portable fallback. Arrow keys may be unavailable.
    return map_key(api.onekey("QH?KJ+=-1234GSLPR", False))


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
    state = new_state(config)
    previous: ScreenBuffer | None = None
    last_poll = -config.poll_interval
    api.rwrite("\x1b[2J\x1b[H\x1b[?25l")
    try:
        while True:
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
                width=config.width,
                height=config.height,
                options=RadarRenderOptions(
                    range_nm=state.range_nm,
                    charset=config.charset,
                    color=config.color,
                    label=state.label,
                    units=config.units,
                    ground=state.show_ground,
                    selected_icao=selected,
                    status=f"src {frame.source_status.kind}",
                ),
            )
            if state.help_overlay:
                _help(rendered)
            if previous is None:
                output = serialize_full(rendered, color=config.color, positioned=True)
            else:
                output = serialize_diff(rendered, previous, color=config.color)
            if output:
                api.rwrite(output)
            previous = rendered
            if state.help_overlay:
                # Help is rendered by the normal frame path; Escape closes it.
                pass
            key = read_mystic_key(api)
            if key is not None:
                action = apply_key(state, key, len(items))
                if log is not None and action is not None:
                    log(action)
                if action == "quit":
                    return "quit"
                if action == "refresh":
                    engine.poller.force_poll()
                if key == "ESC" and state.help_overlay:
                    state.help_overlay = False
            sleep(config.idle_sleep)
    finally:
        api.rwrite("\x1b[0m\x1b[?25h\x1b[2J\x1b[H")


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
