# Architecture

M3 separates source I/O, normalization, track state, and terminal rendering.
`UrlSource`, `FileSource`, and `ReplaySource` implement the source protocol and
return normalized `ObservationSnapshot` values. They never access terminal
sessions, keyboard input, screen buffers, or ANSI serializers.

The decoder compatibility layer accepts the common readsb/dump1090/tar1090
`aircraft.json` shape. `TrackManager` upserts by normalized ICAO, retains
omitted fields for a bounded lifetime, ages positions independently, rejects
out-of-order observations, and bounds active memory. `SourcePoller` provides
interval scheduling, retry backoff, last-good-snapshot retention, and compact
health status.

The CLI adapts track snapshots to the existing pure radar renderer. One-shot
file and replay modes do not enter the alternate screen; interactive mode uses
the existing exception-safe terminal lifecycle and differential rendering.

M4 adds `parse_door32`, `DescriptorSocketTransport`, `LocalTTYTransport`, and
`MemoryTransport`. `run_interactive` is shared by local and BBS sessions. The
DOOR32 path is parsed before caller output, the supplied descriptor is duplicated
for ownership safety, and `BBSTerminalProfile` performs explicit CP437/ASCII/
Unicode encoding without local TTY probing.

M5 keeps that Python Mystic transport/runtime as the production DOOR32 path and
hardens the separate C99 `ansiradar80` path as a classic 80x25 renderer. The C
provider table returns normalized aircraft to a virtual screen; it has no
knowledge of DOOR32 or Python. This deliberately avoids introducing a second
native C DOOR32 implementation while allowing the C renderer to be tested
independently with files and CSV replay.
