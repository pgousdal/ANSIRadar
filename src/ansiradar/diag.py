"""Terminal-safe diagnostics, logging, and URL redaction."""

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_USERINFO = re.compile(r"(^[^/@]*@)")

_QUERY_SECRETS = {
    "api_key",
    "apikey",
    "key",
    "token",
    "access_token",
    "auth",
    "password",
    "passwd",
    "secret",
}


def redact_url(url: str) -> str:
    """Redact userinfo and secret-bearing query parameters from a URL."""
    parts = urlsplit(url)
    netloc = _USERINFO.sub(r"****@", parts.netloc) if parts.netloc else parts.netloc
    query = urlencode(
        [
            (name, "****" if name.casefold() in _QUERY_SECRETS else value)
            for name, value in parse_qsl(parts.query)
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def make_logger(name: str, *, path: str | None = None) -> logging.Logger:
    """Return a logger; when ``path`` is set, appends to that file."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if path:
        handler: logging.Handler
        try:
            handler = logging.FileHandler(path)
        except OSError:
            handler = logging.NullHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


def shorten_message(message: str, *, limit: int = 120) -> str:
    return message if len(message) <= limit else message[: limit - 1] + "…"


def never_log(payload: Any) -> bool:
    return False
