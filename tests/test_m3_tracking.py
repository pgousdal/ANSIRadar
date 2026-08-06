"""Tests for the track manager's upsert, retention, staleness, and bounds."""

from ansiradar.obs import AircraftObservation, ObservationSnapshot, build_observation
from ansiradar.tracking import TrackManager


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def snapshot(
    clock: FakeClock, *observations: AircraftObservation
) -> ObservationSnapshot:
    return ObservationSnapshot(
        generated_at=clock.now, source="file", observations=tuple(observations)
    )


def make(
    icao: str,
    time: float,
    *,
    lat: float | None = None,
    lon: float | None = None,
    callsign: str | None = None,
    alt: int | None = None,
    speed: float | None = None,
    track: float | None = None,
    ground: bool | None = None,
    emergency: str | None = None,
) -> AircraftObservation:
    obs = build_observation(
        icao=icao,
        timestamp=time,
        source="file",
        callsign=callsign,
        latitude=lat,
        longitude=lon,
        altitude_baro_ft=alt,
        ground_speed_kt=speed,
        track_deg=track,
        on_ground=ground,
        emergency=emergency,
    )
    assert obs is not None
    return obs


def test_first_observation() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 0.0, lat=1, lon=2)))
    result = manager.snapshot()
    assert len(result) == 1
    assert result[0].icao == "ABC123"
    assert result[0].active


def test_update_moves_aircraft() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 0.0, lat=1, lon=2, callsign="A")))
    clock.advance(10)
    manager.apply(snapshot(clock, make("ABC123", 10.0, lat=2, lon=3)))
    result = manager.snapshot()
    assert len(result) == 1
    assert (result[0].aircraft.latitude, result[0].aircraft.longitude) == (2.0, 3.0)
    assert result[0].aircraft.callsign == "A"  # retained when omitted


def test_omitted_field_retention() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 0.0, alt=9000, speed=250)))
    clock.advance(5)
    manager.apply(snapshot(clock, make("ABC123", 5.0, alt=9100)))
    result = manager.snapshot()
    assert result[0].aircraft.altitude_baro_ft == 9100
    assert result[0].aircraft.ground_speed_kt == 250  # retained


def test_explicit_replacement() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 0.0, callsign="OLD")))
    manager.apply(snapshot(clock, make("ABC123", 1.0, callsign="NEW")))
    assert manager.snapshot()[0].aircraft.callsign == "NEW"


def test_callsign_change_keeps_same_track() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 0.0, callsign="AAA")))
    manager.apply(snapshot(clock, make("ABC123", 1.0, callsign="BBB")))
    result = manager.snapshot()
    assert len(result) == 1  # not a new aircraft
    assert result[0].first_seen == 0.0
    assert result[0].aircraft.callsign == "BBB"


def test_position_staleness() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock, position_stale_age=30, aircraft_stale_age=60)
    manager.apply(snapshot(clock, make("ABC123", 0.0, lat=1, lon=2)))
    clock.advance(40)
    result = manager.snapshot()
    assert result[0].position_stale
    assert result[0].aircraft.latitude is None  # position hidden
    assert result[0].active  # aircraft still seen recently? no: 40<60 so active


def test_aircraft_staleness_but_not_removed() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock, aircraft_stale_age=60, removal_age=120)
    manager.apply(snapshot(clock, make("ABC123", 0.0, lat=1, lon=2)))
    clock.advance(80)
    result = manager.snapshot()
    assert not result[0].active
    assert len(result) == 1  # not removed yet


def test_removal_after_removal_age() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock, removal_age=120)
    manager.apply(snapshot(clock, make("ABC123", 0.0)))
    clock.advance(121)
    assert manager.snapshot() == ()


def test_out_of_order_updates_ignored() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    manager.apply(snapshot(clock, make("ABC123", 10.0, callsign="NEWER")))
    manager.apply(snapshot(clock, make("ABC123", 5.0, callsign="OLDER")))
    assert manager.snapshot()[0].aircraft.callsign == "NEWER"


def test_emergency_does_not_persist() -> None:
    clock = FakeClock()
    manager = TrackManager(
        clock=clock, emergency_retention_age=30, aircraft_stale_age=200
    )
    manager.apply(snapshot(clock, make("ABC123", 0.0, emergency="general")))
    assert manager.snapshot()[0].aircraft.emergency == "general"
    clock.advance(31)
    result = manager.snapshot()
    assert result[0].aircraft.emergency is None
    # A non-emergency observation clears it immediately.
    manager.apply(snapshot(clock, make("ABC123", 31.0, emergency="none")))
    assert manager.snapshot()[0].aircraft.emergency is None


def test_emergency_expires_while_position_remains_fresh() -> None:
    clock = FakeClock()
    manager = TrackManager(
        clock=clock, emergency_retention_age=30, position_stale_age=60
    )
    manager.apply(
        snapshot(clock, make("ABC123", 0.0, lat=1, lon=2, emergency="general"))
    )
    clock.advance(31)
    manager.apply(snapshot(clock, make("ABC123", 31.0, lat=1.1, lon=2.1)))
    result = manager.snapshot()
    assert result[0].aircraft.latitude == 1.1
    assert result[0].aircraft.emergency is None


def test_bounded_track_count() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock, max_tracks=2)
    manager.apply(snapshot(clock, make("AAAAAA", 0.0)))
    manager.apply(snapshot(clock, make("BBBBBB", 1.0)))
    manager.apply(snapshot(clock, make("CCCCCC", 2.0)))
    assert len(manager) == 2
    assert {item.icao for item in manager.snapshot()} == {"BBBBBB", "CCCCCC"}


def test_deterministic_sorting() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    for icao in ("CCCCCC", "AAAAAA", "BBBBBB"):
        manager.apply(snapshot(clock, make(icao, clock.now)))
    assert [item.icao for item in manager.snapshot()] == ["AAAAAA", "BBBBBB", "CCCCCC"]
    assert [item.icao for item in manager.snapshot()] == ["AAAAAA", "BBBBBB", "CCCCCC"]


def test_summary_counts() -> None:
    clock = FakeClock()
    manager = TrackManager(
        clock=clock, position_stale_age=30, aircraft_stale_age=60, removal_age=120
    )
    manager.apply(snapshot(clock, make("AAAAAA", 0.0, lat=1, lon=2)))
    manager.apply(snapshot(clock, make("BBBBBB", 0.0, lat=3, lon=4)))
    manager.apply(snapshot(clock, make("CCCCCC", 0.0, lat=5, lon=6)))
    clock.advance(40)  # all positions now stale but aircraft active
    summary = manager.summary()
    assert summary.active == 3
    assert summary.positioned == 0
    assert summary.stale_positions == 3


def test_apply_returns_accepted_count() -> None:
    clock = FakeClock()
    manager = TrackManager(clock=clock)
    assert manager.apply(snapshot(clock, make("AAAAAA", 5.0))) == 1
    assert manager.apply(snapshot(clock, make("AAAAAA", 3.0))) == 0  # out of order
