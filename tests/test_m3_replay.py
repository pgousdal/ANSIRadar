"""Tests for the replay format, source, and recorder."""

import json
from pathlib import Path

import pytest

from ansiradar.errors import InvalidSourceData, ReplayExhausted
from ansiradar.obs import ObservationSnapshot, build_observation
from ansiradar.replay import (
    MAX_LINE_BYTES,
    ReplayRecorder,
    ReplaySource,
    parse_replay_line,
    snapshot_to_line,
)
from ansiradar.sources import build_source
from ansiradar.sources.registry import SourceSpec

FIXTURES = Path(__file__).parent / "fixtures"
REPLAY = FIXTURES / "radar-replay.jsonl"


def test_schema_validation() -> None:
    with pytest.raises(InvalidSourceData):
        parse_replay_line('{"aircraft": []}', index=1)
    with pytest.raises(InvalidSourceData):
        parse_replay_line('{"timestamp": 1}', index=1)
    assert parse_replay_line("   \n", index=1) is None


def test_valid_replay_loads() -> None:
    source = ReplaySource(str(REPLAY))
    assert source.record_count() == 4
    assert source.last_timestamp() == 90.0
    assert source.observation_count() == 10


def test_deterministic_stepping() -> None:
    source = ReplaySource(str(REPLAY))
    assert source.peek_time() == 0.0
    assert source.is_due(0.0)
    assert not source.is_due(-1.0)
    first = source.poll()
    assert first.generated_at == 0.0
    assert first.observations[0].icao == "478ABC"


def test_replay_exhaustion(tmp_path: Path) -> None:
    path = tmp_path / "one.jsonl"
    path.write_text(json.dumps({"timestamp": 1.0, "aircraft": []}) + "\n")
    source = ReplaySource(str(path))
    source.poll()
    with pytest.raises(ReplayExhausted):
        source.poll()


def test_malformed_lines(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"timestamp": 1}\nnot json\n')
    with pytest.raises(InvalidSourceData):
        ReplaySource(str(path))


def test_oversized_lines(tmp_path: Path) -> None:
    path = tmp_path / "big.jsonl"
    path.write_text(
        '{"timestamp": 1, "aircraft": [{"icao": "' + "a" * MAX_LINE_BYTES + '"}]}\n'
    )
    with pytest.raises(InvalidSourceData):
        ReplaySource(str(path))


def test_recording_round_trip(tmp_path: Path) -> None:
    recorded = tmp_path / "out.jsonl"
    line1 = snapshot_to_line(
        _obs_snapshot("ABC111", 10.0),
        seq=1,
        timestamp=100.0,
    )
    line2 = snapshot_to_line(
        _obs_snapshot("ABC222", 20.0),
        seq=2,
        timestamp=101.0,
    )
    with ReplayRecorder(str(recorded)) as recorder:
        recorder.write(line1)
        recorder.write(line2)
    source = ReplaySource(str(recorded))
    assert source.record_count() == 2
    first = source.poll()
    assert first.observations[0].icao == "ABC111"
    second = source.poll()
    assert second.observations[0].icao == "ABC222"
    assert second.observations[0].altitude_baro_ft == 20


def test_recording_does_not_corrupt_existing(tmp_path: Path) -> None:
    path = tmp_path / "existing.jsonl"
    path.write_text(json.dumps({"timestamp": 5.0, "aircraft": []}) + "\n")
    with ReplayRecorder(str(path), append=True) as recorder:
        recorder.write(snapshot_to_line(_obs_snapshot("ABCDEF", 1.0), timestamp=6.0))
    source = ReplaySource(str(path))
    assert source.record_count() == 2
    assert source.last_timestamp() == 6.0


def test_recording_refuses_non_replay_append(tmp_path: Path) -> None:
    path = tmp_path / "garbage.jsonl"
    path.write_text("this is not replay\n")
    with pytest.raises(InvalidSourceData):
        ReplayRecorder(str(path), append=True)


def test_recording_refuses_existing_file_without_append(tmp_path: Path) -> None:
    path = tmp_path / "existing.jsonl"
    path.write_text(json.dumps({"timestamp": 1.0, "aircraft": []}) + "\n")
    with pytest.raises(InvalidSourceData):
        ReplayRecorder(str(path))


def test_deterministic_output() -> None:
    a = snapshot_to_line(_obs_snapshot("ABC123", 1.0), timestamp=7.0)
    b = snapshot_to_line(_obs_snapshot("ABC123", 1.0), timestamp=7.0)
    assert a == b
    payload = json.loads(a)
    assert list(payload.keys()) == sorted(payload.keys())


def test_build_source_replay(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    path.write_text(json.dumps({"timestamp": 1.0, "aircraft": []}) + "\n")
    spec = SourceSpec(kind="replay", replay_file=str(path))
    source = build_source(spec)
    assert source.poll().source == "replay"


def _obs_snapshot(icao: str, alt: float) -> ObservationSnapshot:
    observation = build_observation(
        icao=icao,
        timestamp=0.0,
        source="replay",
        altitude_baro_ft=alt,
        latitude=58.0,
        longitude=6.0,
    )
    assert observation is not None
    return ObservationSnapshot(
        generated_at=0.0,
        source="replay",
        observations=(observation,),
        messages=1,
    )
