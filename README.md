# ANSIRadar

Live ADS-B ANSI radar and Mystic BBS door written in Python.

This repository is the Python edition of ANSIRadar. It supports live local
readsb, dump1090, and tar1090-compatible aircraft data, deterministic replay,
track management, interactive ANSI rendering, and Mystic BBS Linux
`DOOR32.SYS` descriptor/socket mode.

The Python project requires Python 3.11 or newer and does not require an SDR,
cloud service, account, browser, database, Docker, or public internet access.

## Install

```console
python -m pip install .
ansiradar --version
```

For development, install the `dev` extra. The package exposes the `ansiradar`
console entry point.

## Python / Mystic edition

```console
ansiradar radar --source file --file tests/fixtures/readsb-basic.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --once --charset ascii --color never
```

Live local decoder endpoint:

```console
ansiradar radar --source url \
  --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812
```

Mystic door mode:

```console
ansiradar door --door32 /path/to/DOOR32.SYS \
  --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --charset cp437 --color always
```

Offline diagnostics and replay:

```console
ansiradar source-check --source file --file tests/fixtures/readsb-aircraft.json
ansiradar replay-inspect tests/fixtures/radar-replay.jsonl
ansiradar radar --source replay --replay-file tests/fixtures/radar-replay.jsonl \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --once --charset ascii --color never
```

Receiver coordinates are mandatory and are never assumed to be `0,0`.
`source-check` and replay inspection never open the alternate screen.

## C edition

The standalone C99 80x25 ANSI/CP437 edition is maintained separately:

https://github.com/pgousdal/ANSIRadar-C

It is not part of this repository and is not built or tested by this project.

## Mystic

The Mystic integration uses an 11-line `DOOR32.SYS` and communication type `2`,
where Mystic passes an already-connected socket descriptor. The descriptor is
duplicated for ownership safety. The runtime supports CP437/ASCII profiles,
fragmented ANSI input, bounded IAC handling, source retries, time-left limits,
idle timeouts, disconnect cleanup, and optional file-only input diagnostics.

See [Mystic door setup](docs/mystic-door.md) and the wrapper under
`examples/mystic/`. Verified manually on:

- Mystic BBS on Linux
- `DOOR32.SYS` descriptor/socket mode
- SyncTERM

## Privacy and safety

ANSIRadar performs only explicit, user-requested reads. It receives decoded
aircraft metadata and does not control an SDR, transmit radio signals, or
modify a decoder. Receiver coordinates and aircraft data can be sensitive;
avoid publishing local captures or exact private receiver locations. Do not
expose decoder endpoints directly to the public internet.

See [architecture](docs/architecture.md), [sources and tracks](docs/m3-sources.md),
[data model](docs/data-model.md), [radar command](docs/radar-command.md),
[terminal compatibility](docs/terminal-compatibility.md), and
[keyboard controls](docs/keyboard-controls.md).
