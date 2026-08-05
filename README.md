# ANSIRadar

ANSIRadar turns readsb/dump1090 `aircraft.json` data into deterministic,
80-column-friendly terminal snapshots. M1 is a read-only data adapter and snapshot
CLI; it is not the future interactive radar display.

## Install

Python 3.11 or newer is required. Install from a checkout with:

```console
python -m pip install .
ansiradar --version
```

A readsb or dump1090-compatible decoder must produce `aircraft.json`. ANSIRadar
does not install or configure the decoder.

## Use

Receiver coordinates are mandatory for snapshots and are never assumed to be
`0,0`:

```console
ansiradar snapshot --source tests/fixtures/readsb-basic.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812

ansiradar snapshot --source http://localhost:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --json

ansiradar source-check --source tests/fixtures/readsb-basic.json
```

`ANSIRADAR_SOURCE`, `ANSIRADAR_RECEIVER_LAT`, and `ANSIRADAR_RECEIVER_LON` can
supply defaults; command-line values take precedence. Snapshot options include
`--max-age`, `--limit`, `--sort`, `--units`, and `--json`.

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

See [source setup](docs/readsb-source.md), [data model](docs/data-model.md), and
[architecture](docs/architecture.md).
