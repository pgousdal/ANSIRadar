"""Tests for observation normalization and sanitization."""

import math

from ansiradar.obs import build_observation, parse_number
from ansiradar.sanity import normalize_icao, sanitize_text


def test_icao_normalization() -> None:
    assert normalize_icao("  abC123 ") == "ABC123"
    assert normalize_icao("ffffff") == "FFFFFF"
    assert normalize_icao("ABC12") is None  # too short
    assert normalize_icao("XYZ123") is None  # non-hex
    assert normalize_icao(123) is None
    assert normalize_icao(None) is None


def test_icao_case_and_mixed() -> None:
    obs = build_observation(icao=" 8a0b1c ", timestamp=0.0, source="file", callsign="X")
    assert obs is not None
    assert obs.icao == "8A0B1C"


def test_callsign_normalization() -> None:
    obs = build_observation(
        icao="abc123", timestamp=0.0, source="file", callsign="  SAS   431  "
    )
    assert obs is not None
    assert obs.callsign == "SAS 431"


def test_callsign_control_chars_stripped() -> None:
    obs = build_observation(
        icao="abc123", timestamp=0.0, source="file", callsign="BAD\x1b[31mESC"
    )
    assert obs is not None
    assert obs.callsign is not None
    assert "\x1b" not in obs.callsign
    assert "ESC" in obs.callsign


def test_coordinate_validation() -> None:
    good = build_observation(
        icao="abc123", timestamp=0.0, source="file", latitude=58.4, longitude=6.3
    )
    assert good is not None
    assert good.latitude == 58.4
    bad = build_observation(
        icao="abc123", timestamp=0.0, source="file", latitude=91.0, longitude=0.0
    )
    assert bad is not None
    assert bad.latitude is None and bad.longitude is None


def test_nan_and_infinity_rejected() -> None:
    assert parse_number(math.nan) is None
    assert parse_number(float("inf")) is None
    assert parse_number(float("-inf")) is None
    obs = build_observation(
        icao="abc123",
        timestamp=0.0,
        source="file",
        latitude=math.nan,
        longitude=float("inf"),
        ground_speed_kt=math.nan,
    )
    assert obs is not None
    assert obs.latitude is None
    assert obs.ground_speed_kt is None


def test_missing_vs_zero() -> None:
    zero = build_observation(
        icao="abc123",
        timestamp=0.0,
        source="file",
        ground_speed_kt=0,
        message_count=0,
    )
    assert zero is not None
    assert zero.ground_speed_kt == 0.0  # explicit zero is preserved
    assert zero.message_count == 0
    missing = build_observation(icao="abc123", timestamp=0.0, source="file")
    assert missing is not None
    assert missing.ground_speed_kt is None  # absent is distinct from zero
    assert missing.message_count is None


def test_ground_state_distinct_from_altitude() -> None:
    ground = build_observation(
        icao="abc123", timestamp=0.0, source="file", on_ground=True
    )
    assert ground is not None
    assert ground.on_ground is True
    airborne = build_observation(
        icao="abc123",
        timestamp=0.0,
        source="file",
        on_ground=False,
        altitude_baro_ft=9000,
    )
    assert airborne is not None
    assert airborne.on_ground is False
    assert airborne.altitude_baro_ft == 9000
    unknown = build_observation(icao="abc123", timestamp=0.0, source="file")
    assert unknown is not None
    assert unknown.on_ground is None


def test_altitude_field_distinction() -> None:
    both = build_observation(
        icao="abc123",
        timestamp=0.0,
        source="file",
        altitude_baro_ft=37000,
        altitude_geom_ft=37200,
    )
    assert both is not None
    assert both.altitude_baro_ft == 37000
    assert both.altitude_geom_ft == 37200
    baro_only = build_observation(
        icao="abc123", timestamp=0.0, source="file", altitude_baro_ft=1000
    )
    assert baro_only is not None
    assert baro_only.altitude_baro_ft == 1000
    assert baro_only.altitude_geom_ft is None


def test_sanitize_text_strips_ansi() -> None:
    assert sanitize_text("a\x1b[31mb") == "ab"
    assert sanitize_text("  hi   there  ") == "hi there"
    assert "\x07" not in sanitize_text("ring\x07")
    assert sanitize_text(None) == ""


def test_bool_numbers_rejected() -> None:
    assert parse_number(True) is None
    assert parse_number(False) is None
