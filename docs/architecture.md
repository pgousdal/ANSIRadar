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

The Python edition is the maintained implementation in this repository. Its
local interactive mode and Mystic door mode share the transport-neutral radar
runtime while keeping source I/O, normalized observations, track state, and
rendering separated. The standalone C99 edition is maintained in the separate
`pgousdal/ANSIRadar-C` repository.
