# ANSIRadar 80x25 Edition

The repository now also contains a standalone C99 radar application optimized
for classic ANSI/CP437 BBS clients. It is intentionally separate from the
Python/Mystic runtime: the C renderer has its own 80x25 screen model, provider
interface, input decoder, and application loop.

## Build

With CMake:

```console
cmake -S . -B build80
cmake --build build80
ctest --test-dir build80 --output-on-failure
```

On a system without CMake, the repository also includes a dependency-free
Makefile:

```console
make
make test
```

The executable is `ansiradar80`.

## Sources

The provider API is source-independent. The initial providers are:

```console
ansiradar80 --source readsb --file /run/readsb/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812
ansiradar80 --source dump1090 --file /run/dump1090-fa/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812
ansiradar80 --source replay --file capture.csv \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --once
```

Replay CSV rows use:

```text
timestamp,icao,callsign,latitude,longitude,altitude_ft,speed_kt,heading_deg,vertical_fpm,seen_seconds
```

The readsb and dump1090 providers consume the common local `aircraft.json`
shape. The parser is bounded and ignores decoder fields not needed by the
renderer.

## Terminal behavior

The primary profile is exactly 80x25, ASCII/CP437-safe, and ANSI-color capable.
Rows 1 is the title/clock line, rows 2-18 are the aspect-correct radar scope,
row 19 is source status, row 20 is the compact table header, rows 21-23 show
the nearest aircraft, and row 25 is the control line. Every screen write is
clipped to zero-based x `0..79`, y `0..24`; ANSI cursor addresses are therefore
never greater than column 80 or row 25, and no newline is emitted after the
last cell.
The virtual screen is rendered once and then updated with cursor-addressed cell
diffs. No ncurses dependency is used. `--once` emits one deterministic frame
for captures and offline tests. Interactive controls are arrows, `+`, `-`,
Tab, Space, Enter, L, H, Esc, and Q.

The radar projection uses a reusable bearing/distance function with a
character-cell aspect correction: the horizontal radius is approximately twice
the vertical radius. Aircraft outside the range or without valid positions are
not plotted. Same-cell collisions use selected aircraft first, then aircraft
with callsigns, nearest distance, freshest `seen` value, and ICAO ordering.

Incremental output is cursor-addressed and never clears the screen after the
initial frame. Approximate output can be measured from the ANSI test buffer;
the initial 80x25 frame is bounded by the implementation's output buffer and a
single-cell refresh consists of one cursor move, optional color state, and one
cell. This is suitable for simulated 2400/9600-baud testing without inserting
baud-rate sleeps into normal operation.

The C edition reads local stdin/stdout for BBS wrappers. It does not implement a
new Telnet server; Mystic DOOR32 descriptor transport remains provided by the
existing Python door runtime.

## Manual Mystic/SyncTERM checklist

1. Build and install the Python door and C renderer from a wheel or Makefile.
2. Configure Mystic to invoke the existing Python `door` command with its
   node-specific `DOOR32.SYS`.
3. Enter through SyncTERM and verify exactly 80x25 without scrolling.
4. Exercise arrows, `+`/`-`, Tab, Space, Enter, H, Esc, L, and Q.
5. Wait through several refresh cycles and temporarily remove the source file.
6. Reconnect, disconnect abruptly, and verify the process exits.
7. Check for leftovers with `pgrep -af 'ansiradar(80| door)'` and confirm no
   ANSIRadar child remains after disconnect.

The C `ansiradar80` program is a local-stdio 80x25 renderer. The Python
implementation remains the Mystic DOOR32 descriptor runtime; M5 does not add a
native C DOOR32 transport.

## Layout and extension

The source tree is organized as `csrc/models`, `csrc/providers`,
`csrc/renderer`, `csrc/ui`, and `csrc/core`, with public headers under
`include/ansiradar80`. Providers return `AircraftList` values and never know
about screen cells. Additional providers can implement the `Provider` function
table without changing radar math or rendering.
