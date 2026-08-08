import re
from pathlib import Path

import pytest

from ansiradar.mystic import (
    MysticConfig,
    MysticStartupError,
    MysticState,
    MysticTerminalAdapter,
    MysticTerminalProfile,
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


class PropertyMystic:
    def __init__(self, available, keys=()):
        self.keypressed = available
        self.keys = list(keys)
        self.output = []

    def rwrite(self, text):
        self.output.append(text)

    def onekey(self, keys, echo):
        del keys, echo
        return self.keys.pop(0)


class AuditedMystic:
    def __init__(self, *keys):
        self._keys = list(keys)
        self.output = []
        self.keypressed_reads = 0
        self.onekey_calls = 0

    @property
    def keypressed(self):
        self.keypressed_reads += 1
        return bool(self._keys)

    def rwrite(self, text):
        self.output.append(text)

    def onekey(self, keys, echo):
        del keys, echo
        self.onekey_calls += 1
        return self._keys.pop(0)

    def close(self):
        raise AssertionError("Mystic API must not be closed")

    def shutdown(self):
        raise AssertionError("Mystic API must not be shut down")

    def disconnect(self):
        raise AssertionError("Mystic API must not be disconnected")


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

    assert read_mystic_key(PropertyMystic(True, ["J"])) == "J"


def test_keypressed_property_and_method_compatibility():
    assert read_mystic_key(PropertyMystic(False)) is None
    assert read_mystic_key(PropertyMystic(True, ["Q"])) == "Q"
    assert read_mystic_key(FakeMystic(["Q"])) == "Q"
    assert MysticTerminalAdapter(PropertyMystic(True)).term_size() == (80, 25)


def test_mystic_profile_is_ascii_and_conservative():
    profile = MysticTerminalProfile()
    assert (profile.width, profile.height) == (80, 25)
    assert (profile.usable_width, profile.usable_height) == (79, 24)
    assert profile.charset == "ascii"
    assert profile.full_refresh


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


def test_all_required_mystic_controls_are_implemented():
    state = MysticState(100, "callsign")
    keys = (
        "H",
        "?",
        "J",
        "K",
        "+",
        "=",
        "-",
        "1",
        "2",
        "3",
        "4",
        "G",
        "S",
        "L",
        "P",
        "R",
    )
    for key in keys:
        assert apply_key(state, key, 3) is not None


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
    assert len(first.output) == 2
    assert len(second.output) == 2


def test_property_style_q_exits_on_first_press():
    fake = AuditedMystic("Q")
    events = []
    assert (
        run_mystic(
            fake,
            engine(),
            MysticConfig(),
            clock=lambda: 0.0,
            sleep=lambda _: None,
            log=events.append,
        )
        == "quit"
    )
    assert fake.onekey_calls == 1
    assert fake.keypressed_reads == 1
    assert events[:3] == ["key_available=True", "key='Q'", "action='quit'"]
    assert events[-2:] == ["restoring_terminal", "return_to_mystic"]
    assert fake.output.count("\x1b[0m\x1b[?25h") == 1


def test_two_fresh_property_sessions_each_consume_one_q():
    first = AuditedMystic("Q")
    second = AuditedMystic("Q")
    for fake in (first, second):
        assert (
            run_mystic(
                fake,
                engine(),
                MysticConfig(),
                clock=lambda: 0.0,
                sleep=lambda _: None,
            )
            == "quit"
        )
        assert fake.onekey_calls == 1
        assert fake.keypressed_reads == 1


def test_renderer_stays_inside_80x25():
    fake = FakeMystic(["R", "Q"])
    run_mystic(fake, engine(), MysticConfig(), clock=lambda: 0.0, sleep=lambda _: None)
    frame = fake.output[1]
    assert "\n" not in frame
    assert all(ord(char) < 128 for char in frame)
    addresses = re.findall(r"\x1b\[(\d+);(\d+)H", frame)
    assert {int(row) for row, _ in addresses} == set(range(1, 25))
    assert {int(column) for _, column in addresses} == {1}
    assert all(int(row) <= 25 and int(column) <= 80 for row, column in addresses)


def test_full_refresh_does_not_grow_vertically():
    fake = FakeMystic(["R", "R", "Q"])
    run_mystic(fake, engine(), MysticConfig(), clock=lambda: 0.0, sleep=lambda _: None)
    frames = fake.output[1:-1]
    assert len(frames) == 2
    assert all(frame.startswith("\x1b[2J\x1b[H") for frame in frames)
    assert all("\n" not in frame and "\r" not in frame for frame in frames)


def test_raw_output_is_ascii_and_uses_rwrite():
    fake = PropertyMystic(True, ["Q"])
    MysticTerminalAdapter(fake).write_raw("A\N{BOX DRAWINGS LIGHT VERTICAL}B")
    assert fake.output == ["A?B"]


def test_source_startup_failure_is_controlled_by_frontend(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(MysticStartupError, match="not found"):
        build_mystic_engine(
            SourceSpec(kind="file", file=str(missing)),
            receiver_lat=58.0,
            receiver_lon=6.0,
        )
