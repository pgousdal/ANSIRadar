from pathlib import Path

import httpx
import pytest

from ansiradar.models import Aircraft
from ansiradar.sources import (
    InvalidSourceData,
    ReadsbSource,
    SourceUnavailable,
    UnsupportedSource,
)
from ansiradar.sources.readsb import parse_readsb

FIXTURES = Path(__file__).parent / "fixtures"


def test_local_loading_normalizes_records() -> None:
    snapshot = ReadsbSource(str(FIXTURES / "readsb-basic.json")).fetch()
    assert snapshot.generated_at == 1720000000.0
    assert snapshot.messages == 123456
    assert len(snapshot.aircraft) == 7
    assert snapshot.aircraft[0].icao == "478ABC"
    assert snapshot.aircraft[0].callsign == "SAS431"
    assert snapshot.raw_metadata["version"] == "synthetic"


def test_optional_bad_values_and_unusable_records() -> None:
    snapshot = ReadsbSource(str(FIXTURES / "readsb-missing-fields.json")).fetch()
    assert len(snapshot.aircraft) == 3
    assert snapshot.aircraft[0].callsign == "TEST 42"
    assert snapshot.aircraft[1].ground
    assert snapshot.aircraft[1].latitude is None
    assert snapshot.aircraft[2].ground_speed_kt is None


def test_file_url() -> None:
    assert (
        len(ReadsbSource((FIXTURES / "readsb-empty.json").as_uri()).fetch().aircraft)
        == 0
    )


def test_invalid_json_and_schema() -> None:
    with pytest.raises(InvalidSourceData):
        ReadsbSource(str(FIXTURES / "readsb-invalid.json")).fetch()
    for payload in ([], {}, {"aircraft": {}}):
        with pytest.raises(UnsupportedSource):
            parse_readsb(payload)


def test_http_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get(url: str, *, timeout: float) -> httpx.Response:
        request = httpx.Request("GET", url)
        return httpx.Response(
            200, request=request, json={"aircraft": [{"hex": "abc123"}]}
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    assert ReadsbSource("https://example.test/aircraft.json").fetch().aircraft == (
        Aircraft(icao="ABC123"),
    )


def test_http_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout(url: str, *, timeout: float) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx, "get", timeout)
    with pytest.raises(SourceUnavailable):
        ReadsbSource("http://example.test/data").fetch()


def test_unknown_protocol_rejected() -> None:
    with pytest.raises(UnsupportedSource):
        ReadsbSource("ftp://example.test/file").fetch()
