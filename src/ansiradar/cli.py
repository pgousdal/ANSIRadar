"""Command-line interface for ANSIRadar operations."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from time import monotonic
from typing import Any

from ansiradar import __version__
from ansiradar.bbs import BBSTerminalProfile
from ansiradar.diag import make_logger, redact_url, shorten_message
from ansiradar.door import (
    DOOR_EXIT_DESCRIPTOR,
    DOOR_EXIT_DISCONNECT,
    DOOR_EXIT_DROPFILE,
    DOOR_EXIT_IDLE,
    DOOR_EXIT_INTERNAL,
    DOOR_EXIT_OK,
    DOOR_EXIT_SOURCE,
    DOOR_EXIT_TIME_EXPIRED,
    DOOR_EXIT_UNSUPPORTED_MODE,
    Door32Error,
    InvalidDescriptor,
    UnsupportedCommunicationMode,
    parse_door32,
)
from ansiradar.models import Aircraft, AircraftSnapshot, PositionedAircraft
from ansiradar.obs import ObservationSnapshot, snapshot_to_aircraft_snapshot
from ansiradar.poller import SourcePoller
from ansiradar.radar.engine import RadarEngine
from ansiradar.radar.geo import coordinates_valid, distance_km, initial_bearing_deg
from ansiradar.render.radar import RadarRenderOptions, render_radar
from ansiradar.render.snapshot import render_snapshot
from ansiradar.replay import ReplayRecorder, ReplaySource
from ansiradar.runtime import RuntimeConfig, run_interactive
from ansiradar.sources import (
    AircraftSource,
    InvalidSourceData,
    SourceError,
    SourceSpec,
    SourceUnavailable,
    UnsupportedSource,
    build_source,
    normalize_kind,
)
from ansiradar.terminal.capabilities import resolve_capabilities
from ansiradar.terminal.session import TerminalSession
from ansiradar.tracking import TrackManager
from ansiradar.transport import DescriptorSocketTransport, LocalTTYTransport

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_INVALID_JSON = 4
EXIT_SCHEMA = 5

_KINDS = ("url", "file", "replay")

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_TIMEOUT = 10.0
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_MAX_AIRCRAFT = 2000


def _add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", help="source kind: url, file, or replay")
    parser.add_argument("--url", help="HTTP(S) aircraft.json endpoint")
    parser.add_argument("--file", help="local aircraft.json file path")
    parser.add_argument("--replay-file", help="JSON-lines replay file")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--max-bytes", type=int, default=DEFAULT_MAX_BYTES, dest="max_bytes"
    )
    parser.add_argument("--max-aircraft", type=int, default=DEFAULT_MAX_AIRCRAFT)
    parser.add_argument("--log", help="optional diagnostics log file")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ansiradar")
    parser.add_argument(
        "--version", action="version", version=f"ANSIRadar {__version__}"
    )
    parser.add_argument("--json", action="store_true", dest="global_json")
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="render one aircraft snapshot")
    _add_source_args(snapshot)
    snapshot.add_argument("--receiver-lat", type=float)
    snapshot.add_argument("--receiver-lon", type=float)
    snapshot.add_argument("--max-age", type=float, default=60.0)
    snapshot.add_argument("--limit", type=int)
    snapshot.add_argument(
        "--sort", choices=("distance", "callsign", "altitude"), default="distance"
    )
    snapshot.add_argument("--units", choices=("metric", "aviation"), default="aviation")
    snapshot.add_argument("--json", action="store_true", dest="command_json")

    check = subparsers.add_parser("source-check", help="validate a data source")
    _add_source_args(check)
    check.add_argument("--json", action="store_true", dest="command_json")

    inspect = subparsers.add_parser("replay-inspect", help="validate a replay file")
    inspect.add_argument("replay_file", nargs="?")
    inspect.add_argument("--replay-file", dest="replay_flag")
    inspect.add_argument("--json", action="store_true", dest="command_json")

    radar = subparsers.add_parser("radar", help="interactive polar radar")
    _add_source_args(radar)
    radar.add_argument("--receiver-lat", type=float)
    radar.add_argument("--receiver-lon", type=float)
    radar.add_argument("--range", type=float, default=100.0, dest="range_nm")
    radar.add_argument("--refresh", type=float, default=DEFAULT_POLL_INTERVAL)
    radar.add_argument("--max-age", type=float, default=60.0)
    radar.add_argument("--units", choices=("metric", "aviation"), default="aviation")
    radar.add_argument(
        "--charset", "--symbols", choices=("ascii", "cp437", "unicode"), default="ascii"
    )
    radar.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    radar.add_argument("--trails", type=int, default=0)
    radar.add_argument(
        "--label", choices=("callsign", "icao", "none"), default="callsign"
    )
    radar.add_argument("--once", action="store_true")
    radar.add_argument("--no-alt-screen", action="store_true")
    radar.add_argument(
        "--record", help="write normalized observations to a replay file"
    )
    radar.add_argument(
        "--pos-stale", type=float, default=30.0, help="position stale age (s)"
    )
    radar.add_argument(
        "--track-stale", type=float, default=60.0, help="aircraft stale age (s)"
    )
    radar.add_argument(
        "--removal-age", type=float, default=120.0, help="track removal age (s)"
    )
    radar.add_argument("--max-tracks", type=int, default=200)

    door = subparsers.add_parser("door", help="interactive Mystic DOOR32 BBS door")
    door.add_argument("--door32", required=True, help="path to Mystic DOOR32.SYS")
    _add_source_args(door)
    door.add_argument("--receiver-lat", type=float)
    door.add_argument("--receiver-lon", type=float)
    door.add_argument("--range", type=float, default=100.0, dest="range_nm")
    door.add_argument("--refresh", type=float, default=DEFAULT_POLL_INTERVAL)
    door.add_argument("--max-age", type=float, default=60.0)
    door.add_argument("--units", choices=("metric", "aviation"), default="aviation")
    door.add_argument(
        "--charset", "--symbols", choices=("ascii", "cp437", "unicode"), default="cp437"
    )
    door.add_argument("--color", choices=("always", "never"), default="always")
    door.add_argument("--trails", type=int, default=0)
    door.add_argument(
        "--label", choices=("callsign", "icao", "none"), default="callsign"
    )
    door.add_argument("--pos-stale", type=float, default=30.0)
    door.add_argument("--track-stale", type=float, default=60.0)
    door.add_argument("--removal-age", type=float, default=120.0)
    door.add_argument("--max-tracks", type=int, default=200)
    door.add_argument("--width", type=int, default=80)
    door.add_argument("--height", type=int, default=24)
    door.add_argument("--idle-timeout", type=float)
    door.add_argument("--idle-warning", type=float, default=60.0)
    door.add_argument("--time-warning", type=float, default=10.0)
    door.add_argument("--no-clear-on-exit", action="store_true")
    door.add_argument(
        "--debug-input-log",
        help="optional bounded raw-input diagnostic log (door mode only)",
    )
    return parser


def _env_float(name: str, parser: argparse.ArgumentParser) -> float | None:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        parser.error(f"{name} must be a number")


def _resolve_spec(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> SourceSpec:
    raw = (args.source or os.getenv("ANSIRADAR_SOURCE") or "").strip()
    explicit_kind = raw.lower() if raw else ""
    provided = [flag for flag in (args.url, args.file, args.replay_file) if flag]
    if len(provided) > 1:
        parser.error("--url, --file, and --replay-file are mutually exclusive")

    if provided:
        if args.url is not None:
            kind = "url"
        elif args.file is not None:
            kind = "file"
        else:
            kind = "replay"
        if explicit_kind and explicit_kind in _KINDS and explicit_kind != kind:
            parser.error(
                f"--source {explicit_kind} conflicts with the provided --{kind} option"
            )
        return SourceSpec(
            kind=normalize_kind(kind),
            url=args.url,
            file=args.file,
            replay_file=args.replay_file,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            max_aircraft=args.max_aircraft,
        )
    if explicit_kind in _KINDS:
        if explicit_kind == "url":
            parser.error("url source requires --url")
        if explicit_kind == "file":
            parser.error("file source requires --file (or ANSIRADAR_SOURCE as a path)")
        parser.error("replay source requires --replay-file")
    if explicit_kind and _looks_like_path(raw):
        return SourceSpec(
            kind="file",
            file=raw,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            max_aircraft=args.max_aircraft,
        )
    if explicit_kind:
        parser.error(
            f"unknown source type {args.source!r}; choose from url, file, replay"
        )
    parser.error(
        "--source KIND (url, file, replay) or one of --url/--file/--replay-file "
        "is required (or set ANSIRADAR_SOURCE)"
    )


def _looks_like_path(value: str) -> bool:
    lowered = value.lower()
    return (
        "/" in value
        or "\\" in value
        or value.startswith(".")
        or lowered.startswith(("http://", "https://", "file://"))
        or lowered.endswith((".json", ".jsonl"))
        or os.path.exists(value)
    )


def _poll_once(
    spec: SourceSpec, parser: argparse.ArgumentParser
) -> ObservationSnapshot:
    source = build_source(spec)
    try:
        return source.poll()
    finally:
        close = getattr(source, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass


def _positioned(
    snapshot: AircraftSnapshot, lat: float, lon: float, max_age: float
) -> tuple[tuple[PositionedAircraft, ...], int]:
    positioned: list[PositionedAircraft] = []
    valid_positions = 0
    for aircraft in snapshot.aircraft:
        if aircraft.latitude is None or aircraft.longitude is None:
            continue
        valid_positions += 1
        if (
            aircraft.seen_pos_seconds is not None
            and aircraft.seen_pos_seconds > max_age
        ):
            continue
        positioned.append(
            PositionedAircraft(
                aircraft=aircraft,
                distance_km=distance_km(
                    lat, lon, aircraft.latitude, aircraft.longitude
                ),
                bearing_deg=initial_bearing_deg(
                    lat, lon, aircraft.latitude, aircraft.longitude
                ),
            )
        )
    return tuple(positioned), valid_positions


def _altitude(aircraft: Aircraft) -> int | None:
    if aircraft.altitude_baro_ft is not None:
        return aircraft.altitude_baro_ft
    return aircraft.altitude_geom_ft


def _sort(
    items: tuple[PositionedAircraft, ...], mode: str
) -> tuple[PositionedAircraft, ...]:
    def key(item: PositionedAircraft) -> tuple[Any, ...]:
        aircraft = item.aircraft
        if mode == "callsign":
            value: Any = aircraft.callsign.casefold() if aircraft.callsign else None
        elif mode == "altitude":
            value = _altitude(aircraft)
        else:
            value = item.distance_km
        return (value is None, value if value is not None else 0, aircraft.icao)

    return tuple(sorted(items, key=key))


def _aircraft_json(item: PositionedAircraft) -> dict[str, Any]:
    aircraft = item.aircraft
    return {
        "altitude_baro_ft": aircraft.altitude_baro_ft,
        "altitude_geom_ft": aircraft.altitude_geom_ft,
        "bearing_deg": round(item.bearing_deg, 3),
        "callsign": aircraft.callsign,
        "category": aircraft.category,
        "distance_km": round(item.distance_km, 3),
        "emergency": aircraft.emergency,
        "ground": aircraft.ground,
        "ground_speed_kt": aircraft.ground_speed_kt,
        "icao": aircraft.icao,
        "latitude": aircraft.latitude,
        "longitude": aircraft.longitude,
        "messages": aircraft.messages,
        "rssi_dbfs": aircraft.rssi_dbfs,
        "seen_pos_seconds": aircraft.seen_pos_seconds,
        "seen_seconds": aircraft.seen_seconds,
        "squawk": aircraft.squawk,
        "track_deg": aircraft.track_deg,
        "vertical_rate_fpm": aircraft.vertical_rate_fpm,
    }


def _dump(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True))


def _receiver(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> tuple[float, float]:
    lat = (
        args.receiver_lat
        if args.receiver_lat is not None
        else _env_float("ANSIRADAR_RECEIVER_LAT", parser)
    )
    lon = (
        args.receiver_lon
        if args.receiver_lon is not None
        else _env_float("ANSIRADAR_RECEIVER_LON", parser)
    )
    if lat is None or lon is None:
        parser.error("receiver latitude and longitude are required")
    if not coordinates_valid(lat, lon):
        parser.error("receiver coordinates are outside valid ranges")
    return lat, lon


def _source_label(spec: SourceSpec) -> str:
    endpoint = redact_url(spec.endpoint()) if spec.kind == "url" else spec.endpoint()
    return f"{spec.kind}:{endpoint}"


def _snapshot(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    spec = _resolve_spec(args, parser)
    lat, lon = _receiver(args, parser)
    if args.max_age < 0:
        parser.error("--max-age must be non-negative")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    snapshot = snapshot_to_aircraft_snapshot(_poll_once(spec, parser))
    positioned, valid_positions = _positioned(snapshot, lat, lon, args.max_age)
    displayed = _sort(positioned, args.sort)
    if args.limit is not None:
        displayed = displayed[: args.limit]
    if args.global_json or args.command_json:
        _dump(
            {
                "aircraft": [_aircraft_json(item) for item in displayed],
                "receiver": {"latitude": lat, "longitude": lon},
                "schema_version": 1,
                "source": {
                    "generated_at": snapshot.generated_at,
                    "kind": spec.kind,
                    "location": _source_label(spec),
                    "messages": snapshot.messages,
                },
                "summary": {
                    "aircraft_displayed": len(displayed),
                    "aircraft_total": len(snapshot.aircraft),
                    "aircraft_with_position": valid_positions,
                    "aircraft_without_position": len(snapshot.aircraft)
                    - valid_positions,
                },
            }
        )
    else:
        print(
            render_snapshot(
                source_name=spec.kind,
                source_location=_source_label(spec),
                receiver_lat=lat,
                receiver_lon=lon,
                total=len(snapshot.aircraft),
                with_position=valid_positions,
                displayed=displayed,
                units=args.units,
            ),
            end="",
        )
    return EXIT_OK


def _source_check(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    spec = _resolve_spec(args, parser)
    snapshot = _poll_once(spec, parser)
    positioned = sum(
        obs.latitude is not None and obs.longitude is not None
        for obs in snapshot.observations
    )
    result = {
        "aircraft_records": len(snapshot.observations),
        "aircraft_with_position": positioned,
        "format": "readsb-json",
        "json_valid": True,
        "kind": spec.kind,
        "messages": snapshot.messages,
        "skipped": snapshot.skipped,
        "source": _source_label(spec),
        "source_readable": True,
        "source_timestamp": snapshot.generated_at,
    }
    if args.global_json or args.command_json:
        _dump(result)
    else:
        print("Source OK")
        print(f"  Location:           {_source_label(spec)}")
        print(f"  Source kind:        {spec.kind}")
        print("  JSON valid:         yes")
        print("  Format:             readsb/dump1090 aircraft.json")
        print(f"  Aircraft records:   {len(snapshot.observations)}")
        print(f"  With position:      {positioned}")
        print(f"  Source timestamp:   {snapshot.generated_at or '-'}")
        print(f"  Message counter:    {snapshot.messages or '-'}")
        if snapshot.skipped:
            print(f"  Skipped records:    {snapshot.skipped}")
    return EXIT_OK


def _replay_inspect(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    path = args.replay_flag or args.replay_file
    if not path:
        parser.error("replay-inspect requires a replay file")
    source = ReplaySource(path)
    result = {
        "lines": source.record_count(),
        "format": "ansiradar-replay-jsonl",
        "path": path,
        "first_timestamp": source.peek_time(),
        "last_timestamp": source.last_timestamp(),
        "aircraft_records": source.observation_count(),
        "valid": True,
    }
    if args.global_json or args.command_json:
        _dump(result)
    else:
        first = _fmt_ts(result["first_timestamp"])
        last = _fmt_ts(result["last_timestamp"])
        print("Replay OK")
        print(f"  Path:               {path}")
        print(f"  Records:            {result['lines']}")
        print(f"  First timestamp:    {first}")
        print(f"  Last timestamp:     {last}")
        print(f"  Observations:       {result['aircraft_records']}")
    return EXIT_OK


def _fmt_ts(value: float | None) -> str:
    return "-" if value is None else f"{value:.6f}"


def _radar_positioned(
    snapshot: AircraftSnapshot, lat: float, lon: float, max_age: float
) -> tuple[PositionedAircraft, ...]:
    positioned, _ = _positioned(snapshot, lat, lon, max_age)
    return _sort(positioned, "distance")


def _status_line(status: Any, now: float) -> str:
    if status.healthy:
        health = "OK"
    elif status.exhausted:
        health = "END"
    else:
        health = "ERR"
    age = (
        f"{now - status.last_success_time:.0f}s"
        if status.last_success_time is not None
        else "-"
    )
    parts = [
        f"src {status.kind} {health} {age}",
        f"{status.observations} obs",
    ]
    if status.retry_in is not None:
        parts.append(f"retry {status.retry_in:.0f}s")
    if status.skipped:
        parts.append(f"skip {status.skipped}")
    return " | ".join(parts)


def _radar_once(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    spec: SourceSpec,
    lat: float,
    lon: float,
    logger: Any,
) -> int:
    if spec.kind == "replay":
        source = ReplaySource(spec.replay_file)  # type: ignore[arg-type]
        end_time = source.last_timestamp() or 0.0
        manager = TrackManager(
            position_stale_age=args.pos_stale,
            aircraft_stale_age=args.track_stale,
            removal_age=args.removal_age,
            max_tracks=args.max_tracks,
            clock=lambda: end_time,
        )
        for record in source.records():
            manager.apply(
                ObservationSnapshot(
                    generated_at=record.timestamp,
                    source=record.source,
                    observations=record.observations,
                    messages=record.messages,
                    skipped=record.skipped,
                )
            )
        items = _items_from_tracks(manager, lat, lon, args.max_age)
        status = _status_line(_static_status(spec), end_time)
        rendered = render_radar(
            items,
            width=80,
            height=24,
            options=RadarRenderOptions(
                range_nm=args.range_nm,
                charset=args.charset,
                color=False,
                label=args.label,
                units=args.units,
                ground=True,
                status=status,
            ),
        )
        print(rendered.serialize())
        return EXIT_OK

    observation = _poll_once(spec, parser)
    if args.record:
        _record_one(args.record, observation, logger)
    snapshot = snapshot_to_aircraft_snapshot(observation)
    items = _radar_positioned(snapshot, lat, lon, args.max_age)
    rendered = render_radar(
        items,
        width=80,
        height=24,
        options=RadarRenderOptions(
            range_nm=args.range_nm,
            charset=args.charset,
            color=False,
            label=args.label,
            units=args.units,
            ground=True,
        ),
    )
    print(rendered.serialize())
    return EXIT_OK


def _items_from_tracks(
    manager: TrackManager, lat: float, lon: float, max_age: float
) -> tuple[PositionedAircraft, ...]:
    items: list[PositionedAircraft] = []
    for item in manager.snapshot():
        if not item.active or item.position_stale:
            continue
        aircraft = item.aircraft
        if aircraft.latitude is None or aircraft.longitude is None:
            continue
        if max_age > 0 and aircraft.seen_pos_seconds is not None:
            if aircraft.seen_pos_seconds > max_age:
                continue
        items.append(
            PositionedAircraft(
                aircraft=aircraft,
                distance_km=distance_km(
                    lat, lon, aircraft.latitude, aircraft.longitude
                ),
                bearing_deg=initial_bearing_deg(
                    lat, lon, aircraft.latitude, aircraft.longitude
                ),
            )
        )
    return _sort(tuple(items), "distance")


def _static_status(spec: SourceSpec) -> Any:
    class _Status:
        kind = spec.kind
        healthy = True
        exhausted = False
        last_success_time = None
        observations = 0
        retry_in = None
        skipped = 0

    return _Status()


def _make_engine(
    args: argparse.Namespace,
    spec: SourceSpec,
    lat: float,
    lon: float,
    *,
    source: AircraftSource | None = None,
) -> RadarEngine:
    source = source or build_source(spec)
    try:
        poller = SourcePoller(
            source,
            poll_interval=args.refresh,
        )
        tracks = TrackManager(
            position_stale_age=args.pos_stale,
            aircraft_stale_age=args.track_stale,
            removal_age=args.removal_age,
            max_tracks=args.max_tracks,
        )
        engine = RadarEngine(
            poller,
            tracks,
            receiver_lat=lat,
            receiver_lon=lon,
            max_age=args.max_age,
        )
        engine.poller._kind = spec.kind
        return engine
    except Exception:
        close = getattr(source, "close", None)
        if callable(close):
            close()
        raise


def _radar(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    spec = _resolve_spec(args, parser)
    lat, lon = _receiver(args, parser)
    if not 5 <= args.range_nm <= 500:
        parser.error("--range must be between 5 and 500 nm")
    if args.refresh <= 0 or args.max_age < 0 or args.trails < 0:
        parser.error("--refresh must be positive; ages and trails must be non-negative")
    if not args.once and not sys.stdout.isatty():
        parser.error("radar requires a TTY unless --once is specified")

    logger = make_logger("ansiradar", path=args.log)
    if args.once:
        return _radar_once(args, parser, spec, lat, lon, logger)

    engine = _make_engine(args, spec, lat, lon)
    capabilities = resolve_capabilities(charset=args.charset, color=args.color)
    transport = LocalTTYTransport()
    try:
        with TerminalSession(alternate=not args.no_alt_screen):
            result = run_interactive(
                engine,
                transport,
                RuntimeConfig(
                    width=capabilities.width,
                    height=capabilities.height,
                    charset=args.charset,
                    color=capabilities.color,
                    range_nm=args.range_nm,
                    label=args.label,
                    units=args.units,
                    poll_timeout=min(0.1, args.refresh),
                    send_setup=True,
                    clear_on_exit=True,
                ),
            )
    finally:
        engine.close()
    return EXIT_OK if result.reason in {"quit", "disconnect"} else EXIT_UNAVAILABLE


def _door(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the shared radar runtime over Mystic's supplied socket descriptor."""
    session_started = monotonic()
    try:
        info = parse_door32(args.door32)
    except UnsupportedCommunicationMode:
        return DOOR_EXIT_UNSUPPORTED_MODE
    except InvalidDescriptor:
        return DOOR_EXIT_DESCRIPTOR
    except Door32Error as error:
        print(f"ansiradar door: invalid DOOR32.SYS: {error}", file=sys.stderr)
        return DOOR_EXIT_DROPFILE

    try:
        spec = _resolve_spec(args, parser)
        lat, lon = _receiver(args, parser)
        if not 5 <= args.range_nm <= 500:
            parser.error("--range must be between 5 and 500 nm")
        if args.refresh <= 0 or args.max_age < 0 or args.trails < 0:
            parser.error(
                "--refresh must be positive; ages and trails must be non-negative"
            )
        if args.idle_timeout is not None and args.idle_timeout <= 0:
            parser.error("--idle-timeout must be positive")
        if (
            args.idle_timeout is not None
            and not 0 < args.idle_warning < args.idle_timeout
        ):
            parser.error("--idle-warning must be shorter than --idle-timeout")
        if args.time_warning <= 0:
            parser.error("--time-warning must be positive")
        BBSTerminalProfile(
            width=args.width,
            height=args.height,
            charset=args.charset,
            color=args.color == "always",
        )
        transport = DescriptorSocketTransport(info.handle)
    except (SourceError, ValueError, InvalidDescriptor) as error:
        print(f"ansiradar door: configuration error: {error}", file=sys.stderr)
        return (
            DOOR_EXIT_SOURCE if isinstance(error, SourceError) else DOOR_EXIT_DROPFILE
        )

    logger = make_logger("ansiradar.door", path=args.log)
    source: AircraftSource | None = None
    try:
        source = build_source(spec)
        startup = source.poll()
        engine = _make_engine(args, spec, lat, lon, source=source)
        engine.poller.seed(startup)
        engine.apply_manual(startup)
        alias = info.user_alias or info.user_name or "caller"
        context = f"{alias[:16]} N{info.node_number} {info.time_left_minutes}m"
        result = run_interactive(
            engine,
            transport,
            RuntimeConfig(
                width=args.width,
                height=args.height,
                charset=args.charset,
                color=args.color == "always",
                range_nm=args.range_nm,
                label=args.label,
                units=args.units,
                session_seconds=info.time_left_minutes * 60,
                time_warning=args.time_warning,
                session_started=session_started,
                idle_timeout=args.idle_timeout,
                idle_warning=args.idle_warning,
                debug_input_log=(
                    args.debug_input_log or os.getenv("ANSIRADAR_DEBUG_INPUT_LOG")
                ),
                context=context,
                send_setup=True,
                clear_on_exit=not args.no_clear_on_exit,
            ),
        )
        return {
            "quit": DOOR_EXIT_OK,
            "disconnect": DOOR_EXIT_DISCONNECT,
            "time_expired": DOOR_EXIT_TIME_EXPIRED,
            "idle_timeout": DOOR_EXIT_IDLE,
            "internal_error": DOOR_EXIT_INTERNAL,
        }.get(result.reason, DOOR_EXIT_OK)
    except SourceError as error:
        logger.error("door source startup failed: %s", shorten_message(str(error)))
        return DOOR_EXIT_SOURCE
    except (BrokenPipeError, ConnectionResetError, OSError):
        return DOOR_EXIT_DISCONNECT
    except Exception:
        logger.exception("unexpected door runtime failure")
        return DOOR_EXIT_INTERNAL
    finally:
        close = getattr(source, "close", None)
        if close is not None:
            try:
                close()
            except Exception:  # noqa: BLE001
                pass
        transport.close()


def _record_one(path: str, snapshot: ObservationSnapshot, logger: Any) -> None:
    from ansiradar.replay import snapshot_to_line as to_line

    try:
        with ReplayRecorder(path) as recorder:
            recorder.write(to_line(snapshot))
    except (OSError, InvalidSourceData) as error:
        logger.warning("recording failed for %s: %s", path, error)
        raise SourceUnavailable(f"recording failed for {path}: {error}") from error


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            return _snapshot(args, parser)
        if args.command == "radar":
            return _radar(args, parser)
        if args.command == "door":
            return _door(args, parser)
        if args.command == "replay-inspect":
            return _replay_inspect(args, parser)
        return _source_check(args, parser)
    except SourceUnavailable as error:
        print(f"ansiradar: source unavailable: {error}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except InvalidSourceData as error:
        print(f"ansiradar: invalid source data: {error}", file=sys.stderr)
        return EXIT_INVALID_JSON
    except UnsupportedSource as error:
        print(f"ansiradar: unsupported source: {error}", file=sys.stderr)
        return EXIT_SCHEMA


if __name__ == "__main__":
    raise SystemExit(main())
