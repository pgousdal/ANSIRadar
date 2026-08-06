"""Track management between normalized observations and radar rendering.

Tracks are upserted by normalized ICAO address. Fields omitted by a later
observation are retained briefly; positions age independently of aircraft
staleness; out-of-order observations never replace newer state; and memory is
bounded by both track count and removal age.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from ansiradar.models import Aircraft
from ansiradar.obs import AircraftObservation, ObservationSnapshot, now_clock

DEFAULT_POSITION_STALE_AGE = 30.0
DEFAULT_AIRCRAFT_STALE_AGE = 60.0
DEFAULT_REMOVAL_AGE = 120.0
DEFAULT_EMERGENCY_RETENTION_AGE = 60.0
DEFAULT_MAX_TRACKS = 200


@dataclass
class Track:
    icao: str
    first_seen: float
    last_seen: float
    last_pos_time: float | None
    emergency_time: float | None
    aircraft: Aircraft


@dataclass(frozen=True, slots=True)
class TrackSnapshot:
    """A deterministic, render-ready view of one track at one point in time."""

    icao: str
    aircraft: Aircraft
    first_seen: float
    last_seen: float
    last_pos_time: float | None
    active: bool
    position_stale: bool


@dataclass(frozen=True, slots=True)
class TrackSummary:
    """Deterministic aggregate counts exposed to the status area."""

    active: int
    positioned: int
    stale_positions: int
    total: int


class TrackManager:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = now_clock,
        position_stale_age: float = DEFAULT_POSITION_STALE_AGE,
        aircraft_stale_age: float = DEFAULT_AIRCRAFT_STALE_AGE,
        removal_age: float = DEFAULT_REMOVAL_AGE,
        emergency_retention_age: float = DEFAULT_EMERGENCY_RETENTION_AGE,
        max_tracks: int = DEFAULT_MAX_TRACKS,
    ) -> None:
        self.clock = clock
        self.position_stale_age = position_stale_age
        self.aircraft_stale_age = aircraft_stale_age
        self.removal_age = removal_age
        self.emergency_retention_age = emergency_retention_age
        self.max_tracks = max(1, max_tracks)
        self._tracks: dict[str, Track] = {}
        self._last_update: float | None = None

    def apply(self, snapshot: ObservationSnapshot) -> int:
        """Upsert observations; returns the number of accepted updates."""
        accepted = 0
        for observation in snapshot.observations:
            if self._merge(observation):
                accepted += 1
        self._last_update = self.clock()
        return accepted

    def _merge(self, observation: AircraftObservation) -> bool:
        existing = self._tracks.get(observation.icao)
        if existing is None:
            if len(self._tracks) >= self.max_tracks:
                self._evict_oldest()
            self._tracks[observation.icao] = self._new_track(observation)
            return True
        if observation.timestamp < existing.last_seen:
            return False
        self._tracks[observation.icao] = self._merged(existing, observation)
        return True

    def _new_track(self, observation: AircraftObservation) -> Track:
        aircraft = _to_aircraft(observation)
        return Track(
            icao=observation.icao,
            first_seen=observation.timestamp,
            last_seen=observation.timestamp,
            last_pos_time=(
                observation.timestamp if observation.latitude is not None else None
            ),
            emergency_time=(
                observation.timestamp if _is_emergency(observation.emergency) else None
            ),
            aircraft=aircraft,
        )

    def _merged(self, existing: Track, observation: AircraftObservation) -> Track:
        old = existing.aircraft
        aircraft = Aircraft(
            icao=observation.icao,
            callsign=_retain(old.callsign, observation.callsign),
            latitude=_retain(old.latitude, observation.latitude),
            longitude=_retain(old.longitude, observation.longitude),
            altitude_baro_ft=_retain(
                old.altitude_baro_ft, observation.altitude_baro_ft
            ),
            altitude_geom_ft=_retain(
                old.altitude_geom_ft, observation.altitude_geom_ft
            ),
            ground=_retain_ground(old.ground, observation.on_ground),
            ground_speed_kt=_retain(old.ground_speed_kt, observation.ground_speed_kt),
            track_deg=_retain(old.track_deg, observation.track_deg),
            vertical_rate_fpm=_retain(
                old.vertical_rate_fpm, observation.vertical_rate_fpm
            ),
            squawk=_retain(old.squawk, observation.squawk),
            category=_retain(old.category, observation.category),
            emergency=_retain_emergency(old.emergency, observation.emergency),
            seen_seconds=_retain(old.seen_seconds, observation.seen_seconds),
            seen_pos_seconds=_retain(
                old.seen_pos_seconds, observation.seen_pos_seconds
            ),
            messages=_retain(old.messages, observation.message_count),
            rssi_dbfs=_retain(old.rssi_dbfs, observation.rssi_dbfs),
        )
        last_pos_time = existing.last_pos_time
        if observation.latitude is not None:
            last_pos_time = observation.timestamp
        emergency_time = existing.emergency_time
        if observation.emergency is not None:
            emergency_time = (
                observation.timestamp if _is_emergency(observation.emergency) else None
            )
        return Track(
            icao=observation.icao,
            first_seen=existing.first_seen,
            last_seen=observation.timestamp,
            last_pos_time=last_pos_time,
            emergency_time=emergency_time,
            aircraft=aircraft,
        )

    def _evict_oldest(self) -> None:
        oldest_icao = min(self._tracks, key=lambda key: self._tracks[key].last_seen)
        del self._tracks[oldest_icao]

    def snapshot(self, now: float | None = None) -> tuple[TrackSnapshot, ...]:
        current = now if now is not None else self.clock()
        self._expire(current)
        result: list[TrackSnapshot] = []
        for icao in sorted(self._tracks):
            track = self._tracks[icao]
            active = current - track.last_seen <= self.aircraft_stale_age
            position_stale = (
                track.last_pos_time is None
                or current - track.last_pos_time > self.position_stale_age
            )
            aircraft = _apply_staleness(
                track.aircraft,
                current=current,
                position_stale=position_stale,
                emergency_expired=(
                    track.emergency_time is not None
                    and current - track.emergency_time > self.emergency_retention_age
                ),
            )
            result.append(
                TrackSnapshot(
                    icao=icao,
                    aircraft=aircraft,
                    first_seen=track.first_seen,
                    last_seen=track.last_seen,
                    last_pos_time=track.last_pos_time,
                    active=active,
                    position_stale=position_stale,
                )
            )
        return tuple(result)

    def summary(self, now: float | None = None) -> TrackSummary:
        snapshots = self.snapshot(now)
        active = sum(1 for item in snapshots if item.active)
        positioned = sum(
            1
            for item in snapshots
            if item.active
            and not item.position_stale
            and item.aircraft.latitude is not None
        )
        stale = sum(1 for item in snapshots if item.active and item.position_stale)
        return TrackSummary(
            active=active,
            positioned=positioned,
            stale_positions=stale,
            total=len(snapshots),
        )

    def _expire(self, now: float) -> None:
        expired = [
            icao
            for icao, track in self._tracks.items()
            if now - track.last_seen > self.removal_age
        ]
        for icao in expired:
            del self._tracks[icao]

    def __len__(self) -> int:
        return len(self._tracks)


def _is_emergency(value: str | None) -> bool:
    return bool(value and value.casefold() not in {"none", "-", ""})


_T = TypeVar("_T")


def _retain(old: _T | None, new: _T | None) -> _T | None:
    return new if new is not None else old


def _retain_ground(old: bool, new: bool | None) -> bool:
    return bool(new if new is not None else old)


def _retain_emergency(old: str | None, new: str | None) -> str | None:
    if new is not None:
        return new if _is_emergency(new) else None
    return old


def _to_aircraft(observation: AircraftObservation) -> Aircraft:
    return Aircraft(
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


def _apply_staleness(
    aircraft: Aircraft,
    *,
    current: float,
    position_stale: bool,
    emergency_expired: bool,
) -> Aircraft:
    if not position_stale and not emergency_expired:
        return aircraft
    return Aircraft(
        icao=aircraft.icao,
        callsign=aircraft.callsign,
        latitude=None if position_stale else aircraft.latitude,
        longitude=None if position_stale else aircraft.longitude,
        altitude_baro_ft=aircraft.altitude_baro_ft,
        altitude_geom_ft=aircraft.altitude_geom_ft,
        ground=aircraft.ground,
        ground_speed_kt=aircraft.ground_speed_kt,
        track_deg=aircraft.track_deg,
        vertical_rate_fpm=aircraft.vertical_rate_fpm,
        squawk=aircraft.squawk,
        category=aircraft.category,
        emergency=None if emergency_expired else aircraft.emergency,
        seen_seconds=aircraft.seen_seconds,
        seen_pos_seconds=aircraft.seen_pos_seconds,
        messages=aircraft.messages,
        rssi_dbfs=aircraft.rssi_dbfs,
    )
