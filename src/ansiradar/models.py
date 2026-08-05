"""Immutable domain models used by source adapters and renderers."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class Aircraft:
    icao: str
    callsign: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    altitude_baro_ft: int | None = None
    altitude_geom_ft: int | None = None
    ground: bool = False
    ground_speed_kt: float | None = None
    track_deg: float | None = None
    vertical_rate_fpm: int | None = None
    squawk: str | None = None
    category: str | None = None
    emergency: str | None = None
    seen_seconds: float | None = None
    seen_pos_seconds: float | None = None
    messages: int | None = None
    rssi_dbfs: float | None = None


@dataclass(frozen=True, slots=True)
class AircraftSnapshot:
    source_name: str
    generated_at: float | None
    messages: int | None
    aircraft: tuple[Aircraft, ...]
    raw_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True, slots=True)
class PositionedAircraft:
    aircraft: Aircraft
    distance_km: float
    bearing_deg: float
