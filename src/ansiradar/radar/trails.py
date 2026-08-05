"""Bounded in-memory aircraft trails."""

from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrailPoint:
    icao: str
    latitude: float
    longitude: float
    sequence: int


class TrailStore:
    def __init__(self, length: int = 0, max_aircraft: int = 200) -> None:
        self.length = max(0, length)
        self.max_aircraft = max(1, max_aircraft)
        self._points: dict[str, deque[TrailPoint]] = defaultdict(
            lambda: deque(maxlen=self.length or 1)
        )

    def add(self, point: TrailPoint) -> None:
        if not self.length:
            return
        if point.icao not in self._points and len(self._points) >= self.max_aircraft:
            oldest = next(iter(self._points))
            del self._points[oldest]
        self._points[point.icao].append(point)

    def get(self, icao: str) -> tuple[TrailPoint, ...]:
        return tuple(self._points.get(icao, ()))

    def __len__(self) -> int:
        return sum(len(points) for points in self._points.values())
