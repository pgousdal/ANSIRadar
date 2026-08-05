"""Command-line interface for one-shot ANSIRadar operations."""

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from typing import Any

from ansiradar import __version__
from ansiradar.models import Aircraft, AircraftSnapshot, PositionedAircraft
from ansiradar.radar.geo import coordinates_valid, distance_km, initial_bearing_deg
from ansiradar.render.ansi import serialize_diff
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import RadarRenderOptions, render_radar
from ansiradar.render.snapshot import render_snapshot
from ansiradar.sources import (
    InvalidSourceData,
    ReadsbSource,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.terminal.capabilities import resolve_capabilities
from ansiradar.terminal.input import read_key
from ansiradar.terminal.session import TerminalSession

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_UNAVAILABLE = 3
EXIT_INVALID_JSON = 4
EXIT_SCHEMA = 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ansiradar")
    parser.add_argument(
        "--version", action="version", version=f"ANSIRadar {__version__}"
    )
    parser.add_argument("--json", action="store_true", dest="global_json")
    parser.add_argument(
        "--no-color", action="store_true", help="accepted for scripting"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser("snapshot", help="render one aircraft snapshot")
    snapshot.add_argument("--source")
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
    check.add_argument("--source")
    check.add_argument("--json", action="store_true", dest="command_json")
    radar = subparsers.add_parser("radar", help="interactive polar radar")
    radar.add_argument("--source")
    radar.add_argument("--receiver-lat", type=float)
    radar.add_argument("--receiver-lon", type=float)
    radar.add_argument("--range", type=float, default=100.0, dest="range_nm")
    radar.add_argument("--refresh", type=float, default=2.0)
    radar.add_argument("--max-age", type=float, default=60.0)
    radar.add_argument("--units", choices=("metric", "aviation"), default="aviation")
    radar.add_argument(
        "--charset", choices=("ascii", "cp437", "unicode"), default="ascii"
    )
    radar.add_argument("--color", choices=("auto", "always", "never"), default="auto")
    radar.add_argument("--trails", type=int, default=0)
    radar.add_argument(
        "--label", choices=("callsign", "icao", "none"), default="callsign"
    )
    radar.add_argument("--once", action="store_true")
    radar.add_argument("--no-alt-screen", action="store_true")
    return parser


def _env_float(name: str, parser: argparse.ArgumentParser) -> float | None:
    value = os.getenv(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        parser.error(f"{name} must be a number")


def _source(value: str | None, parser: argparse.ArgumentParser) -> str:
    result = value or os.getenv("ANSIRADAR_SOURCE")
    if not result:
        parser.error("--source is required (or set ANSIRADAR_SOURCE)")
    return result


def _positioned(
    snapshot: AircraftSnapshot, lat: float, lon: float, max_age: float
) -> tuple[tuple[PositionedAircraft, ...], int]:
    positioned: list[PositionedAircraft] = []
    valid_positions = 0
    for aircraft in snapshot.aircraft:
        if aircraft.latitude is None or aircraft.longitude is None:
            continue
        valid_positions += 1
        # Unknown seen_pos is included: the source supplied no evidence it is stale.
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


def _fetch(location: str) -> AircraftSnapshot:
    return ReadsbSource(location).fetch()


def _snapshot(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    location = _source(args.source, parser)
    lat = args.receiver_lat
    lon = args.receiver_lon
    if lat is None:
        lat = _env_float("ANSIRADAR_RECEIVER_LAT", parser)
    if lon is None:
        lon = _env_float("ANSIRADAR_RECEIVER_LON", parser)
    if lat is None or lon is None:
        parser.error("receiver latitude and longitude are required")
    if not coordinates_valid(lat, lon):
        parser.error("receiver coordinates are outside valid ranges")
    if args.max_age < 0:
        parser.error("--max-age must be non-negative")
    if args.limit is not None and args.limit < 0:
        parser.error("--limit must be non-negative")
    snapshot = _fetch(location)
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
                    "kind": "readsb-json",
                    "location": location,
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
                source_name=snapshot.source_name,
                source_location=location,
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
    location = _source(args.source, parser)
    snapshot = _fetch(location)
    positioned = sum(
        aircraft.latitude is not None and aircraft.longitude is not None
        for aircraft in snapshot.aircraft
    )
    result = {
        "aircraft_records": len(snapshot.aircraft),
        "aircraft_with_position": positioned,
        "format": "readsb-json",
        "json_valid": True,
        "messages": snapshot.messages,
        "source": location,
        "source_readable": True,
        "source_timestamp": snapshot.generated_at,
    }
    if args.global_json or args.command_json:
        _dump(result)
    else:
        print("Source OK")
        print(f"  Location:           {location}")
        print("  JSON valid:         yes")
        print("  Format:             readsb/dump1090 aircraft.json")
        print(f"  Aircraft records:   {len(snapshot.aircraft)}")
        print(f"  With position:      {positioned}")
        print(f"  Source timestamp:   {snapshot.generated_at or '-'}")
        print(f"  Message counter:    {snapshot.messages or '-'}")
    return EXIT_OK


def _radar_positioned(
    snapshot: AircraftSnapshot, lat: float, lon: float, max_age: float
) -> tuple[PositionedAircraft, ...]:
    positioned, _ = _positioned(snapshot, lat, lon, max_age)
    return _sort(positioned, "distance")


def _radar(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    location = _source(args.source, parser)
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
    if not 5 <= args.range_nm <= 500:
        parser.error("--range must be between 5 and 500 nm")
    if args.refresh <= 0 or args.max_age < 0 or args.trails < 0:
        parser.error("--refresh must be positive; ages and trails must be non-negative")
    if not args.once and not sys.stdout.isatty():
        parser.error("radar requires a TTY unless --once is specified")

    capabilities = resolve_capabilities(charset=args.charset, color=args.color)
    width, height = (80, 24) if args.once else (capabilities.width, capabilities.height)
    selected: str | None = None
    selection_index = 0
    sort_mode = "distance"
    label_mode = args.label
    range_nm = args.range_nm
    show_ground = True
    paused = False
    help_overlay = False
    current: ScreenBuffer | None = None
    last_snapshot: AircraftSnapshot | None = None
    last_error = ""
    next_fetch = 0.0
    frame_count = 0

    def frame() -> ScreenBuffer:
        nonlocal last_snapshot, last_error
        if time.monotonic() >= next_fetch and not paused:
            try:
                last_snapshot = _fetch(location)
                last_error = ""
            except SourceUnavailable as error:
                last_error = f"source error: {error}"
            except (InvalidSourceData, UnsupportedSource) as error:
                last_error = str(error)
        items = (
            _radar_positioned(last_snapshot, lat, lon, args.max_age)
            if last_snapshot
            else ()
        )
        if sort_mode != "distance":
            items = _sort(items, sort_mode)
        selected_from_items = (
            items[selection_index].aircraft.icao
            if items and selection_index < len(items)
            else selected
        )
        if selected_from_items is not None and selected_from_items not in {
            item.aircraft.icao for item in items
        }:
            # Keep selection stable where possible; disappearance clears it.
            selected_value = None
        else:
            selected_value = selected_from_items
        rendered = render_radar(
            items,
            width=width,
            height=height,
            options=RadarRenderOptions(
                range_nm=range_nm,
                charset=args.charset,
                color=capabilities.color and not args.once,
                label=label_mode,
                units=args.units,
                ground=show_ground,
                selected_icao=selected_value,
            ),
        )
        if last_error:
            rendered.clipped_text(
                2, max(0, height - 2), f"ERROR: {last_error}", max(0, width - 4)
            )
        return rendered

    def refresh_deadline() -> None:
        nonlocal next_fetch
        next_fetch = time.monotonic() + args.refresh

    next_fetch = 0.0
    if args.once:
        rendered = frame()
        print(rendered.serialize())
        return EXIT_OK if not last_error else EXIT_UNAVAILABLE

    with TerminalSession(alternate=not args.no_alt_screen):
        try:
            refresh_deadline()
            while True:
                rendered = frame()
                if help_overlay:
                    rendered.box(
                        2, 2, min(width - 4, 56), min(height - 4, 17), args.charset
                    )
                    rendered.clipped_text(4, 3, "ANSIRadar controls", 48)
                    rendered.clipped_text(
                        4, 5, "q quit   Up/k previous   Down/j next", 48
                    )
                    rendered.clipped_text(
                        4, 6, "Enter details   Esc close   +/- range", 48
                    )
                    rendered.clipped_text(
                        4, 7, "1/2/3/4 preset   g ground   s sort", 48
                    )
                    rendered.clipped_text(
                        4, 8, "l labels   t trails   p pause   r refresh", 48
                    )
                    rendered.clipped_text(4, 9, "? or Esc closes help", 48)
                output = serialize_diff(rendered, current, color=capabilities.color)
                if output:
                    sys.stdout.write(output)
                    sys.stdout.flush()
                current = rendered
                frame_count += 1
                key = read_key(timeout=min(0.1, args.refresh))
                if key:
                    if key in {"q", "Q"} and not help_overlay:
                        break
                    if key in {"?", "h"}:
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
                        next_fetch = 0.0
                    elif key in {"j", "\x1b[B"}:
                        item_count = len(
                            _radar_positioned(last_snapshot, lat, lon, args.max_age)
                            if last_snapshot
                            else ()
                        )
                        selection_index = min(
                            selection_index + 1, max(0, item_count - 1)
                        )
                    elif key in {"k", "\x1b[A"}:
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
                refresh_deadline()
        finally:
            if frame_count:
                print("", file=sys.stderr)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            return _snapshot(args, parser)
        if args.command == "radar":
            return _radar(args, parser)
        return _source_check(args, parser)
    except SourceUnavailable as error:
        print(f"ansiradar: source unavailable: {error}", file=sys.stderr)
        return EXIT_UNAVAILABLE
    except InvalidSourceData as error:
        print(f"ansiradar: invalid JSON: {error}", file=sys.stderr)
        return EXIT_INVALID_JSON
    except UnsupportedSource as error:
        print(f"ansiradar: unsupported source: {error}", file=sys.stderr)
        return EXIT_SCHEMA


if __name__ == "__main__":
    raise SystemExit(main())
