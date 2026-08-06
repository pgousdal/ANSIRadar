"""Common source contract and the poll protocol."""

from typing import Protocol

from ansiradar.errors import (
    InvalidSourceData,
    ReplayExhausted,
    ResponseTooLarge,
    SourceError,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.obs import ObservationSnapshot

__all__ = [
    "AircraftSource",
    "InvalidSourceData",
    "ReplayExhausted",
    "ResponseTooLarge",
    "SourceError",
    "SourceUnavailable",
    "UnsupportedSource",
]


class AircraftSource(Protocol):
    """A live or static producer of normalized snapshots.

    Source implementations must not touch terminals, screen buffers, keyboard
    handling, radar layout, or ANSI rendering. They return normalized
    snapshots and raise the ``SourceError`` subclasses defined here only.
    """

    def poll(self) -> ObservationSnapshot:
        """Read one snapshot, raising a ``SourceError`` subclass on failure."""
        ...
