# Mystic BBS Door

ANSIRadar supports Mystic BBS on Linux through the descriptor/socket mode
described by an 11-line `DOOR32.SYS`. It does not implement other BBS dropfiles,
listen for Telnet, or initiate a network connection. Mystic must pass an already
connected socket descriptor using communication type `2`.

## Install

Install the wheel in a stable virtual environment owned by the BBS service:

```console
python3 -m venv /home/mystic/doors/ansiradar/venv
/home/mystic/doors/ansiradar/venv/bin/python -m pip install dist/ansiradar-0.5.0-py3-none-any.whl
```

The BBS user must be able to execute the environment and read the installed
wrapper. The decoder endpoint should remain local or on a trusted private
network; do not expose it to the public internet.

## Wrapper

`examples/mystic/ansiradar-door.sh` accepts the node-specific DOOR32 path and
uses `exec`, quoted paths, an absolute executable, and explicit receiver/source
configuration. Copy it to a root-owned or otherwise protected directory and
adjust the absolute paths for the installation.

```console
/home/mystic/doors/ansiradar/ansiradar-door.sh /path/to/DOOR32.SYS
```

Mystic menu command syntax varies by installation. Configure the menu entry to
invoke the wrapper and pass Mystic's node-specific `DOOR32.SYS` path. Do not
invent a fixed shared dropfile path for multiple nodes.

## Runtime

```console
ansiradar door --door32 /path/to/DOOR32.SYS \
  --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --charset cp437 --color always
```

Door mode defaults to 80x24, CP437 output, ANSI color, no alternate screen,
and no local TTY requirement. `q`, arrows, `j`/`k`, `+`/`=`/`-`, range digits,
`g`, `s`, `l`, `p`, `r`, and `?` are supported. `--idle-timeout` is optional;
source refreshes do not reset it. Session time is taken from DOOR32 and the
door stops conservatively before the supplied limit.

`?` and `h` toggle help, `Esc` closes help, and Enter has no action. For input
troubleshooting, enable a bounded file log explicitly:

```console
ansiradar door ... --debug-input-log /var/log/ansiradar/node1-input.log
```

`ANSIRADAR_DEBUG_INPUT_LOG` is an equivalent environment-variable fallback.
The log records received bytes as hex, decoded keys, and the controlled exit
reason. It also records interesting transport transitions such as
`read_would_block`, `read_eof`, `read_error`, `write_error`, and their disconnect
source. It never writes to the caller socket, stdout, or stderr, and disables
itself if the file cannot be written. Repeated normal timeouts are suppressed.
Use distinct paths for simultaneous nodes.

## DOOR32 assumptions

The parser expects these lines in order: communication type, communication
handle, baud rate, BBS ID, user ID, user name, user alias, security level, time
left in minutes, terminal emulation, and node number. Names are bounded and
terminal-sanitized. The dropfile is read only and never rewritten.

Only communication type `2` is supported and the handle must identify a
connected socket. The descriptor is duplicated before wrapping, so closing the
door does not close an unrelated original descriptor. EOF, reset, broken pipe,
and invalid descriptor outcomes are normal controlled exits.

## Testing

Without Mystic, use the deterministic socket-pair tests and the static mode:

```console
ansiradar radar --source replay --replay-file tests/fixtures/radar-replay.jsonl \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --once \
  --charset cp437 --color never
```

The project tests DOOR32 parsing, descriptor ownership, partial/fragmented
input, Telnet IAC filtering, disconnects, time-left, idle limits, and two
independent runtime instances without public networking.

Verified manually on:

- Mystic BBS on Linux
- `DOOR32.SYS` descriptor/socket mode
- SyncTERM

The practical integration survived normal idle periods, EAGAIN/EWOULDBLOCK,
repeated keyboard input, and normal `q` exit. A two-node production deployment
was not used as a quality gate for every change.

## Exit codes

`0` is a normal quit. `10` is an invalid dropfile, `11` an unsupported
communication mode, `12` an invalid descriptor, `13` startup source failure,
`14` disconnect, `15` time expiry, `16` idle timeout, and `17` unexpected door
failure. These are process outcomes for Mystic, not messages sent to the caller.
