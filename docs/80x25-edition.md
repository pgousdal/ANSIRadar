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
The virtual screen is rendered once and then updated with cursor-addressed cell
diffs. No ncurses dependency is used. `--once` emits one deterministic frame
for captures and offline tests. Interactive controls are arrows, `+`, `-`,
Tab, Space, Enter, L, H, Esc, and Q.

The C edition reads local stdin/stdout for BBS wrappers. It does not implement a
new Telnet server; Mystic DOOR32 descriptor transport remains provided by the
existing Python door runtime.

## Layout and extension

The source tree is organized as `csrc/models`, `csrc/providers`,
`csrc/renderer`, `csrc/ui`, and `csrc/core`, with public headers under
`include/ansiradar80`. Providers return `AircraftList` values and never know
about screen cells. Additional providers can implement the `Provider` function
table without changing radar math or rendering.
