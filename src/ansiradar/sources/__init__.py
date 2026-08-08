"""Aircraft data source adapters and selection."""

from typing import TYPE_CHECKING

from ansiradar.sources.base import (
    AircraftSource,
    InvalidSourceData,
    ReplayExhausted,
    ResponseTooLarge,
    SourceError,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.sources.file import FileSource
from ansiradar.sources.registry import (
    SourceSpec,
    build_source,
    normalize_kind,
    validate_spec,
)

if TYPE_CHECKING:
    from ansiradar.sources.readsb import ReadsbSource
    from ansiradar.sources.url import UrlSource


def __getattr__(name: str) -> object:
    """Load optional network-backed source classes only when explicitly used."""
    if name == "ReadsbSource":
        from ansiradar.sources.readsb import ReadsbSource

        return ReadsbSource
    if name == "UrlSource":
        from ansiradar.sources.url import UrlSource

        return UrlSource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "AircraftSource",
    "FileSource",
    "InvalidSourceData",
    "ReadsbSource",
    "ReplayExhausted",
    "ResponseTooLarge",
    "SourceError",
    "SourceSpec",
    "SourceUnavailable",
    "UnsupportedSource",
    "UrlSource",
    "build_source",
    "normalize_kind",
    "validate_spec",
]
