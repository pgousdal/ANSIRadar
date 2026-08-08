import ast
import logging
import re
import runpy
import sys
import types
from pathlib import Path

import pytest

from ansiradar.mystic import (
    MysticConfig,
    MysticInputError,
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

    def getkey(self):
        return self.keys.pop(0)


class PropertyMystic:
    def __init__(self, available, keys=()):
        self.keypressed = available
        self.keys = list(keys)
        self.output = []

    def rwrite(self, text):
        self.output.append(text)

    def getkey(self):
        return self.keys.pop(0)


class AuditedMystic:
    def __init__(self, *keys):
        self._keys = list(keys)
        self.output = []
        self.keypressed_reads = 0
        self.onekey_calls = 0
        self.getkey_calls = 0
        self.flush_calls = 0

    @property
    def keypressed(self):
        self.keypressed_reads += 1
        return bool(self._keys)

    def rwrite(self, text):
        self.output.append(text)

    def getkey(self):
        self.getkey_calls += 1
        return self._keys.pop(0)

    def flush(self):
        self.flush_calls += 1

    def onekey(self, keys, echo):
        del keys, echo
        self.onekey_calls += 1
        raise AssertionError("onekey must not be used by the radar event loop")

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
    assert map_key(ord("Q")) == "Q"
    fake = FakeMystic(["K"])
    assert read_mystic_key(fake) == "K"

    assert read_mystic_key(PropertyMystic(True, [("J", False)])) == "J"


def test_keypressed_property_and_method_compatibility():
    assert read_mystic_key(PropertyMystic(False)) is None
    assert read_mystic_key(PropertyMystic(True, [("Q", False)])) == "Q"
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
    fake = AuditedMystic(("Q", False))
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
    assert fake.getkey_calls == 1
    assert fake.onekey_calls == 0
    assert fake.keypressed_reads == 1
    assert events[:4] == [
        "key_available=True",
        "getkey raw=('Q', False)",
        "key='Q'",
        "action='quit'",
    ]
    assert events[-2:] == ["restoring_terminal", "return_to_mystic"]
    assert fake.output.count("\x1b[0m\x1b[?25h") == 1
    assert fake.flush_calls == 1


def test_two_fresh_property_sessions_each_consume_one_q():
    first = AuditedMystic(("Q", False))
    second = AuditedMystic(("Q", False))
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
        assert fake.getkey_calls == 1
        assert fake.onekey_calls == 0
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


def test_event_loop_rejects_onekey_only_api():
    class OnKeyOnly:
        keypressed = True

        def onekey(self, keys, echo):
            del keys, echo
            raise AssertionError("onekey must not consume radar events")

    with pytest.raises(MysticInputError, match="getkey"):
        MysticTerminalAdapter(OnKeyOnly()).read_key()


def test_mpy_main_returns_none_and_falls_through_to_end():
    path = Path(__file__).parents[1] / "integrations" / "mystic" / "ansiradar.mpy"
    tree = ast.parse(path.read_text())
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    returns = [node for node in ast.walk(main) if isinstance(node, ast.Return)]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Constant)
    assert returns[0].value.value is None
    source = path.read_text()
    assert "logging.info(\"mpy_end\")" in source
    assert "sys.exit" not in source
    assert "SystemExit" not in source
    assert "bbs.shutdown" not in source
    assert "bbs.menucmd" not in source


def test_mpy_q_completion_returns_to_mystic_without_commands(monkeypatch):
    path = Path(__file__).parents[1] / "integrations" / "mystic" / "ansiradar.mpy"
    events = []

    class FakeLogger:
        def info(self, message):
            events.append(message)

    class FakeBbs(types.ModuleType):
        def __init__(self):
            super().__init__("mystic_bbs")
            self.calls = []

        def rwrite(self, text):
            self.calls.append(("rwrite", text))

        def __getattr__(self, name):
            def unexpected_call(*args, **kwargs):
                self.calls.append((name, args, kwargs))
                raise AssertionError(f"unexpected Mystic API call: {name}")

            return unexpected_call

    bbs = FakeBbs()
    mystic = types.ModuleType("ansiradar.mystic")
    mystic.MysticConfig = lambda **kwargs: types.SimpleNamespace(
        **kwargs, poll_interval=1.0
    )
    mystic.build_mystic_engine = lambda *args, **kwargs: (object(), object())

    def fake_run_mystic(*args, **kwargs):
        kwargs["log"]("action='quit'")
        kwargs["log"]("restoring_terminal")
        return "quit"

    mystic.run_mystic = fake_run_mystic
    sources = types.ModuleType("ansiradar.sources")
    sources.SourceSpec = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "mystic_bbs", bbs)
    monkeypatch.setitem(sys.modules, "ansiradar.mystic", mystic)
    monkeypatch.setitem(sys.modules, "ansiradar.sources", sources)
    monkeypatch.setattr("logging.basicConfig", lambda **kwargs: None)
    monkeypatch.setattr("logging.info", events.append)
    real_get_logger = logging.getLogger

    def get_logger(name=None):
        if name == "ansiradar.mystic":
            return FakeLogger()
        return real_get_logger(name)

    monkeypatch.setattr("logging.getLogger", get_logger)

    namespace = runpy.run_path(str(path), run_name="__main__")

    assert namespace["main"]() is None
    assert events == [
        "startup",
        "action='quit'",
        "restoring_terminal",
        "run_mystic_returned",
        "main_return",
        "mpy_end",
        "action='quit'",
        "restoring_terminal",
        "run_mystic_returned",
    ]
    assert bbs.calls == []


def test_source_startup_failure_is_controlled_by_frontend(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(MysticStartupError, match="not found"):
        build_mystic_engine(
            SourceSpec(kind="file", file=str(missing)),
            receiver_lat=58.0,
            receiver_lon=6.0,
        )
