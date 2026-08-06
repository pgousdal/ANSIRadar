"""Integration tests for CLI source selection, polling, and rendering."""

import json
from pathlib import Path

import pytest

from ansiradar.cli import main
from ansiradar.errors import SourceUnavailable
from ansiradar.obs import ObservationSnapshot, build_observation
from ansiradar.poller import SourcePoller
from ansiradar.render.buffer import ScreenBuffer
from ansiradar.render.radar import RadarRenderOptions, render_radar
from ansiradar.tracking import TrackManager

FIXTURES = Path(__file__).parent / "fixtures"
BASIC = str(FIXTURES / "readsb-basic.json")
REPLAY = str(FIXTURES / "radar-replay.jsonl")


def _base_radar_args(*extra: str) -> list[str]:
    return [
        "radar",
        "--receiver-lat",
        "58.3405",
        "--receiver-lon",
        "6.2812",
        "--once",
        "--color",
        "never",
        "--symbols",
        "ascii",
        *extra,
    ]


def test_radar_once_file_source(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([*_base_radar_args(), "--source", "file", "--file", BASIC])
    output = capsys.readouterr().out
    assert code == 0
    assert "ANSIRadar 0.5.0" in output
    assert "CALL" in output and "Rng 100nm" in output
    assert "\x1b" not in output


def test_radar_once_replay_source(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([*_base_radar_args(), "--source", "replay", "--replay-file", REPLAY])
    output = capsys.readouterr().out
    assert code == 0
    assert "SAS431" in output
    assert "TIE" in output


def test_radar_once_legacy_source_path(capsys: pytest.CaptureFixture[str]) -> None:
    code = main([*_base_radar_args(), "--source", BASIC])
    assert code == 0
    assert "Rng 100nm" in capsys.readouterr().out


def test_mutually_exclusive_source_flags(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                *_base_radar_args(),
                "--url",
                "http://127.0.0.1:1/x",
                "--file",
                BASIC,
            ]
        )
    assert error.value.code == 2
    assert "mutually exclusive" in capsys.readouterr().err


def test_missing_url_for_url_kind(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main([*_base_radar_args(), "--source", "url"])
    assert error.value.code == 2
    assert "requires --url" in capsys.readouterr().err


def test_missing_replay_file_for_replay_kind(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main([*_base_radar_args(), "--source", "replay"])
    assert error.value.code == 2
    assert "requires --replay-file" in capsys.readouterr().err


def test_invalid_source_kind(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as error:
        main([*_base_radar_args(), "--source", "bogus"])
    assert error.value.code == 2


def test_radar_once_unavailable_file(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [*_base_radar_args(), "--source", "file", "--file", "/nonexistent/x.json"]
    )
    assert code == 3
    assert "unavailable" in capsys.readouterr().err


def test_radar_once_invalid_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            *_base_radar_args(),
            "--source",
            "file",
            "--file",
            str(FIXTURES / "readsb-invalid.json"),
        ]
    )
    assert code == 4


def test_source_check_file_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["source-check", "--source", "file", "--file", BASIC, "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["aircraft_records"] == 7
    assert data["kind"] == "file"


def test_replay_inspect(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["replay-inspect", "--replay-file", REPLAY, "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["lines"] == 4
    assert data["last_timestamp"] == 90.0


def test_recording_writes_replay(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "rec.jsonl"
    code = main(
        [
            *_base_radar_args(),
            "--source",
            "file",
            "--file",
            BASIC,
            "--record",
            str(out),
        ]
    )
    assert code == 0
    lines = out.read_text().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert len(payload["aircraft"]) == 7
    assert payload["aircraft"][0]["icao"] == "478ABC"


def test_transient_failure_retains_last_snapshot() -> None:
    class FlakySource:
        calls = 0

        def poll(self) -> ObservationSnapshot:
            self.calls += 1
            if self.calls == 1:
                raise SourceUnavailable("boom")
            observation = build_observation(icao="abc123", timestamp=0.0, source="file")
            assert observation is not None
            return ObservationSnapshot(
                generated_at=0.0, source="file", observations=(observation,)
            )

    clock = [0.0]
    source = FlakySource()
    poller = SourcePoller(source, poll_interval=2.0, clock=lambda: clock[0])
    poller.step()  # fails
    assert poller.status().healthy is False
    assert poller.last_snapshot() is None
    clock[0] = 3.0
    poller.step()  # succeeds after backoff window
    assert poller.status().healthy is True
    assert poller.last_snapshot() is not None
    assert poller.status().observations == 1


def test_compact_status_at_80x24() -> None:
    from ansiradar.models import Aircraft, PositionedAircraft

    items = (PositionedAircraft(Aircraft("ABC123", "TEST", 58.4, 6.3, 30000), 5, 90),)
    rendered = render_radar(
        items,
        width=80,
        height=24,
        options=RadarRenderOptions(status="src file OK 2s | 7 obs"),
    )
    serialized = rendered.serialize()
    for line in serialized.splitlines():
        assert len(line) <= 80
    assert "src file OK" in serialized


def test_below_minimum_terminal_size() -> None:
    rendered = render_radar(
        (),
        width=20,
        height=10,
        options=RadarRenderOptions(status="x"),
    )
    assert "too sma" in rendered.serialize()


def test_engine_deterministic_replay_frame() -> None:
    from ansiradar.obs import ObservationSnapshot
    from ansiradar.poller import SourcePoller
    from ansiradar.radar.engine import RadarEngine
    from ansiradar.replay import ReplaySource

    source = ReplaySource(REPLAY)
    end = source.last_timestamp() or 0.0
    poller = SourcePoller(source, clock=lambda: end)
    tracks = TrackManager(clock=lambda: end)
    engine = RadarEngine(poller, tracks, receiver_lat=58.3405, receiver_lon=6.2812)
    for record in source.records():
        engine.apply_manual(
            ObservationSnapshot(
                generated_at=record.timestamp,
                source=record.source,
                observations=record.observations,
                messages=record.messages,
            )
        )
    first = engine.frame()
    second = engine.frame()
    assert first.items == second.items
    assert len(first.items) == 2
    assert {item.aircraft.icao for item in first.items} == {"478ABC", "ABC001"}


def test_engine_applies_successful_poll_to_tracks() -> None:
    from ansiradar.obs import AircraftObservation
    from ansiradar.radar.engine import RadarEngine

    observation = build_observation(
        icao="ABC123", timestamp=0.0, source="file", latitude=58.4, longitude=6.3
    )
    assert observation is not None
    valid_observation: AircraftObservation = observation

    class Source:
        def poll(self) -> ObservationSnapshot:
            return ObservationSnapshot(
                generated_at=0.0, source="file", observations=(valid_observation,)
            )

    poller = SourcePoller(Source(), clock=lambda: 0.0)
    engine = RadarEngine(
        poller,
        TrackManager(clock=lambda: 0.0),
        receiver_lat=58.3405,
        receiver_lon=6.2812,
    )
    engine.step()
    assert [item.aircraft.icao for item in engine.frame().items] == ["ABC123"]


def test_screen_buffer_still_deterministic() -> None:
    buffer = ScreenBuffer(4, 1)
    buffer.draw_text(0, 0, "abcd")
    assert buffer.serialize() == "abcd"
