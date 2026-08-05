"""Dependency-free great-circle calculations."""

import math

EARTH_RADIUS_KM = 6371.0088


def coordinates_valid(latitude: object, longitude: object) -> bool:
    return (
        isinstance(latitude, (int, float))
        and not isinstance(latitude, bool)
        and isinstance(longitude, (int, float))
        and not isinstance(longitude, bool)
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90.0 <= latitude <= 90.0
        and -180.0 <= longitude <= 180.0
    )


def _validate(lat1: float, lon1: float, lat2: float, lon2: float) -> None:
    if not coordinates_valid(lat1, lon1) or not coordinates_valid(lat2, lon2):
        raise ValueError("latitude must be -90..90 and longitude -180..180")


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    _validate(lat1, lon1, lat2, lon2)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * (
        math.sin(dlambda / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    _validate(lat1, lon1, lat2, lon2)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(
        dlambda
    )
    return math.degrees(math.atan2(y, x)) % 360.0
