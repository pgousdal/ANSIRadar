# Snapshot command

```text
ansiradar snapshot --source file --file SOURCE --receiver-lat FLOAT --receiver-lon FLOAT
                    [--max-age 60] [--limit N]
                    [--sort distance|callsign|altitude]
                    [--units aviation|metric] [--json]
ansiradar source-check --source file --file SOURCE [--json]
```

The source kind can be `url`, `file`, or `replay`; use `--url` or
`--replay-file` for the other kinds. The default ordering is ascending distance.
Missing sort values come last and
ICAO is the deterministic final tie-breaker. Callsigns compare case-insensitively.
A positioned aircraft whose `seen_pos` exceeds `--max-age` is omitted from the
table but retained in summary totals. If `seen_pos` is absent, freshness is
unknown and the position is included; ANSIRadar has no evidence that it is stale.

Aviation output uses feet, knots, nautical miles, and ft/min. Metric output uses
metres, km/h, kilometres, and m/s. JSON always exposes canonical source units and
computed kilometres/degrees, independent of text display units.

Exit codes are 0 for success, 2 for usage, 3 for an unavailable source, 4 for
invalid JSON, and 5 for an unsupported protocol or malformed schema. Diagnostics
go to stderr. `source-check` reports readability, JSON/schema recognition,
aircraft and position counts, timestamp, and message counter.
