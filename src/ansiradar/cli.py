"""Command-line interface for one-shot ANSIRadar operations."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from ansiradar import __version__
from ansiradar.models import Aircraft, AircraftSnapshot, PositionedAircraft
from ansiradar.radar.geo import coordinates_valid, distance_km, initial_bearing_deg
from ansiradar.render.snapshot import render_snapshot
from ansiradar.sources import (
    InvalidSourceData,
    ReadsbSource,
    SourceUnavailable,
    UnsupportedSource,
)

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


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            return _snapshot(args, parser)
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
