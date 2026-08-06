"""Local JSON file source that tolerates replacement and temporary absence."""

import json
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from ansiradar.obs import ObservationSnapshot
from ansiradar.sources.base import (
    InvalidSourceData,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.sources.decoder import parse_aircraft_json


class FileSource:
    """Poll a decoder-compatible JSON file from disk.

    The file may be a static snapshot, repeatedly overwritten by another
    process, or replaced atomically. A temporarily missing file or a partial
    write surfaces as a classifiable error so the radar loop can retry instead
    of crashing.
    """

    def __init__(
        self,
        path: str,
        *,
        max_bytes: int = 2_000_000,
        max_aircraft: int = 2000,
    ) -> None:
        self.location = path
        self.max_bytes = max_bytes
        self.max_aircraft = max_aircraft
        self.path = _resolve_path(path)

    def poll(self) -> ObservationSnapshot:
        text = self._read_text()
        try:
            payload: object = json.loads(text)
        except json.JSONDecodeError as error:
            raise InvalidSourceData(
                f"invalid JSON in {self.path} at line {error.lineno}, "
                f"column {error.colno}"
            ) from error
        return parse_aircraft_json(
            payload,
            timestamp=time.time(),
            source="file",
            max_aircraft=self.max_aircraft,
        ).snapshot

    def _read_text(self) -> str:
        try:
            stat = self.path.stat()
        except FileNotFoundError as error:
            raise SourceUnavailable(f"source file not found: {self.path}") from error
        except OSError as error:
            raise SourceUnavailable(f"cannot stat {self.path}: {error}") from error
        if stat.st_size > self.max_bytes:
            raise SourceUnavailable(
                f"source file {self.path} exceeds {self.max_bytes} bytes"
            )
        try:
            data = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as error:
            raise SourceUnavailable(
                f"source file disappeared while reading: {self.path}"
            ) from error
        except UnicodeError as error:
            raise InvalidSourceData(
                f"source file {self.path} is not UTF-8 text"
            ) from error
        except OSError as error:
            raise SourceUnavailable(f"cannot read {self.path}: {error}") from error
        return data


def _resolve_path(location: str) -> Path:
    parsed = urlparse(location)
    if parsed.scheme == "file":
        if parsed.netloc not in {"", "localhost"}:
            raise UnsupportedSource("remote file URLs are not supported")
        return Path(unquote(parsed.path))
    if parsed.scheme:
        raise UnsupportedSource(f"unsupported source protocol: {parsed.scheme}")
    return Path(location)
