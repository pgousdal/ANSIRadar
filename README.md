# ANSIRadar

ANSIRadar turns local readsb, dump1090, and tar1090-compatible `aircraft.json`
data into deterministic terminal snapshots and an interactive 80x24-friendly
ANSI polar radar. M3 adds live URL/file polling, bounded track aging, replay,
recording, and source diagnostics. It does not implement BBS door protocols.

## Install

Python 3.11 or newer is required. Install from a checkout with:

```console
python -m pip install .
ansiradar --version
```

A readsb, dump1090, or tar1090-compatible decoder must produce `aircraft.json`.
ANSIRadar does not install or configure the decoder.

## Use

Receiver coordinates are mandatory for snapshots and are never assumed to be
`0,0`:

```console
ansiradar snapshot --source file --file tests/fixtures/readsb-basic.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812

ansiradar snapshot --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --json

ansiradar source-check --source file --file tests/fixtures/readsb-basic.json

ansiradar radar --source file --file tests/fixtures/readsb-basic.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --once \
  --charset ascii --color never
```

The source kind is explicit: `url`, `file`, or `replay`. `--url`, `--file`, and
`--replay-file` are mutually exclusive and may imply the kind. The legacy form
`--source PATH` remains accepted for local files. `ANSIRADAR_SOURCE`,
`ANSIRADAR_RECEIVER_LAT`, and `ANSIRADAR_RECEIVER_LON` can supply defaults;
command-line values take precedence.

Live radar example:

```console
ansiradar radar --source url \
  --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --refresh 2
```

Offline replay and diagnostics:

```console
ansiradar source-check --source file --file tests/fixtures/readsb-aircraft.json
ansiradar replay-inspect tests/fixtures/radar-replay.jsonl
ansiradar radar --source replay --replay-file tests/fixtures/radar-replay.jsonl \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --once --color never --symbols ascii
```

Text output begins with receiver and aircraft totals, followed by an ASCII table:

```text
CALL       ICAO     ALT        SPD       HDG   DIST      BRG   AGE
SAS431     478ABC   37000 ft   451 kt    213   9.6 nm    006   1s
```

JSON output has schema version 1 and contains `source`, `receiver`, `summary`, and
deterministically ordered `aircraft` members. See [snapshot command](docs/snapshot-command.md).

## Privacy and safety

ANSIRadar performs only explicit, user-requested reads. It does not control an
SDR, transmit radio signals, write to readsb, poll in the background, or receive
raw RF samples. It receives decoded aircraft metadata. Receiver coordinates and
aircraft data can be sensitive; avoid publishing local captures or exact private
receiver locations.

See [source setup](docs/readsb-source.md), [live sources and tracks](docs/m3-sources.md),
[data model](docs/data-model.md), [architecture](docs/architecture.md),
[radar command](docs/radar-command.md), and [keyboard controls](docs/keyboard-controls.md).
