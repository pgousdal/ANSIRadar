"""Tests for the URL, file, and decoder source adapters."""

import http.server
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from ansiradar.errors import (
    InvalidSourceData,
    ResponseTooLarge,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.sources.decoder import parse_aircraft_json
from ansiradar.sources.file import FileSource
from ansiradar.sources.url import UrlSource

FIXTURES = Path(__file__).parent / "fixtures"
BASIC = FIXTURES / "readsb-basic.json"


@contextmanager
def serve(payload: bytes, *, status: int = 200) -> Iterator[str]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/data/aircraft.json"
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_file_source_valid() -> None:
    snapshot = FileSource(str(BASIC)).poll()
    assert snapshot.source == "file"
    assert len(snapshot.observations) == 7
    assert snapshot.observations[0].icao == "478ABC"
    assert snapshot.generated_at == 1720000000.0


def test_file_source_missing() -> None:
    with pytest.raises(SourceUnavailable):
        FileSource("/nonexistent/aircraft.json").poll()


def test_file_source_oversized(tmp_path: Path) -> None:
    big = tmp_path / "big.json"
    big.write_text(" " * 5000)
    with pytest.raises(SourceUnavailable):
        FileSource(str(big), max_bytes=1024).poll()


def test_static_file_replacement(tmp_path: Path) -> None:
    path = tmp_path / "aircraft.json"
    path.write_text(json.dumps({"aircraft": [{"hex": "abc001"}]}))
    assert FileSource(str(path)).poll().observations[0].icao == "ABC001"
    path.write_text(json.dumps({"aircraft": [{"hex": "abc002"}]}))
    assert FileSource(str(path)).poll().observations[0].icao == "ABC002"


def test_temporarily_missing_then_present(tmp_path: Path) -> None:
    path = tmp_path / "aircraft.json"
    with pytest.raises(SourceUnavailable):
        FileSource(str(path)).poll()
    path.write_text(json.dumps({"aircraft": [{"hex": "abc003"}]}))
    assert FileSource(str(path)).poll().observations[0].icao == "ABC003"


def test_partial_or_malformed_file(tmp_path: Path) -> None:
    partial = tmp_path / "partial.json"
    partial.write_text('{"aircraft": [{"hex": "abc1')
    with pytest.raises(InvalidSourceData):
        FileSource(str(partial)).poll()


def test_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json at all")
    with pytest.raises(InvalidSourceData):
        FileSource(str(bad)).poll()


def test_malformed_top_level_schema() -> None:
    payloads: tuple[object, ...] = ([], {}, {"aircraft": {}})
    for payload in payloads:
        with pytest.raises(UnsupportedSource):
            parse_aircraft_json(
                payload, timestamp=0.0, source="file", max_aircraft=2000
            )


def test_malformed_individual_records_are_skipped() -> None:
    snapshot = FileSource(str(FIXTURES / "malformed-records.json")).poll()
    assert len(snapshot.observations) == 3
    assert snapshot.skipped == 5
    assert {obs.icao for obs in snapshot.observations} == {"ABC111", "ABC222", "ABC333"}
    ground = next(obs for obs in snapshot.observations if obs.icao == "ABC333")
    assert ground.on_ground is True


def test_dump1090_fixture() -> None:
    snapshot = FileSource(str(FIXTURES / "dump1090.json")).poll()
    assert len(snapshot.observations) == 3
    assert snapshot.observations[0].icao == "40621A"


def test_tar1090_fixture() -> None:
    snapshot = FileSource(str(FIXTURES / "tar1090.json")).poll()
    assert len(snapshot.observations) == 3
    assert snapshot.observations[0].icao == "A7C0E1"


def test_url_valid() -> None:
    payload = json.dumps(
        {"now": 1.0, "messages": 3, "aircraft": [{"hex": "abc123", "flight": "T1"}]}
    ).encode()
    with serve(payload) as url:
        snapshot = UrlSource(url).poll()
    assert snapshot.source == "url"
    assert snapshot.observations[0].icao == "ABC123"
    assert snapshot.messages == 3


def test_url_http_error() -> None:
    with serve(b"{}", status=500) as url:
        with pytest.raises(SourceUnavailable):
            UrlSource(url).poll()


def test_url_invalid_json() -> None:
    with serve(b"not json") as url:
        with pytest.raises(InvalidSourceData):
            UrlSource(url).poll()


def test_url_oversized_response_rejected() -> None:
    payload = json.dumps(
        {"aircraft": [{"hex": f"abc{i:03d}"} for i in range(50)]}
    ).encode()
    with serve(payload) as url:
        with pytest.raises(ResponseTooLarge):
            UrlSource(url, max_bytes=200).poll()


def test_url_unsupported_scheme() -> None:
    with pytest.raises(UnsupportedSource):
        UrlSource("ftp://example.test/aircraft.json")


def test_url_missing_aircraft_array() -> None:
    with serve(b'{"now": 1.0}') as url:
        with pytest.raises(UnsupportedSource):
            UrlSource(url).poll()
