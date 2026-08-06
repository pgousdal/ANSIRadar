"""Deterministic radar application engine tying sources to tracks and rendering."""

from dataclasses import dataclass

from ansiradar.models import PositionedAircraft
from ansiradar.obs import ObservationSnapshot
from ansiradar.poller import SourcePoller, SourceStatus
from ansiradar.radar.geo import distance_km, initial_bearing_deg
from ansiradar.tracking import TrackManager, TrackSnapshot, TrackSummary


@dataclass(frozen=True, slots=True)
class RadarFrame:
    """Everything the renderer needs for one frame plus status data."""

    items: tuple[PositionedAircraft, ...]
    positioned_count: int
    track_summary: TrackSummary
    source_status: SourceStatus


class RadarEngine:
    """Owns the poller and track manager and produces render-ready frames."""

    def __init__(
        self,
        poller: SourcePoller,
        tracks: TrackManager,
        *,
        receiver_lat: float,
        receiver_lon: float,
        max_age: float = 0.0,
    ) -> None:
        self.poller = poller
        self.tracks = tracks
        self.receiver_lat = receiver_lat
        self.receiver_lon = receiver_lon
        self.max_age = max_age
        self._last_applied: ObservationSnapshot | None = None

    def step(self) -> None:
        self.poller.step()
        snapshot = self.poller.last_snapshot()
        if snapshot is not None and snapshot is not self._last_applied:
            self.tracks.apply(snapshot)
            self._last_applied = snapshot

    def apply_manual(self, snapshot: ObservationSnapshot) -> None:
        self.tracks.apply(snapshot)
        self._last_applied = snapshot

    def last_snapshot(self) -> ObservationSnapshot | None:
        return self.poller.last_snapshot()

    def now(self) -> float:
        return self.tracks.clock()

    def _positioned_from_tracks(
        self, snapshots: tuple[TrackSnapshot, ...]
    ) -> tuple[PositionedAircraft, ...]:
        items: list[PositionedAircraft] = []
        for item in snapshots:
            if not item.active or item.position_stale:
                continue
            aircraft = item.aircraft
            if aircraft.latitude is None or aircraft.longitude is None:
                continue
            if self.max_age > 0 and aircraft.seen_pos_seconds is not None:
                if aircraft.seen_pos_seconds > self.max_age:
                    continue
            items.append(
                PositionedAircraft(
                    aircraft=aircraft,
                    distance_km=distance_km(
                        self.receiver_lat,
                        self.receiver_lon,
                        aircraft.latitude,
                        aircraft.longitude,
                    ),
                    bearing_deg=initial_bearing_deg(
                        self.receiver_lat,
                        self.receiver_lon,
                        aircraft.latitude,
                        aircraft.longitude,
                    ),
                )
            )
        return tuple(items)

    def frame(self) -> RadarFrame:
        snapshots = self.tracks.snapshot()
        items = self._positioned_from_tracks(snapshots)
        positioned_count = sum(
            1
            for item in snapshots
            if item.active
            and not item.position_stale
            and item.aircraft.latitude is not None
        )
        return RadarFrame(
            items=items,
            positioned_count=positioned_count,
            track_summary=self.tracks.summary(),
            source_status=self.poller.status(),
        )
