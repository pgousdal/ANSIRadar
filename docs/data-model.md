# Data model

`AircraftObservation` and `ObservationSnapshot` are immutable normalized
dataclasses. The decoder recognizes `hex`/`icao`, `flight`, `lat`, `lon`,
`alt_baro`, `alt_geom`, `gs`, `track`, `baro_rate`, `geom_rate`, `squawk`,
`category`, `emergency`, `seen`, `seen_pos`, `messages`, and `rssi`, while
ignoring tar1090-specific extras such as `mlat`, `tisb`, `nac_p`, and `sil`.

ICAO identifiers are uppercased and must be exactly six hexadecimal digits.
Callsign whitespace is normalized and terminal control/ANSI sequences are
removed. Invalid coordinate pairs become absent. `alt_baro: "ground"` sets a
dedicated ground flag; missing ground state remains distinct from an explicit
false state in observations. Malformed optional numbers become absent without
losing an otherwise usable record. A record is skipped when it is not an object
or lacks a usable ICAO identifier, and the skip count is observable.

Unknown top-level fields are retained as bounded source metadata. Distance and
initial bearing are derived for each receiver/snapshot operation rather than
stored on the source aircraft. Replay records use canonical normalized fields
and explicit timestamps. JSON schema version 1 contains:

```json
{
  "aircraft": [],
  "receiver": {"latitude": 58.3405, "longitude": 6.2812},
  "schema_version": 1,
  "source": {"generated_at": 1720000000.0, "kind": "readsb-json", "location": "aircraft.json", "messages": 123456},
  "summary": {"aircraft_displayed": 0, "aircraft_total": 0, "aircraft_with_position": 0, "aircraft_without_position": 0}
}
```
