import json
from pathlib import Path

import pytest

from ansiradar.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
BASIC = str(FIXTURES / "readsb-basic.json")


def run_snapshot(*extra: str) -> int:
    return main(
        [
            "snapshot",
            "--source",
            BASIC,
            "--receiver-lat",
            "58.3405",
            "--receiver-lon",
            "6.2812",
            *extra,
        ]
    )


def test_text_snapshot_and_stale_filter(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_snapshot() == 0
    output = capsys.readouterr().out
    assert "ANSIRadar 0.2.0" in output
    assert "Visible:           7" in output
    assert "Without position:  2" in output
    assert "SAS431" in output
    assert "ft" in output and "kt" in output and "nm" in output


def test_metric_limit_and_deterministic_ties(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_snapshot("--units", "metric", "--sort", "callsign", "--limit", "2") == 0
    output = capsys.readouterr().out
    assert "km/h" in output and " km" in output and " m" in output
    assert "Displayed:         2" in output


def test_json_contract(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_snapshot("--json", "--sort", "callsign") == 0
    raw = capsys.readouterr().out
    data = json.loads(raw)
    assert raw.index('"aircraft"') < raw.index('"receiver"')
    assert data["schema_version"] == 1
    assert data["source"]["generated_at"] == 1720000000.0
    assert data["summary"] == {
        "aircraft_displayed": 5,
        "aircraft_total": 7,
        "aircraft_with_position": 5,
        "aircraft_without_position": 2,
    }
    ties = [
        item
        for item in data["aircraft"]
        if item["callsign"] and item["callsign"].lower() == "tie"
    ]
    assert [item["icao"] for item in ties] == ["ABC001", "ABC002"]


def test_stale_unknown_and_threshold(capsys: pytest.CaptureFixture[str]) -> None:
    stale = str(FIXTURES / "readsb-stale.json")
    assert (
        main(
            [
                "snapshot",
                "--source",
                stale,
                "--receiver-lat",
                "58",
                "--receiver-lon",
                "6",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert [item["icao"] for item in data["aircraft"]] == ["AAA002", "AAA003"]
    assert data["summary"]["aircraft_with_position"] == 3


def test_environment_and_cli_override(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ANSIRADAR_SOURCE", BASIC)
    monkeypatch.setenv("ANSIRADAR_RECEIVER_LAT", "1")
    monkeypatch.setenv("ANSIRADAR_RECEIVER_LON", "2")
    assert (
        main(
            [
                "snapshot",
                "--receiver-lat",
                "58.3405",
                "--receiver-lon",
                "6.2812",
                "--json",
                "--limit",
                "0",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert data["receiver"] == {"latitude": 58.3405, "longitude": 6.2812}


def test_source_check_and_exit_codes(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["source-check", "--source", BASIC, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["aircraft_records"] == 7
    assert main(["source-check", "--source", str(tmp_path / "absent")]) == 3
    assert (
        main(["source-check", "--source", str(FIXTURES / "readsb-invalid.json")]) == 4
    )
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{}")
    assert main(["source-check", "--source", str(malformed)]) == 5


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main(["--version"])
    assert error.value.code == 0
    assert capsys.readouterr().out == "ANSIRadar 0.2.0\n"


def test_missing_receiver_is_usage_error(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANSIRADAR_RECEIVER_LAT", raising=False)
    monkeypatch.delenv("ANSIRADAR_RECEIVER_LON", raising=False)
    with pytest.raises(SystemExit) as error:
        main(["snapshot", "--source", BASIC])
    assert error.value.code == 2
    assert "receiver latitude and longitude" in capsys.readouterr().err
