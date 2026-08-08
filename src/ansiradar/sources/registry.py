"""Source selection and construction from CLI/configuration."""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from ansiradar.replay import ReplaySource
from ansiradar.sources.base import AircraftSource, UnsupportedSource
from ansiradar.sources.file import FileSource
from ansiradar.sources.url import UrlSource

Kind = Literal["url", "file", "replay"]

KINDS: tuple[Kind, ...] = ("url", "file", "replay")


def normalize_kind(value: str) -> Kind:
    lowered = value.strip().lower()
    if lowered not in KINDS:
        raise UnsupportedSource(
            f"unsupported source type {value!r}; choose from url, file, replay"
        )
    return lowered


@dataclass(frozen=True, slots=True)
class SourceSpec:
    """Describes how to build a source; used by the CLI and configuration."""

    kind: Kind
    url: str | None = None
    file: str | None = None
    replay_file: str | None = None
    timeout: float = 10.0
    max_bytes: int = 2_000_000
    max_aircraft: int = 2000

    def endpoint(self) -> str:
        if self.kind == "url":
            return self.url or ""
        if self.kind == "file":
            return self.file or ""
        return self.replay_file or ""


def validate_spec(spec: SourceSpec) -> None:
    """Fail fast on invalid source combinations before any terminal session."""
    if spec.kind == "url" and not spec.url:
        raise UnsupportedSource("url source requires --url")
    if spec.kind == "file" and not spec.file:
        raise UnsupportedSource("file source requires --file")
    if spec.kind == "replay" and not spec.replay_file:
        raise UnsupportedSource("replay source requires --replay-file")
    if spec.timeout <= 0:
        raise UnsupportedSource("source timeout must be positive")
    if spec.max_bytes < 1024:
        raise UnsupportedSource("source response limit must be at least 1 KiB")
    if spec.max_aircraft < 1:
        raise UnsupportedSource("maximum aircraft count must be positive")


def build_source(
    spec: SourceSpec,
    *,
    client: httpx.Client | None = None,
) -> AircraftSource:
    validate_spec(spec)
    logging.getLogger("ansiradar.resources").info(
        "creating radar source kind=%s", spec.kind
    )
    if spec.kind == "url":
        return UrlSource(
            spec.url,  # type: ignore[arg-type]
            timeout=spec.timeout,
            max_bytes=spec.max_bytes,
            max_aircraft=spec.max_aircraft,
            client=client,
        )
    if spec.kind == "replay":
        return ReplaySource(spec.replay_file)  # type: ignore[arg-type]
    return FileSource(
        spec.file,  # type: ignore[arg-type]
        max_bytes=spec.max_bytes,
        max_aircraft=spec.max_aircraft,
    )
