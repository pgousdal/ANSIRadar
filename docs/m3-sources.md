# M3 Sources, Replay, and Tracks

## Source selection

Use an explicit source kind and endpoint:

```console
ansiradar source-check --source file --file /run/readsb/aircraft.json
ansiradar source-check --source url --url http://127.0.0.1:8080/data/aircraft.json
ansiradar replay-inspect capture.jsonl
```

`source-check` never opens the alternate screen. `replay-inspect` validates the
whole JSON Lines file and reports deterministic record and observation counts.

## Replay format

Each line is one normalized snapshot:

```json
{"timestamp":1720000000.0,"source":"url","messages":123,"aircraft":[{"icao":"478ABC","callsign":"SAS431","latitude":58.5,"longitude":6.3,"altitude_baro_ft":37000,"altitude_geom_ft":37200,"on_ground":false,"ground_speed_kt":451.2,"track_deg":213,"vertical_rate_fpm":-64,"squawk":"1234","category":"A3","emergency":"none","seen_seconds":0.2,"seen_pos_seconds":1.2,"message_count":100,"rssi_dbfs":-18.5}]}
```

`timestamp` is required and drives deterministic replay timing. `seq` is
optional. Aircraft fields use explicit canonical units. Raw HTTP headers,
credentials, and arbitrary server fields are never recorded.

Record a normalized snapshot with:

```console
ansiradar radar --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --once --record capture.jsonl
```

Recording is opt-in. A non-empty existing path is refused unless an append mode
is implemented by the calling API; this prevents accidental corruption of a
completed capture.

## Track aging

Tracks are keyed only by normalized ICAO, so callsign changes do not create new
tracks. The defaults are position stale after 30 seconds, aircraft stale after
60 seconds, and removed after 120 seconds. `--max-tracks` bounds memory. A stale
position is removed from the plotted radar while the aircraft track may remain
visible in counts. Callsigns, altitude, speed, heading, rates, squawk, category,
and signal fields are retained only while the track remains in memory; missing
values are never inferred. Emergency state is cleared after its bounded
retention period or an explicit non-emergency value.

## Failure handling

Timeouts, connection failures, HTTP failures, oversized responses, invalid JSON,
invalid schemas, unavailable files, incomplete files, and replay exhaustion are
classified source errors. Live retries back off from one second to a maximum of
30 seconds and reset after a successful poll. The last valid state remains on
screen during a bounded outage. Detailed diagnostics may be written with
`--log`; terminal status text is shortened and control characters are removed.

## Trust boundary

Only explicitly configured local or trusted-network endpoints are read. HTTPS
certificate verification remains enabled. Do not expose decoder endpoints to the
public internet. Receiver coordinates and aircraft observations can have privacy
or operational implications. Offline replay and fixture sources are preferred
for tests and demonstrations.
