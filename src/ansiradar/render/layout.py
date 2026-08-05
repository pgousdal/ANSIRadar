"""Deterministic radar screen layout."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RadarLayout:
    width: int
    height: int
    radar_x: int
    radar_y: int
    radar_width: int
    radar_height: int
    center_x: int
    center_y: int
    list_y: int
    status_y: int
    too_small: bool


def calculate_layout(width: int, height: int) -> RadarLayout:
    too_small = width < 60 or height < 20
    radar_height = max(5, min(14, height - 10))
    radar_y = 1
    list_y = radar_y + radar_height + 1
    status_y = max(0, height - 2)
    return RadarLayout(
        width,
        height,
        1,
        radar_y,
        max(1, width - 2),
        radar_height,
        width // 2,
        radar_y + radar_height // 2,
        list_y,
        status_y,
        too_small,
    )
