"""Normalization of readsb/dump1090/tar1090 aircraft JSON into observations."""

from ansiradar.obs import (
    AircraftObservation,
    ObservationSnapshot,
    build_observation,
    parse_integer,
    parse_number,
)
from ansiradar.sources.base import InvalidSourceData, UnsupportedSource


class DecodeResult:
    """A normalized snapshot plus parser diagnostics."""

    def __init__(self, snapshot: ObservationSnapshot, skipped: int) -> None:
        self.snapshot = snapshot
        self.skipped = skipped


def _ground_alt(record: object) -> tuple[bool | None, object]:
    """Return on-ground state and barometric altitude input."""
    if not isinstance(record, dict):
        return False, None
    alt = record.get("alt_baro")
    if isinstance(alt, str) and alt.strip().lower() == "ground":
        return True, None
    if alt is not None or record.get("alt_geom") is not None:
        return False, alt
    return None, alt


def parse_aircraft_json(
    payload: object,
    *,
    timestamp: float,
    source: str,
    max_aircraft: int,
) -> DecodeResult:
    """Normalize a decoder ``aircraft.json`` document.

    A malformed top-level document raises ``InvalidSourceData`` or
    ``UnsupportedSource``. A malformed individual aircraft record is skipped and
    counted instead of invalidating the whole snapshot.
    """
    if not isinstance(payload, dict):
        raise UnsupportedSource("top-level JSON value must be an object")
    records = payload.get("aircraft")
    if not isinstance(records, list):
        raise UnsupportedSource("decoder JSON requires an aircraft array")

    observations: list[AircraftObservation] = []
    skipped = 0
    for record in records[:max_aircraft]:
        if not isinstance(record, dict):
            skipped += 1
            continue
        icao = record.get("hex")
        if icao is None:
            icao = record.get("icao")
        if icao is None:
            skipped += 1
            continue
        on_ground, baro_alt = _ground_alt(record)
        baro_rate = parse_number(record.get("baro_rate"))
        geom_rate = parse_number(record.get("geom_rate"))
        vertical_rate = baro_rate if baro_rate is not None else geom_rate
        observation = build_observation(
            icao=icao,
            timestamp=timestamp,
            source=source,
            callsign=record.get("flight"),
            latitude=record.get("lat"),
            longitude=record.get("lon"),
            altitude_baro_ft=baro_alt,
            altitude_geom_ft=record.get("alt_geom"),
            on_ground=on_ground,
            ground_speed_kt=record.get("gs"),
            track_deg=record.get("track"),
            vertical_rate_fpm=vertical_rate,
            squawk=record.get("squawk"),
            category=record.get("category"),
            emergency=record.get("emergency"),
            seen_seconds=record.get("seen"),
            seen_pos_seconds=record.get("seen_pos"),
            message_count=record.get("messages"),
            rssi_dbfs=record.get("rssi"),
            observer_timestamp=parse_number(payload.get("now")),
        )
        if observation is None:
            skipped += 1
            continue
        observations.append(observation)

    snapshot = ObservationSnapshot(
        generated_at=parse_number(payload.get("now")),
        source=source,
        observations=tuple(observations),
        messages=parse_integer(payload.get("messages")),
        skipped=skipped,
        raw_metadata={
            key: value for key, value in payload.items() if key != "aircraft"
        },
    )
    return DecodeResult(snapshot, skipped)


def decoder_error(payload_error: Exception) -> Exception:
    """Wrap an arbitrary decoding failure as a classifiable source error."""
    if isinstance(payload_error, (InvalidSourceData, UnsupportedSource)):
        return payload_error
    return InvalidSourceData(
        f"decoder payload could not be normalized: {payload_error}"
    )
