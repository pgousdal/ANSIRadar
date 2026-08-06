"""Transport-neutral interactive radar runtime shared by local and BBS modes."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from ansiradar.bbs import BBSTerminalProfile
from ansiradar.models import PositionedAircraft
from ansiradar.radar.engine import RadarEngine
from ansiradar.render.ansi import serialize_diff
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import RadarRenderOptions
from ansiradar.transport import InteractiveTransport, TransportError
from ansiradar.transport_input import InputDisconnected, KeyDecoder, read_key

MAX_FRAME_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    width: int = 80
    height: int = 24
    charset: str = "cp437"
    color: bool = True
    range_nm: float = 100.0
    label: str = "callsign"
    units: str = "aviation"
    poll_timeout: float = 0.1
    session_seconds: float | None = None
    time_warning: float = 10.0
    idle_timeout: float | None = None
    idle_warning: float = 60.0
    session_started: float | None = None
    context: str = ""
    send_setup: bool = True
    clear_on_exit: bool = True


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    reason: str
    frames: int


def run_interactive(
    engine: RadarEngine,
    transport: InteractiveTransport,
    config: RuntimeConfig,
    *,
    clock: Callable[[], float] = monotonic,
) -> RuntimeResult:
    """Run one radar session over any byte transport.

    The runtime owns no global state and never writes to stdout/stderr. It emits
    only renderer output through ``transport`` and returns a stable reason for
    controlled shutdown.
    """
    profile = BBSTerminalProfile(
        width=config.width,
        height=config.height,
        charset=config.charset,
        color=config.color,
    )
    decoder = KeyDecoder()
    current: ScreenBuffer | None = None
    selected: str | None = None
    selection_index = 0
    sort_mode = "distance"
    label_mode = config.label
    range_nm = config.range_nm
    show_ground = True
    paused = False
    help_overlay = False
    frames = 0
    started = config.session_started if config.session_started is not None else clock()
    last_input = started
    session_cutoff = (
        started + config.session_seconds - max(5.0, config.time_warning)
        if config.session_seconds is not None
        else None
    )
    reason = "quit"

    try:
        if config.send_setup:
            transport.write(profile.startup())
            transport.flush()
        while transport.is_connected():
            now = clock()
            if session_cutoff is not None and now >= session_cutoff:
                reason = "time_expired"
                break
            if (
                config.idle_timeout is not None
                and now - last_input >= config.idle_timeout
            ):
                reason = "idle_timeout"
                break

            if not paused:
                engine.step()
            radar_frame = engine.frame()
            items = radar_frame.items
            if sort_mode != "distance":
                items = _sort_items(items, sort_mode)
            if items and selection_index < len(items):
                selected = items[selection_index].aircraft.icao
            if selected is not None and selected not in {
                item.aircraft.icao for item in items
            }:
                selected = None
            status = _status(
                radar_frame.source_status,
                now,
                context=config.context,
                session_cutoff=session_cutoff,
                time_warning=config.time_warning,
                idle_timeout=config.idle_timeout,
                idle_warning=config.idle_warning,
                last_input=last_input,
            )
            rendered = _render(
                items,
                config,
                range_nm=range_nm,
                label=label_mode,
                show_ground=show_ground,
                selected=selected,
                status=status,
                width=config.width,
                height=config.height,
            )
            if help_overlay:
                _help(rendered, config.charset)
            output = serialize_diff(rendered, current, color=config.color)
            if len(output.encode("utf-8")) > MAX_FRAME_BYTES:
                raise RuntimeError("rendered frame exceeds output limit")
            if output:
                transport.write(profile.trusted_encode(output))
                transport.flush()
            current = rendered
            frames += 1

            try:
                key = read_key(
                    transport,
                    decoder,
                    timeout=min(config.poll_timeout, 0.25),
                )
            except InputDisconnected:
                reason = "disconnect"
                break
            if key is None:
                continue
            last_input = clock()
            if key in {"q", "Q"} and not help_overlay:
                reason = "quit"
                break
            if key in {"?", "h", "ENTER"}:
                help_overlay = not help_overlay
            elif key == "\x1b" and help_overlay:
                help_overlay = False
            elif key in {"p", "P"}:
                paused = not paused
            elif key in {"g", "G"}:
                show_ground = not show_ground
            elif key in {"+", "="}:
                range_nm = max(5.0, range_nm / 2)
            elif key == "-":
                range_nm = min(500.0, range_nm * 2)
            elif key in "1234":
                range_nm = {"1": 25.0, "2": 50.0, "3": 100.0, "4": 200.0}[key]
            elif key in {"r", "R"}:
                engine.poller.force_poll()
            elif key in {"DOWN", "j"}:
                selection_index = min(selection_index + 1, max(0, len(items) - 1))
            elif key in {"UP", "k"}:
                selection_index = max(0, selection_index - 1)
            elif key == "s":
                sort_mode = {
                    "distance": "callsign",
                    "callsign": "altitude",
                    "altitude": "distance",
                }[sort_mode]
            elif key == "l":
                label_mode = {
                    "callsign": "icao",
                    "icao": "none",
                    "none": "callsign",
                }[label_mode]
    except (TransportError, BrokenPipeError, ConnectionResetError):
        reason = "disconnect"
    except Exception:
        reason = "internal_error"
        raise
    finally:
        if config.send_setup and transport.is_connected():
            try:
                transport.write(profile.shutdown(clear=config.clear_on_exit))
                transport.flush()
            except (TransportError, OSError):
                reason = "disconnect"
    return RuntimeResult(reason=reason, frames=frames)


def _render(
    items: tuple[PositionedAircraft, ...],
    config: RuntimeConfig,
    *,
    range_nm: float,
    label: str,
    show_ground: bool,
    selected: str | None,
    status: str,
    width: int,
    height: int,
) -> ScreenBuffer:
    from ansiradar.render.radar import render_radar

    return render_radar(
        items,
        width=width,
        height=height,
        options=RadarRenderOptions(
            range_nm=range_nm,
            charset=config.charset,
            color=config.color,
            label=label,
            units=config.units,
            ground=show_ground,
            selected_icao=selected,
            status=status,
        ),
    )


def _help(buffer: ScreenBuffer, charset: str) -> None:
    buffer.box(2, 2, min(buffer.width - 4, 56), min(buffer.height - 4, 17), charset)
    buffer.clipped_text(4, 3, "ANSIRadar controls", 48)
    buffer.clipped_text(4, 5, "q quit   Up/k previous   Down/j next", 48)
    buffer.clipped_text(4, 6, "Enter details   Esc close   +/- range", 48)
    buffer.clipped_text(4, 7, "1/2/3/4 preset   g ground   s sort", 48)
    buffer.clipped_text(4, 8, "l labels   t trails   p pause   r refresh", 48)
    buffer.clipped_text(4, 9, "? or Esc closes help", 48)


def _status(
    source: object,
    now: float,
    *,
    context: str,
    session_cutoff: float | None,
    time_warning: float,
    idle_timeout: float | None,
    idle_warning: float,
    last_input: float,
) -> str:
    healthy = bool(getattr(source, "healthy", False))
    exhausted = bool(getattr(source, "exhausted", False))
    kind = str(getattr(source, "kind", "source"))
    health = "OK" if healthy else "END" if exhausted else "ERR"
    last_success = getattr(source, "last_success_time", None)
    age = f"{now - last_success:.0f}s" if last_success is not None else "-"
    observations = int(getattr(source, "observations", 0))
    result = f"src {kind} {health} {age} | {observations} obs"
    error = getattr(source, "last_error", None)
    if error and not healthy:
        result = f"{result} | {str(error)[:40]}"
    if context:
        result = f"{context} | {result}"
    if session_cutoff is not None:
        remaining = max(0.0, session_cutoff - now)
        if remaining < max(5.0, time_warning):
            result = f"{result} | time {remaining:.0f}s"
    if idle_timeout is not None:
        remaining = max(0.0, idle_timeout - (now - last_input))
        if remaining < idle_warning:
            result = f"{result} | idle {remaining:.0f}s"
    return result


def _sort_items(
    items: tuple[PositionedAircraft, ...], mode: str
) -> tuple[PositionedAircraft, ...]:
    def key(item: PositionedAircraft) -> tuple[bool, object, str]:
        aircraft = item.aircraft
        value: object
        if mode == "callsign":
            value = aircraft.callsign.casefold() if aircraft.callsign else None
        elif mode == "altitude":
            value = aircraft.altitude_baro_ft or aircraft.altitude_geom_ft
        else:
            value = item.distance_km
        return (value is None, value if value is not None else 0, aircraft.icao)

    return tuple(sorted(items, key=key))
