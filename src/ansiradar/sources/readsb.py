"""readsb/dump1090 aircraft.json source adapter."""

import json
import math
from pathlib import Path
from types import MappingProxyType
from urllib.parse import unquote, urlparse

import httpx

from ansiradar.models import Aircraft, AircraftSnapshot
from ansiradar.radar.geo import coordinates_valid
from ansiradar.sources.base import (
    InvalidSourceData,
    SourceUnavailable,
    UnsupportedSource,
)


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _aircraft(record: object) -> Aircraft | None:
    if not isinstance(record, dict):
        return None
    icao = _text(record.get("hex"))
    if icao is None:
        return None
    icao = icao.upper()
    lat, lon = _number(record.get("lat")), _number(record.get("lon"))
    if lat is None or lon is None or not coordinates_valid(lat, lon):
        lat, lon = None, None
    alt_raw = record.get("alt_baro")
    ground = isinstance(alt_raw, str) and alt_raw.strip().lower() == "ground"
    baro_rate = _integer(record.get("baro_rate"))
    geom_rate = _integer(record.get("geom_rate"))
    return Aircraft(
        icao=icao,
        callsign=_text(record.get("flight")),
        latitude=lat,
        longitude=lon,
        altitude_baro_ft=None if ground else _integer(alt_raw),
        altitude_geom_ft=_integer(record.get("alt_geom")),
        ground=ground,
        ground_speed_kt=_number(record.get("gs")),
        track_deg=_number(record.get("track")),
        vertical_rate_fpm=baro_rate if baro_rate is not None else geom_rate,
        squawk=_text(record.get("squawk")),
        category=_text(record.get("category")),
        emergency=_text(record.get("emergency")),
        seen_seconds=_number(record.get("seen")),
        seen_pos_seconds=_number(record.get("seen_pos")),
        messages=_integer(record.get("messages")),
        rssi_dbfs=_number(record.get("rssi")),
    )


def parse_readsb(payload: object) -> AircraftSnapshot:
    if not isinstance(payload, dict):
        raise UnsupportedSource("top-level JSON value must be an object")
    records = payload.get("aircraft")
    if not isinstance(records, list):
        raise UnsupportedSource("readsb JSON requires an aircraft array")
    aircraft = tuple(item for record in records if (item := _aircraft(record)))
    metadata = {key: value for key, value in payload.items() if key != "aircraft"}
    return AircraftSnapshot(
        source_name="readsb JSON",
        generated_at=_number(payload.get("now")),
        messages=_integer(payload.get("messages")),
        aircraft=aircraft,
        raw_metadata=MappingProxyType(metadata),
    )


class ReadsbSource:
    """One-shot HTTP or local-file reader for aircraft.json."""

    def __init__(self, location: str, *, timeout: float = 10.0) -> None:
        self.location = location
        self.timeout = timeout

    def _read(self) -> str:
        parsed = urlparse(self.location)
        if parsed.scheme in {"http", "https"}:
            try:
                response = httpx.get(self.location, timeout=self.timeout)
                response.raise_for_status()
            except httpx.HTTPError as error:
                raise SourceUnavailable(
                    f"cannot read {self.location}: {error}"
                ) from error
            return response.text
        if parsed.scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise UnsupportedSource("remote file URLs are not supported")
            path = Path(unquote(parsed.path))
        elif parsed.scheme:
            raise UnsupportedSource(f"unsupported source protocol: {parsed.scheme}")
        else:
            path = Path(self.location)
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SourceUnavailable(f"cannot read {path}: {error}") from error

    def fetch(self) -> AircraftSnapshot:
        try:
            payload = json.loads(self._read())
        except json.JSONDecodeError as error:
            raise InvalidSourceData(
                f"invalid JSON at line {error.lineno}, column {error.colno}"
            ) from error
        return parse_readsb(payload)
