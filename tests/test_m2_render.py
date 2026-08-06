from ansiradar.models import Aircraft, PositionedAircraft
from ansiradar.radar.projection import project_polar
from ansiradar.radar.trails import TrailPoint, TrailStore
from ansiradar.render.ansi import serialize_diff
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import render_radar


def test_cardinal_projection() -> None:
    north = project_polar(0, 50, 100, 40, 10, 20, 8)
    east = project_polar(90, 50, 100, 40, 10, 20, 8)
    south = project_polar(180, 50, 100, 40, 10, 20, 8)
    west = project_polar(270, 50, 100, 40, 10, 20, 8)
    assert (north.x, north.y) == (40, 6)
    assert (east.x, east.y) == (50, 10)
    assert (south.x, south.y) == (40, 14)
    assert (west.x, west.y) == (30, 10)
    assert not project_polar(0, 101, 100, 0, 0, 1, 1).in_range


def test_buffer_clipping_and_diff() -> None:
    buffer = ScreenBuffer(5, 2)
    buffer.draw_text(-2, 0, "abcdef")
    assert buffer.serialize().splitlines()[0] == "cdef "
    assert "\x1b[2J" in serialize_diff(buffer, None)
    changed = ScreenBuffer(5, 2)
    changed.draw_text(0, 0, "hello")
    delta = serialize_diff(changed, buffer)
    assert "h" in delta


def test_radar_ascii_is_deterministic_and_size_safe() -> None:
    item = PositionedAircraft(Aircraft("ABC123", "TEST", 58.4, 6.3), 5, 90)
    first = render_radar((item,), width=80, height=24)
    second = render_radar((item,), width=80, height=24)
    assert first.serialize() == second.serialize()
    assert "ANSIRadar 0.5.0" in first.serialize()
    assert "+" in first.serialize()
    tiny = render_radar((item,), width=20, height=10)
    assert "too sma" in tiny.serialize()


def test_trails_are_strictly_bounded() -> None:
    trails = TrailStore(length=2, max_aircraft=1)
    trails.add(TrailPoint("A", 1, 1, 1))
    trails.add(TrailPoint("A", 2, 2, 2))
    trails.add(TrailPoint("A", 3, 3, 3))
    trails.add(TrailPoint("B", 4, 4, 4))
    assert len(trails) == 1
    assert trails.get("A") == ()
