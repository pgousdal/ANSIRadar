"""Stable, ASCII-only terminal snapshot renderer."""

from ansiradar import __version__
from ansiradar.models import PositionedAircraft
from ansiradar.units import (
    feet_to_metres,
    kilometres_to_nautical_miles,
    knots_to_kmh,
)


def _altitude(item: PositionedAircraft, units: str) -> str:
    aircraft = item.aircraft
    if aircraft.ground:
        return "GROUND"
    altitude = aircraft.altitude_baro_ft
    if altitude is None:
        altitude = aircraft.altitude_geom_ft
    if altitude is None:
        return "-"
    if units == "metric":
        return f"{feet_to_metres(altitude):.0f} m"
    return f"{altitude} ft"


def _speed(item: PositionedAircraft, units: str) -> str:
    speed = item.aircraft.ground_speed_kt
    if speed is None:
        return "-"
    if units == "metric":
        return f"{knots_to_kmh(speed):.0f} km/h"
    return f"{speed:.0f} kt"


def _distance(item: PositionedAircraft, units: str) -> str:
    if units == "metric":
        return f"{item.distance_km:.1f} km"
    return f"{kilometres_to_nautical_miles(item.distance_km):.1f} nm"


def render_snapshot(
    *,
    source_name: str,
    source_location: str,
    receiver_lat: float,
    receiver_lon: float,
    total: int,
    with_position: int,
    displayed: tuple[PositionedAircraft, ...],
    units: str,
) -> str:
    lines = [
        f"ANSIRadar {__version__}",
        "",
        "Receiver",
        f"  Latitude:          {receiver_lat:.6f}",
        f"  Longitude:         {receiver_lon:.6f}",
        f"  Source:            {source_name} ({source_location})",
        "",
        "Aircraft",
        f"  Visible:           {total}",
        f"  With position:     {with_position}",
        f"  Without position:  {total - with_position}",
        f"  Displayed:         {len(displayed)}",
        "",
        f"{'CALL':<10} {'ICAO':<8} {'ALT':<10} {'SPD':<9} "
        f"{'HDG':<5} {'DIST':<9} {'BRG':<5} {'AGE':<6}",
    ]
    for item in displayed:
        aircraft = item.aircraft
        callsign = (aircraft.callsign or "-")[:10]
        heading = (
            "-" if aircraft.track_deg is None else f"{aircraft.track_deg % 360:03.0f}"
        )
        age = (
            "-"
            if aircraft.seen_pos_seconds is None
            else f"{aircraft.seen_pos_seconds:.0f}s"
        )
        lines.append(
            f"{callsign:<10} {aircraft.icao[:8]:<8} {_altitude(item, units):<10} "
            f"{_speed(item, units):<9} {heading:<5} {_distance(item, units):<9} "
            f"{item.bearing_deg:03.0f}  {age:<6}"
        )
    return "\n".join(lines) + "\n"
