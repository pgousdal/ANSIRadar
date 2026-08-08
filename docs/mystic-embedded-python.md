# Mystic Embedded Python

ANSIRadar has a Mystic-native integration for Mystic BBS 1.12 A48. It runs as
an embedded Python 3 `.mpy` script and calls `mystic_bbs` for all terminal I/O.
Mystic retains ownership of the Telnet session. This path does not read
`DOOR32.SYS`, duplicate descriptors, negotiate Telnet, use `termios`, or use
stdin/stdout.

The first real Mystic 1.12 A48 test reached the radar successfully but exposed
two defects in the initial frontend: it treated `keypressed` as a function and
sent Unicode/80-column differential frames. Those defects are addressed here.
Another real Mystic 1.12 A48 test is still required before calling this path
fully verified.

DOOR32 remains available for generic BBS integration. Embedded Python is the
preferred Mystic-native integration.

## Installation

Mystic embeds the system Python 3 library, so the package and its dependencies
must be installed into that same Python environment. Do not rely on an
interactive shell virtualenv or `PATH`:

```console
cd /path/to/ANSIRadar
python3 -m pip install --target /home/mystic/doors/ansiradar/site-packages .
```

Copy the script to the stable path used by the entry point:

```console
mkdir -p /home/mystic/doors/ansiradar
cp integrations/mystic/ansiradar.mpy /home/mystic/doors/ansiradar/
```

The `.mpy` adds `/home/mystic/doors/ansiradar/site-packages` to `sys.path`
explicitly; it does not depend on shell activation. This is the import path
used by the supplied script and must match the target directory above.

## Menu Entry

In a Mystic menu configure:

```text
Command: GZ - Execute Mystic Python 3.x (MPY) Script
Data: /home/mystic/doors/ansiradar/ansiradar.mpy
```

`GZ` and the full-path behavior are documented by Mystic's [Python scripting
guide](https://wiki.mysticbbs.com/doku.php?id=python_getstarted). The API
details are in Mystic's [Python function reference](https://wiki.mysticbbs.com/doku.php?id=python_functions).
No external door command or dropfile is involved.

## Configuration

The example defaults are in the top-level `main()` of
`integrations/mystic/ansiradar.mpy`:

```text
source = file
file = /home/mystic/doors/data/aircraft.json
receiver_lat = 58.662
receiver_lon = 6.717
range_nm = 100
```

They can be overridden with `ANSIRADAR_SOURCE`, `ANSIRADAR_FILE`,
`ANSIRADAR_RECEIVER_LAT`, `ANSIRADAR_RECEIVER_LON`, and
`ANSIRADAR_RANGE_NM`. The file source accepts readsb/dump1090-compatible
`aircraft.json`; the existing ANSIRadar source registry is used.

The renderer defaults to 80x25. Frames use explicit cursor positioning for
every full refresh, clear the screen, and contain no row separators. The
nominal screen is 80x25, but Mystic uses a conservative 79x24 drawing area:
column 80 and row 25 are never written by radar frames, avoiding terminal
wrap/scroll behavior. The status and help overlays are clipped to that area.
Mystic uses ASCII symbols by default and currently rejects other charsets.
CP437 is not enabled until its behavior through the actual Mystic embedded
runtime is verified.

## Controls

`Q` quits immediately on the first press. `H` or `?` toggles help, Up/Down
select previous/next aircraft, `K`/`J` are reliable previous/next fallbacks,
`+`/`=` and `-` zoom, `1`/`2`/`3`/`4` select 25/50/100/200 NM, `G` toggles
ground aircraft, `S` cycles sorting, `L` cycles labels, `P` pauses, and `R`
refreshes the source. Enter, Left, Right, and Tab currently do nothing.

Mystic documents `keypressed` as a boolean property, not a function. The
adapter supports that real property and also tolerates method-style fakes used
by tests. For the nonblocking radar loop, when input is available it calls
`getkey()` exactly once to consume the queued character. `onekey(keylist,
echo)` is intentionally not used here because it is a blocking constrained
prompt and real Mystic showed that combining it with `keypressed` waits for a
second physical key. Mystic A48's bundled Python notes and demo specify
`getkey()` as returning `(char, extended)`; the adapter consumes the first
tuple element. String and integer test doubles are also accepted. Arrow
semantics are not claimed. `J`/`K` are the reliable next/previous controls.

## Getkey Probe

The minimal probe at
`integrations/mystic/tools/keyprobe.mpy` uses only `keypressed` and `getkey`.
Copy it to the Mystic script directory and run it with a GZ menu entry whose
data is `/home/mystic/doors/ansiradar/keyprobe.mpy`. Press keys followed by Q;
inspect `/home/mystic/doors/ansiradar/keyprobe.log` for timestamps, raw
`(char, extended)` values, types, and representations. It does not use
`onekey`, stdin, sockets, or terminal modes.

## Logging and Errors

The default local log is `/home/mystic/doors/ansiradar/mystic.log`. It records
startup, key availability transitions, raw `getkey` values, key actions,
`mpy_end`, and exceptions, but never passwords or user data. Startup
and rendering failures display a short ANSI-safe message and return to Mystic;
the traceback is logged only.

On normal quit, `run_mystic()` writes only `ESC[0m` and `ESC[?25h`. It does not
call Mystic's `flush()` by default. A GZ script returns to its calling menu by
completing normally and reaching script EOF; it must not invoke `GR` (or
another menu navigation command) to unwind the menu context. The wrapper calls
`main()` for side effects, logs `main_return` and `mpy_end`, and reaches EOF. It
does not return an integer, raise `SystemExit`, call `bbs.shutdown()`, or close
any Mystic-owned connection.

Exit cleanup is controlled by `MysticConfig`. The defaults are
`restore_on_exit=True` and `flush_on_exit=False`. The restore output is exactly
`ESC[0mESC[?25h`; no screen clear, cursor movement, menu command, or Telnet
control is sent during cleanup. For diagnostics, set
`ANSIRADAR_MYSTIC_RESTORE_ON_EXIT=0` to make cleanup produce no final output.
`ANSIRADAR_MYSTIC_FLUSH_ON_EXIT` defaults to `0` and should remain disabled for
the normal GZ return path.

## Real Mystic A/B Test

Run the same GZ menu entry on the actual Mystic 1.12 A48 system and press Q.
Keep the normal configuration for Test A:

```console
ANSIRADAR_MYSTIC_FLUSH_ON_EXIT=0 ANSIRADAR_MYSTIC_RESTORE_ON_EXIT=1
```

If the Telnet session still disconnects, repeat as Test B:

```console
ANSIRADAR_MYSTIC_FLUSH_ON_EXIT=0 ANSIRADAR_MYSTIC_RESTORE_ON_EXIT=0
```

The variables must be present in the environment inherited by the GZ process,
or the equivalent values can be supplied through the Mystic launch setup.
Inspect `mystic.log` after each run. Test A distinguishes the old `flush()`
behavior from final ANSI output; Test B determines whether the remaining issue
is caused by the final ANSI restore itself. Repository fakes cannot validate
the embedded loader or Mystic's real terminal lifecycle, so do not call the
disconnect fixed until one of these tests succeeds on Mystic 1.12 A48.

## Troubleshooting

- If `mystic_bbs` cannot be imported, verify Mystic's Python 3 library and the
  explicit source path in the `.mpy`.
- If the source fails, verify permissions and the absolute `aircraft.json`
  path; the full error is in `mystic.log`.
- If the screen shows mojibake such as `Γöé`, verify that the updated `.mpy`
  and package are installed. Mystic output intentionally uses ASCII only;
  Unicode box-drawing and assumed CP437 conversion are not used.
- If the screen grows or wraps, verify the updated frontend is in use. Every
  frame clears the screen and writes only explicit cursor positions in rows
  1-24 and columns 1-79.
- If third-party imports fail, install the wheel/dependencies into the Python
  interpreter whose `libpython3.x` Mystic loads, matching its architecture.
- Verify this integration in a real Mystic 1.12 A48 session. Repository tests
  use a fake Mystic API and cannot validate Mystic's embedded loader or terminal.

The existing DOOR32 integration remains documented in `docs/mystic-door.md`.
