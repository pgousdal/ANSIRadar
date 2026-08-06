"""Sanitization of untrusted terminal-visible strings."""

import re

_ANSI_ESC = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|"
    r"\x1b][^\x07\x1b]*(?:\x07|\x1b\\)|"
    r"\x1b[()][A-Z0-9]|\x1b[@-Z\\-_]|\x08"
)
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")

_ICAO_PARTS = re.compile(r"^[0-9A-F]{6}$")


def sanitize_text(value: object, *, limit: int = 0) -> str:
    """Return an ASCII-safe string with control and ANSI sequences removed.

    Control characters (including ESC, which would otherwise allow ANSI escape
    injection) are removed rather than emitted verbatim. Interior whitespace
    runs are collapsed. Optional ``limit`` truncates after normalization.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = _coerce_text(value)
    stripped_ansi = _ANSI_ESC.sub("", value)
    cleaned = _CONTROL.sub(" ", stripped_ansi)
    normalized = " ".join(cleaned.split())
    if limit and len(normalized) > limit:
        normalized = normalized[:limit]
    return normalized


def _coerce_text(value: object) -> str:
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - never let dumping fail validation
        return ""


def normalize_icao(value: object) -> str | None:
    """Return a validated uppercase ICAO 24-bit address or None.

    Rejects anything that is not exactly six hexadecimal digits after
    normalizing and trimming whitespace.
    """
    text = sanitize_text(value)
    text = text.upper()
    if not _ICAO_PARTS.match(text):
        return None
    return text


def normalize_callsign(value: object) -> str | None:
    text = sanitize_text(value)
    if not text:
        return None
    return text
