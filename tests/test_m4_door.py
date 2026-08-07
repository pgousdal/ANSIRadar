"""Deterministic M4 DOOR32, transport, input, and runtime tests."""

import errno
import socket
from pathlib import Path
from typing import Any, cast

import pytest

from ansiradar.bbs import BBSTerminalProfile
from ansiradar.cli import main
from ansiradar.door import (
    DOOR_EXIT_DISCONNECT,
    DOOR_EXIT_IDLE,
    DOOR_EXIT_TIME_EXPIRED,
    Door32Error,
    UnsupportedCommunicationMode,
    parse_door32,
)
from ansiradar.poller import SourcePoller
from ansiradar.radar.engine import RadarEngine
from ansiradar.runtime import RuntimeConfig, run_interactive
from ansiradar.sources.file import FileSource
from ansiradar.tracking import TrackManager
from ansiradar.transport import (
    DescriptorSocketTransport,
    MemoryTransport,
    TransportDisconnected,
)
from ansiradar.transport_input import KeyDecoder, decode_bytes, read_key

FIXTURES = Path(__file__).parent / "fixtures"


def door32_text(
    *,
    communication_type: int = 2,
    time_left: int = 30,
    user_name: str = "Test User",
    alias: str = "TestAlias",
) -> str:
    return "\n".join(
        [
            str(communication_type),
            "7",
            "115200",
            "Mystic",
            "42",
            user_name,
            alias,
            "10",
            str(time_left),
            "1",
            "3",
        ]
    )


def test_door32_valid_crlf_without_final_newline(tmp_path: Path) -> None:
    path = tmp_path / "DOOR32.SYS"
    path.write_bytes(door32_text().replace("\n", "\r\n").encode())
    info = parse_door32(path)
    assert info.communication_type == 2
    assert info.handle == 7
    assert info.user_name == "Test User"
    assert info.user_alias == "TestAlias"
    assert info.node_number == 3


def test_representative_mystic_fixture() -> None:
    info = parse_door32(FIXTURES / "door32-valid.sys")
    assert (info.communication_type, info.handle, info.node_number) == (2, 7, 3)


@pytest.mark.parametrize(
    "payload",
    [
        "\n".join(["2"] * 10),
        door32_text() + "\nextra",
        door32_text().replace("115200", "bad"),
        door32_text(time_left=-1),
    ],
)
def test_door32_invalid_payloads(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "DOOR32.SYS"
    path.write_text(payload)
    with pytest.raises(Door32Error):
        parse_door32(path)


def test_door32_unsupported_mode(tmp_path: Path) -> None:
    path = tmp_path / "DOOR32.SYS"
    path.write_text(door32_text(communication_type=0))
    with pytest.raises(UnsupportedCommunicationMode):
        parse_door32(path)


def test_door32_names_are_terminal_safe(tmp_path: Path) -> None:
    path = tmp_path / "DOOR32.SYS"
    path.write_text(door32_text(user_name="A\x1b[31m", alias="B\x00C"))
    info = parse_door32(path)
    assert "\x1b" not in info.user_name
    assert "\x00" not in info.user_alias


def test_descriptor_transport_round_trip_and_ownership() -> None:
    left, right = socket.socketpair()
    try:
        transport = DescriptorSocketTransport(right.fileno())
        left.sendall(b"q")
        assert transport.read(8, timeout=1) == b"q"
        transport.write(b"ok")
        assert left.recv(2) == b"ok"
        transport.close()
        right.sendall(b"still-open")
        assert left.recv(10) == b"still-open"
    finally:
        left.close()
        right.close()


def test_descriptor_transport_invalid_descriptor() -> None:
    from ansiradar.door import InvalidDescriptor

    with pytest.raises(InvalidDescriptor):
        DescriptorSocketTransport(-1)


def test_input_fragmentation_and_telnet_defense() -> None:
    assert decode_bytes([b"\x1b", b"[", b"A"]) == ["UP"]
    assert decode_bytes([b"j", b"k", b"\r", b"\x1b"]) == ["j", "k", "ENTER", "\x1b"]
    assert decode_bytes([b"\xff\xfb\x01q"]) == ["q"]
    assert decode_bytes([b"\xff\xfa", b"\x01\xff", b"\xf0q"]) == ["q"]
    assert decode_bytes([b"\x1b[999999999999999999Aq"]) == ["\x1b", "q"]


def test_read_key_preserves_every_key_from_one_read() -> None:
    transport = MemoryTransport(b"jp1")
    decoder = KeyDecoder()
    assert read_key(transport, decoder, timeout=0) == "j"
    assert read_key(transport, decoder, timeout=0) == "p"
    assert read_key(transport, decoder, timeout=0) == "1"


def test_read_key_preserves_key_before_fragmented_arrow() -> None:
    transport = MemoryTransport(b"j\x1b[A")
    decoder = KeyDecoder()
    assert read_key(transport, decoder, timeout=0) == "j"
    assert read_key(transport, decoder, timeout=0) == "UP"


class _FakeSocket:
    def __init__(self, *receives: object) -> None:
        self.receives = list(receives)

    def recv(self, size: int) -> bytes:
        del size
        result = self.receives.pop(0)
        if isinstance(result, BaseException):
            raise result
        return cast(bytes, result)

    def close(self) -> None:
        return

    def send(self, data: bytes) -> int:
        return len(data)


def _fake_descriptor(*receives: object) -> DescriptorSocketTransport:
    transport = object.__new__(DescriptorSocketTransport)
    transport.socket = cast(Any, _FakeSocket(*receives))
    transport.connected = True
    transport._debug = None
    transport._last_event = None
    return transport


def test_descriptor_timeout_and_would_block_stay_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)

    fake = _fake_descriptor(
        BlockingIOError(errno.EAGAIN, "would block"),
        BlockingIOError(errno.EWOULDBLOCK, "would block"),
        InterruptedError(),
    )
    monkeypatch.setattr(module.select, "select", lambda *args: ([], [], []))
    assert fake.read(8, timeout=0) == b""
    monkeypatch.setattr(module.select, "select", lambda *args: ([fake.socket], [], []))
    assert fake.read(8, timeout=0) == b""
    assert fake.read(8, timeout=0) == b""
    assert fake.read(8, timeout=0) == b""
    assert fake.is_connected()


def test_transport_debug_events_are_interesting_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)
    events: list[str] = []
    fake = _fake_descriptor(BlockingIOError(errno.EAGAIN, "would block"))
    fake.set_debug(events.append)
    monkeypatch.setattr(module.select, "select", lambda *args: ([], [], []))
    fake.read(8, timeout=0)
    fake.read(8, timeout=0)
    monkeypatch.setattr(module.select, "select", lambda *args: ([fake.socket], [], []))
    fake.read(8, timeout=0)
    assert events == ["read_timeout", "read_would_block errno=11"]


def test_data_then_eagain_stays_connected_and_read_key_preserves_j(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)

    fake = _fake_descriptor(b"j", BlockingIOError(errno.EAGAIN, "would block"))
    monkeypatch.setattr(module.select, "select", lambda *args: ([fake.socket], [], []))
    decoder = KeyDecoder()
    assert read_key(fake, decoder, timeout=0) == "j"
    assert read_key(fake, decoder, timeout=0) is None
    assert fake.is_connected()


def test_runtime_j_then_eagain_does_not_disconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)
    fake = _fake_descriptor(b"j", BlockingIOError(errno.EAGAIN, "would block"), b"q")
    monkeypatch.setattr(
        module.select,
        "select",
        lambda *args: ([fake.socket], [fake.socket], []),
    )
    result = run_interactive(_engine([0.0]), fake, RuntimeConfig(), clock=lambda: 0.0)
    assert result.reason == "quit"


@pytest.mark.parametrize(
    "error",
    [ConnectionResetError(errno.ECONNRESET, "reset"), OSError(errno.EBADF, "bad fd")],
)
def test_real_socket_errors_disconnect(
    monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)

    fake = _fake_descriptor(error)
    monkeypatch.setattr(module.select, "select", lambda *args: ([fake.socket], [], []))
    with pytest.raises(TransportDisconnected):
        fake.read(8, timeout=0)
    assert not fake.is_connected()


def test_recv_eof_disconnects(monkeypatch: pytest.MonkeyPatch) -> None:
    import ansiradar.transport as transport_module

    module = cast(Any, transport_module)

    fake = _fake_descriptor(b"")
    monkeypatch.setattr(module.select, "select", lambda *args: ([fake.socket], [], []))
    assert fake.read(8, timeout=0) == b""
    assert not fake.is_connected()


def test_read_key_fragmented_arrow_across_reads() -> None:
    class Chunks(MemoryTransport):
        def __init__(self) -> None:
            super().__init__()
            self.chunks = [b"\x1b", b"[", b"A"]

        def read(self, size: int, timeout: float | None = None) -> bytes:
            del size, timeout
            return self.chunks.pop(0) if self.chunks else b""

    transport = Chunks()
    decoder = KeyDecoder()
    assert read_key(transport, decoder, timeout=0.01) is None
    assert read_key(transport, decoder, timeout=0.01) is None
    assert read_key(transport, decoder, timeout=0.01) == "UP"


def test_timeout_is_not_disconnect() -> None:
    transport = MemoryTransport()
    decoder = KeyDecoder()
    assert read_key(transport, decoder, timeout=0.01) is None
    assert transport.is_connected()


def _engine(clock: list[float]) -> RadarEngine:
    source = FileSource(str(FIXTURES / "readsb-aircraft.json"))
    poller = SourcePoller(source, clock=lambda: clock[0], poll_interval=1)
    tracks = TrackManager(clock=lambda: clock[0])
    return RadarEngine(
        poller,
        tracks,
        receiver_lat=58.3405,
        receiver_lon=6.2812,
    )


def test_runtime_uses_transport_no_alt_screen() -> None:
    clock = [0.0]
    transport = MemoryTransport(b"q")
    result = run_interactive(
        _engine(clock),
        transport,
        RuntimeConfig(charset="cp437", color=True),
        clock=lambda: clock[0],
    )
    assert result.reason == "quit"
    assert b"\x1b[?1049h" not in transport.outgoing
    assert b"\x1b[?25l" in transport.outgoing
    assert b"\x1b[?25h" in transport.outgoing


def test_runtime_disconnect_is_normal() -> None:
    clock = [0.0]
    transport = MemoryTransport()
    transport.connected = False
    result = run_interactive(
        _engine(clock),
        transport,
        RuntimeConfig(),
        clock=lambda: clock[0],
    )
    assert result.reason == "disconnect"


def test_runtime_only_q_is_quit_key(tmp_path: Path) -> None:
    clock = [0.0]
    transport = MemoryTransport(b"jp1?\x1b\rq")
    result = run_interactive(
        _engine(clock),
        transport,
        RuntimeConfig(debug_input_log=str(tmp_path / "input.log")),
        clock=lambda: clock[0],
    )
    assert result.reason == "quit"
    assert result.frames >= 5


def test_help_controls_match_runtime() -> None:
    from ansiradar.render.buffer import ScreenBuffer
    from ansiradar.runtime import _help

    buffer = ScreenBuffer(80, 24)
    _help(buffer, "ascii")
    text = buffer.serialize()
    assert "Enter no action" in text
    assert "? or h toggles help" in text
    assert "t trails" not in text


def test_input_debug_log_is_opt_in_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "input.log"
    transport = MemoryTransport(b"jq")
    result = run_interactive(
        _engine([0.0]),
        transport,
        RuntimeConfig(debug_input_log=str(path)),
        clock=lambda: 0.0,
    )
    text = path.read_text()
    assert result.reason == "quit"
    assert "raw=6a71" in text
    assert "key='j'" in text
    assert "key='q'" in text
    assert "exit='quit'" in text


def test_debug_log_write_failure_does_not_crash(tmp_path: Path) -> None:
    transport = MemoryTransport(b"q")
    result = run_interactive(
        _engine([0.0]),
        transport,
        RuntimeConfig(debug_input_log=str(tmp_path / "missing" / "input.log")),
        clock=lambda: 0.0,
    )
    assert result.reason == "quit"


def test_debug_log_disabled_by_default(tmp_path: Path) -> None:
    transport = MemoryTransport(b"q")
    run_interactive(_engine([0.0]), transport, RuntimeConfig(), clock=lambda: 0.0)
    assert list(tmp_path.iterdir()) == []


def test_runtime_time_limit_is_injected() -> None:
    clock = [0.0]
    transport = MemoryTransport()

    def advancing_clock() -> float:
        clock[0] += 1.0
        return clock[0]

    result = run_interactive(
        _engine(clock),
        transport,
        RuntimeConfig(session_seconds=6, time_warning=5),
        clock=advancing_clock,
    )
    assert result.reason == "time_expired"
    assert DOOR_EXIT_TIME_EXPIRED == 15


def test_runtime_idle_limit_is_injected() -> None:
    clock = [0.0]
    transport = MemoryTransport()

    def advancing_clock() -> float:
        clock[0] += 1.0
        return clock[0]

    result = run_interactive(
        _engine(clock),
        transport,
        RuntimeConfig(idle_timeout=4, idle_warning=1),
        clock=advancing_clock,
    )
    assert result.reason == "idle_timeout"
    assert DOOR_EXIT_IDLE == 16
    assert DOOR_EXIT_DISCONNECT == 14


def test_bbs_profile_encoding_and_lifecycle() -> None:
    profile = BBSTerminalProfile(charset="ascii", color=False)
    assert b"\x1b" not in profile.encode("A\x1bB")
    assert b"\x1b[?25l" in profile.startup()
    assert b"\x1b[?25h" in profile.shutdown()


def test_door_cli_socket_pair_without_local_tty(tmp_path: Path) -> None:
    left, right = socket.socketpair()
    path = tmp_path / "DOOR32.SYS"
    path.write_text(door32_text().replace("\n7\n", f"\n{right.fileno()}\n"))
    try:
        left.sendall(b"q")
        result = main(
            [
                "door",
                "--door32",
                str(path),
                "--source",
                "file",
                "--file",
                str(FIXTURES / "readsb-aircraft.json"),
                "--receiver-lat",
                "58.3405",
                "--receiver-lon",
                "6.2812",
                "--charset",
                "ascii",
                "--color",
                "never",
            ]
        )
        assert result == 0
    finally:
        right.close()
        left.settimeout(1)
        received = bytearray()
        while True:
            try:
                chunk = left.recv(65536)
            except TimeoutError:
                break
            if not chunk:
                break
            received.extend(chunk)
        left.close()
    assert b"ANSIRadar 0.5.0" in received
    assert b"\x1b[?1049h" not in received


def test_two_memory_sessions_are_independent() -> None:
    first = MemoryTransport(b"q")
    second = MemoryTransport(b"q")
    first_result = run_interactive(
        _engine([0.0]), first, RuntimeConfig(context="A N1"), clock=lambda: 0.0
    )
    second_result = run_interactive(
        _engine([0.0]), second, RuntimeConfig(context="B N2"), clock=lambda: 0.0
    )
    assert first_result.reason == second_result.reason == "quit"
    assert b"A\x1b[0m \x1b[0mN\x1b[0m1" in first.outgoing
    assert b"B\x1b[0m \x1b[0mN\x1b[0m2" in second.outgoing
    assert b"B\x1b[0m \x1b[0mN\x1b[0m2" not in first.outgoing
