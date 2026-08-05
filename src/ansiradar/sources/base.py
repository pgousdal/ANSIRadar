"""Common source contract and errors."""

from typing import Protocol

from ansiradar.models import AircraftSnapshot


class SourceError(Exception):
    """Base class for expected source failures."""


class SourceUnavailable(SourceError):
    """The source could not be read or reached."""


class InvalidSourceData(SourceError):
    """The source body is not valid JSON."""


class UnsupportedSource(SourceError):
    """The source URI or JSON schema is unsupported."""


class AircraftSource(Protocol):
    def fetch(self) -> AircraftSnapshot:
        """Read and parse one source snapshot."""
        ...
