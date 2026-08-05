# Data model

Source snapshots and aircraft are immutable dataclasses. The readsb adapter
recognizes `hex`, `flight`, `lat`, `lon`, `alt_baro`, `alt_geom`, `gs`, `track`,
`baro_rate`, `geom_rate`, `squawk`, `category`, `emergency`, `seen`, `seen_pos`,
`messages`, and `rssi`.

ICAO identifiers are uppercased and callsign whitespace is normalized. Invalid
coordinate pairs become absent. `alt_baro: "ground"` sets a dedicated ground flag.
Malformed optional numbers become absent without losing an otherwise usable
record. A record is rejected only when it is not an object or lacks a usable
`hex` identifier.

Unknown top-level fields are retained as read-only metadata. Distance and initial
bearing are derived for each receiver/snapshot operation rather than stored on
the source aircraft. JSON schema version 1 contains:

```json
{
  "aircraft": [],
  "receiver": {"latitude": 58.3405, "longitude": 6.2812},
  "schema_version": 1,
  "source": {"generated_at": 1720000000.0, "kind": "readsb-json", "location": "aircraft.json", "messages": 123456},
  "summary": {"aircraft_displayed": 0, "aircraft_total": 0, "aircraft_with_position": 0, "aircraft_without_position": 0}
}
```
