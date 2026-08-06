# Changelog

## 0.5.0

- Add a Mystic Linux DOOR32.SYS interactive BBS door runtime.
- Add descriptor/socket, local TTY, and deterministic memory transports.
- Add CP437/ASCII BBS profiles, fragmented ANSI input, defensive IAC handling,
  time-left and idle limits, disconnect handling, and node context.
- Add deterministic DOOR32, socket-pair, and door-session coverage.

## 0.4.0

- Add URL, local-file, and deterministic JSON Lines replay sources.
- Add normalized observation parsing for readsb, dump1090, and tar1090-compatible
  `aircraft.json` documents.
- Add bounded ICAO-keyed track management with field retention, stale positions,
  out-of-order protection, expiry, and source-health status.
- Add replay recording, `source-check`, and `replay-inspect` diagnostics.
- Add bounded response/line/aircraft input handling and terminal-safe diagnostics.
