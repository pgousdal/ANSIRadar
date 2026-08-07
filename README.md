# ANSIRadar

ANSIRadar turns local readsb, dump1090, and tar1090-compatible `aircraft.json`
data into deterministic terminal snapshots, an interactive 80x24-friendly ANSI
polar radar, and a Mystic BBS door runtime. M4 supports Mystic BBS on Linux
through `DOOR32.SYS` descriptor/socket mode.

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

ansiradar door --door32 /path/to/DOOR32.SYS \
  --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --charset cp437 --color always
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
[radar command](docs/radar-command.md), [Mystic door setup](docs/mystic-door.md),
and [keyboard controls](docs/keyboard-controls.md).

## 80x25 C edition

The repository also includes a standalone C99 classic-BBS edition with a native
80x25 CP437/ANSI layout, provider abstraction, CSV replay, virtual screen
buffer, and incremental cursor-addressed rendering. Build it with `cmake` or
the fallback `Makefile`; see [80x25 edition](docs/80x25-edition.md).
