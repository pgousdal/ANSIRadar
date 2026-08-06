"""Aircraft data source adapters and selection."""

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
from ansiradar.sources.readsb import ReadsbSource
from ansiradar.sources.registry import (
    SourceSpec,
    build_source,
    normalize_kind,
    validate_spec,
)
from ansiradar.sources.url import UrlSource

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
