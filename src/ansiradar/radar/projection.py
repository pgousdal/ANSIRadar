"""North-up polar projection for terminal character cells."""

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Projection:
    x: int
    y: int
    in_range: bool


def project_polar(
    bearing_deg: float,
    distance_nm: float,
    max_range_nm: float,
    center_x: float,
    center_y: float,
    horizontal_radius: float,
    vertical_radius: float,
) -> Projection:
    """Project a bearing/distance onto a north-up, aspect-corrected ellipse."""
    if max_range_nm <= 0:
        raise ValueError("maximum range must be positive")
    normalized = distance_nm / max_range_nm
    angle = math.radians(bearing_deg % 360.0)
    x = center_x + math.sin(angle) * normalized * horizontal_radius
    y = center_y - math.cos(angle) * normalized * vertical_radius
    return Projection(round(x), round(y), 0 <= distance_nm <= max_range_nm)


def range_nm_from_km(distance_km: float) -> float:
    return distance_km * 0.539956803
