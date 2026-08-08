"""HTTP(S) aircraft JSON source with bounded, validated reads."""

import json
import logging

import httpx

from ansiradar.diag import redact_url
from ansiradar.obs import ObservationSnapshot
from ansiradar.sources.base import (
    InvalidSourceData,
    ResponseTooLarge,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.sources.decoder import parse_aircraft_json

USER_AGENT = "ansiradar/0.4 (+local ADS-B read only)"

_MAX_REDIRECTS = 5


class UrlSource:
    """Poll an HTTP(S) ``aircraft.json`` endpoint without auto-discovery."""

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 10.0,
        max_bytes: int = 2_000_000,
        max_aircraft: int = 2000,
        user_agent: str = USER_AGENT,
        client: httpx.Client | None = None,
    ) -> None:
        parts = url.split(":", 1)
        scheme = parts[0].lower() if "://" in url else ""
        if scheme not in {"http", "https"}:
            raise UnsupportedSource(f"unsupported source URL scheme: {scheme!r}")
        self.url = url
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_aircraft = max_aircraft
        self.user_agent = user_agent
        self._client = client
        self._owned_client = False

    def _transport(self) -> httpx.Client:
        if self._client is None:
            logging.getLogger("ansiradar.resources").info("creating HTTP client")
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=False,
            )
            self._owned_client = True
        return self._client

    def close(self) -> None:
        if self._owned_client and self._client is not None:
            logging.getLogger("ansiradar.resources").info("closing HTTP client")
            self._client.close()
            self._client = None
            self._owned_client = False

    def poll(self) -> ObservationSnapshot:
        text = self._fetch_text()
        try:
            payload: object = json.loads(text)
        except json.JSONDecodeError as error:
            raise InvalidSourceData(
                f"invalid JSON from {redact_url(self.url)} at "
                f"line {error.lineno}, column {error.colno}"
            ) from error
        return parse_aircraft_json(
            payload,
            timestamp=_observe_time(),
            source="url",
            max_aircraft=self.max_aircraft,
        ).snapshot

    def _fetch_text(self) -> str:
        client = self._transport()
        try:
            response = self._get(client, self.url)
        except httpx.ConnectTimeout as error:
            raise SourceUnavailable(
                f"connection timeout reaching {redact_url(self.url)}"
            ) from error
        except httpx.ReadTimeout as error:
            raise SourceUnavailable(
                f"read timeout reaching {redact_url(self.url)}"
            ) from error
        except httpx.ConnectError as error:
            raise SourceUnavailable(
                f"connection failed for {redact_url(self.url)}: {error}"
            ) from error
        except httpx.TransportError as error:
            raise SourceUnavailable(
                f"transport error for {redact_url(self.url)}: {error}"
            ) from error
        if response.status_code >= 400:
            raise SourceUnavailable(
                f"HTTP {response.status_code} from {redact_url(self.url)}"
            )
        body = self._read_body(response)
        try:
            return body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidSourceData(
                f"response from {redact_url(self.url)} is not UTF-8 text"
            ) from error

    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            response = client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                target = response.headers.get("location")
                if not target:
                    raise SourceUnavailable(
                        f"redirect from {redact_url(current)} has no Location header"
                    )
                target = str(httpx.URL(target).join(httpx.URL(current)))
                scheme = str(httpx.URL(target).scheme)
                if scheme not in {"http", "https"}:
                    raise UnsupportedSource(
                        f"redirect to unsupported scheme {scheme!r}"
                    )
                current = target
                continue
            return response
        raise SourceUnavailable(
            f"too many redirects while reading {redact_url(self.url)}"
        )

    def _read_body(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > self.max_bytes:
                    raise ResponseTooLarge(
                        f"response from {redact_url(self.url)} exceeded "
                        f"{self.max_bytes} bytes"
                    )
                chunks.append(chunk)
        finally:
            response.close()
        return b"".join(chunks)


def _observe_time() -> float:
    import time

    return time.time()
