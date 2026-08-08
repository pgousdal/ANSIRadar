from pathlib import Path

import pytest

from ansiradar.mystic import (
    MysticConfig,
    MysticStartupError,
    MysticState,
    apply_key,
    build_mystic_engine,
    map_key,
    read_mystic_key,
    run_mystic,
)
from ansiradar.poller import SourcePoller
from ansiradar.radar.engine import RadarEngine
from ansiradar.sources import SourceSpec
from ansiradar.sources.file import FileSource
from ansiradar.tracking import TrackManager

FIXTURE = Path(__file__).parent / "fixtures" / "readsb-aircraft.json"


class FakeMystic:
    def __init__(self, keys=()):
        self.keys = list(keys)
        self.output = []

    def rwrite(self, text):
        self.output.append(text)

    def keypressed(self):
        return bool(self.keys)

    def onekey(self, keys, echo):
        del keys, echo
        return self.keys.pop(0)


def engine():
    source = FileSource(str(FIXTURE))
    poller = SourcePoller(source, poll_interval=1, clock=lambda: 0.0)
    tracks = TrackManager(clock=lambda: 0.0)
    return RadarEngine(poller, tracks, receiver_lat=58.3405, receiver_lon=6.2812)


def test_mystic_key_mapping_and_fallback():
    assert map_key("KEY_UP") == "UP"
    assert map_key(27) == "ESC"
    fake = FakeMystic(["K"])
    assert read_mystic_key(fake) == "K"

    class GetKey(FakeMystic):
        def getkey(self):
            return "KEY_DOWN"

    assert read_mystic_key(GetKey(["x"])) == "DOWN"


def test_controls_are_deterministic():
    state = MysticState(100, "callsign")
    assert apply_key(state, "J", 3) == "next"
    assert apply_key(state, "K", 3) == "previous"
    assert apply_key(state, "+", 3) == "zoom_in"
    assert apply_key(state, "1", 3) == "range"
    assert state.range_nm == 25
    assert apply_key(state, "P", 3) == "pause"
    assert apply_key(state, "S", 3) == "sort"
    assert apply_key(state, "L", 3) == "labels"
    assert apply_key(state, "H", 3) == "help"
    assert apply_key(state, "Q", 3) == "quit"


def test_q_exits_on_first_press_and_state_does_not_leak():
    first = FakeMystic(["Q"])
    second = FakeMystic(["Q"])
    assert (
        run_mystic(
            first, engine(), MysticConfig(), clock=lambda: 0.0, sleep=lambda _: None
        )
        == "quit"
    )
    assert (
        run_mystic(
            second, engine(), MysticConfig(), clock=lambda: 0.0, sleep=lambda _: None
        )
        == "quit"
    )
    assert len(first.output) == 3
    assert len(second.output) == 3


def test_renderer_stays_inside_80x25():
    fake = FakeMystic(["Q"])
    run_mystic(fake, engine(), MysticConfig(), clock=lambda: 0.0, sleep=lambda _: None)
    assert all("\x1b[26;" not in output for output in fake.output)


def test_source_startup_failure_is_controlled_by_frontend(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(MysticStartupError, match="not found"):
        build_mystic_engine(
            SourceSpec(kind="file", file=str(missing)),
            receiver_lat=58.0,
            receiver_lon=6.0,
        )
