"""Deterministic M4 DOOR32, transport, input, and runtime tests."""

import socket
from pathlib import Path

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
from ansiradar.transport import DescriptorSocketTransport, MemoryTransport
from ansiradar.transport_input import decode_bytes

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
