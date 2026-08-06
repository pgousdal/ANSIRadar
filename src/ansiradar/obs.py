"""Canonical aircraft observation model independent of decoder formats."""

from collections.abc import Callable
from dataclasses import dataclass

from ansiradar.models import Aircraft, AircraftSnapshot
from ansiradar.radar.geo import coordinates_valid
from ansiradar.sanity import normalize_callsign, normalize_icao, sanitize_text


@dataclass(frozen=True, slots=True)
class AircraftObservation:
    """A single normalized observation of one aircraft at one point in time.

    All optional fields default to ``None`` so that *missing* is distinguishable
    from a numeric zero, and no value is ever invented when the decoder did not
    provide it. Coordinates and rates are validated during construction.
    """

    icao: str
    timestamp: float
    source: str
    observer_timestamp: float | None = None
    callsign: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_baro_ft: int | None = None
    altitude_geom_ft: int | None = None
    on_ground: bool | None = None
    ground_speed_kt: float | None = None
    track_deg: float | None = None
    vertical_rate_fpm: int | None = None
    squawk: str | None = None
    category: str | None = None
    emergency: str | None = None
    seen_seconds: float | None = None
    seen_pos_seconds: float | None = None
    message_count: int | None = None
    rssi_dbfs: float | None = None


@dataclass(frozen=True, slots=True)
class ObservationSnapshot:
    """A normalized snapshot of multiple observations at one moment."""

    generated_at: float | None
    source: str
    observations: tuple[AircraftObservation, ...]
    messages: int | None = None
    skipped: int = 0
    raw_metadata: object = None


def snapshot_to_aircraft_snapshot(snapshot: ObservationSnapshot) -> AircraftSnapshot:
    """Bridge the normalized observation model to the legacy render model."""
    aircraft = tuple(
        Aircraft(
            icao=observation.icao,
            callsign=observation.callsign,
            latitude=observation.latitude,
            longitude=observation.longitude,
            altitude_baro_ft=observation.altitude_baro_ft,
            altitude_geom_ft=observation.altitude_geom_ft,
            ground=bool(observation.on_ground or False),
            ground_speed_kt=observation.ground_speed_kt,
            track_deg=observation.track_deg,
            vertical_rate_fpm=observation.vertical_rate_fpm,
            squawk=observation.squawk,
            category=observation.category,
            emergency=observation.emergency,
            seen_seconds=observation.seen_seconds,
            seen_pos_seconds=observation.seen_pos_seconds,
            messages=observation.message_count,
            rssi_dbfs=observation.rssi_dbfs,
        )
        for observation in snapshot.observations
    )
    return AircraftSnapshot(
        source_name=snapshot.source,
        generated_at=snapshot.generated_at,
        messages=snapshot.messages,
        aircraft=aircraft,
    )


def parse_number(value: object) -> float | None:
    """Return a finite float for numeric input, else None.

    Booleans, NaN, and infinities are rejected so they are never accepted as
    coordinates or rates.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            number = float(stripped)
        except ValueError:
            return None
    else:
        return None
    import math

    return number if math.isfinite(number) else None


def parse_integer(value: object) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def build_observation(
    *,
    icao: object,
    timestamp: float,
    source: str,
    callsign: object = None,
    latitude: object = None,
    longitude: object = None,
    altitude_baro_ft: object = None,
    altitude_geom_ft: object = None,
    on_ground: bool | None = None,
    ground_speed_kt: object = None,
    track_deg: object = None,
    vertical_rate_fpm: object = None,
    squawk: object = None,
    category: object = None,
    emergency: object = None,
    seen_seconds: object = None,
    seen_pos_seconds: object = None,
    message_count: object = None,
    rssi_dbfs: object = None,
    observer_timestamp: float | None = None,
) -> AircraftObservation | None:
    """Build a validated observation, returning None for an unusable record."""
    code = normalize_icao(icao)
    if code is None:
        return None
    lat = parse_number(latitude)
    lon = parse_number(longitude)
    if lat is None or lon is None or not coordinates_valid(lat, lon):
        lat, lon = None, None
    return AircraftObservation(
        icao=code,
        timestamp=timestamp,
        source=source,
        observer_timestamp=observer_timestamp,
        callsign=normalize_callsign(callsign),
        latitude=lat,
        longitude=lon,
        altitude_baro_ft=parse_integer(altitude_baro_ft),
        altitude_geom_ft=parse_integer(altitude_geom_ft),
        on_ground=on_ground,
        ground_speed_kt=parse_number(ground_speed_kt),
        track_deg=parse_number(track_deg),
        vertical_rate_fpm=parse_integer(vertical_rate_fpm),
        squawk=sanitize_text(squawk) or None,
        category=normalize_callsign(category),
        emergency=normalize_callsign(emergency),
        seen_seconds=parse_number(seen_seconds),
        seen_pos_seconds=parse_number(seen_pos_seconds),
        message_count=parse_integer(message_count),
        rssi_dbfs=parse_number(rssi_dbfs),
    )


def now_clock() -> float:
    """The default real-time clock used when no injectable clock is provided."""
    import time

    return time.time()


Clock = Callable[[], float]
