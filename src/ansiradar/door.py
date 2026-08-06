"""Mystic DOOR32.SYS parsing and stable door exit codes."""

from dataclasses import dataclass
from pathlib import Path

from ansiradar.sanity import sanitize_text

DOOR32_REQUIRED_LINES = 11
DOOR32_MAX_LINES = 11
DOOR32_MAX_LINE_BYTES = 512

DOOR_EXIT_OK = 0
DOOR_EXIT_USAGE = 2
DOOR_EXIT_DROPFILE = 10
DOOR_EXIT_UNSUPPORTED_MODE = 11
DOOR_EXIT_DESCRIPTOR = 12
DOOR_EXIT_SOURCE = 13
DOOR_EXIT_DISCONNECT = 14
DOOR_EXIT_TIME_EXPIRED = 15
DOOR_EXIT_IDLE = 16
DOOR_EXIT_INTERNAL = 17


class Door32Error(Exception):
    """The DOOR32 file is absent or malformed."""


class UnsupportedCommunicationMode(Door32Error):
    """The dropfile describes a mode this runtime does not support."""


class InvalidDescriptor(Door32Error):
    """The dropfile descriptor is not a usable connected socket."""


@dataclass(frozen=True, slots=True)
class Door32Info:
    communication_type: int
    handle: int
    baud_rate: int
    bbs_id: str
    user_id: int
    user_name: str
    user_alias: str
    security_level: int
    time_left_minutes: int
    terminal_emulation: int
    node_number: int


def parse_door32(path: str | Path) -> Door32Info:
    """Parse the 11-line Mystic DOOR32.SYS field order.

    Supported communication type is ``2`` (an already-connected socket/file
    descriptor). The parser never modifies the file and does not log its
    contents. LF, CRLF, and a missing final newline are accepted.
    """
    source = Path(path)
    try:
        raw = source.read_bytes()
    except OSError as error:
        raise Door32Error(f"cannot read DOOR32.SYS {source}: {error}") from error
    lines = raw.splitlines()
    if len(lines) < DOOR32_REQUIRED_LINES:
        raise Door32Error(
            f"DOOR32.SYS requires {DOOR32_REQUIRED_LINES} lines, got {len(lines)}"
        )
    if len(lines) > DOOR32_MAX_LINES:
        raise Door32Error("DOOR32.SYS contains unexpected extra lines")
    if any(len(line) > DOOR32_MAX_LINE_BYTES for line in lines):
        raise Door32Error(
            f"DOOR32.SYS lines must be at most {DOOR32_MAX_LINE_BYTES} bytes"
        )

    text = [line.decode("utf-8", "replace").strip() for line in lines]
    communication_type = _integer(text[0], "communication type")
    handle = _integer(text[1], "communication handle")
    baud_rate = _integer(text[2], "baud rate")
    user_id = _integer(text[4], "user id")
    security_level = _integer(text[7], "security level")
    time_left = _integer(text[8], "time left")
    terminal_emulation = _integer(text[9], "terminal emulation")
    node_number = _integer(text[10], "node number")
    if communication_type != 2:
        raise UnsupportedCommunicationMode(
            f"DOOR32 communication type {communication_type} is unsupported; "
            "Mystic Linux socket mode is type 2"
        )
    if handle < 0:
        raise InvalidDescriptor("DOOR32 communication handle must be non-negative")
    if time_left < 0:
        raise Door32Error("DOOR32 time left must be non-negative")
    return Door32Info(
        communication_type=communication_type,
        handle=handle,
        baud_rate=baud_rate,
        bbs_id=_field_text(text[3], "BBS id"),
        user_id=user_id,
        user_name=_field_text(text[5], "user name"),
        user_alias=_field_text(text[6], "user alias"),
        security_level=security_level,
        time_left_minutes=time_left,
        terminal_emulation=terminal_emulation,
        node_number=node_number,
    )


def _integer(value: str, field: str) -> int:
    try:
        return int(value, 10)
    except ValueError as error:
        raise Door32Error(f"DOOR32 {field} must be an integer") from error


def _field_text(value: str, field: str) -> str:
    result = sanitize_text(value, limit=64)
    if "\x00" in result:
        raise Door32Error(f"DOOR32 {field} contains an invalid character")
    return result
