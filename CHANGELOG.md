# Changelog

## 0.4.0

- Add URL, local-file, and deterministic JSON Lines replay sources.
- Add normalized observation parsing for readsb, dump1090, and tar1090-compatible
  `aircraft.json` documents.
- Add bounded ICAO-keyed track management with field retention, stale positions,
  out-of-order protection, expiry, and source-health status.
- Add replay recording, `source-check`, and `replay-inspect` diagnostics.
- Add bounded response/line/aircraft input handling and terminal-safe diagnostics.
