import pytest

from ansiradar.radar.geo import coordinates_valid, distance_km, initial_bearing_deg
from ansiradar.units import (
    feet_per_minute_to_metres_per_second,
    feet_to_metres,
    kilometres_to_nautical_miles,
    knots_to_kmh,
)


def test_known_distance_and_bearing() -> None:
    assert distance_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.01)
    assert initial_bearing_deg(0, 0, 0, 1) == pytest.approx(90)
    assert initial_bearing_deg(0, 0, -1, 0) == pytest.approx(180)


def test_coordinate_validation() -> None:
    assert coordinates_valid(90, -180)
    assert not coordinates_valid(91, 0)
    assert not coordinates_valid(0, float("nan"))
    with pytest.raises(ValueError):
        distance_km(91, 0, 0, 0)


def test_unit_conversions() -> None:
    assert feet_to_metres(1000) == pytest.approx(304.8)
    assert knots_to_kmh(100) == pytest.approx(185.2)
    assert kilometres_to_nautical_miles(1.852) == pytest.approx(1)
    assert feet_per_minute_to_metres_per_second(1000) == pytest.approx(5.08)
