"""Explicit display-unit conversions."""

FT_TO_M = 0.3048
KT_TO_KMH = 1.852
KM_TO_NM = 0.539956803
FPM_TO_MPS = 0.00508


def feet_to_metres(value: float) -> float:
    return value * FT_TO_M


def knots_to_kmh(value: float) -> float:
    return value * KT_TO_KMH


def kilometres_to_nautical_miles(value: float) -> float:
    return value * KM_TO_NM


def feet_per_minute_to_metres_per_second(value: float) -> float:
    return value * FPM_TO_MPS
