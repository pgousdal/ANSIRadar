# Terminal compatibility

ASCII is the default and safest mode for BBS capture and narrow terminals. The
renderer targets 80x24 and degrades on larger terminals; 60x20 is the hard
minimum and displays a clipped warning below it. Unicode uses box drawing and
radar glyphs where the terminal encoding supports them. CP437 uses compatible
box and symbol glyphs; select it only when the terminal is configured for CP437.

Interactive mode uses the alternate screen by default, restores cursor and input
mode on normal exit, exceptions, SIGINT, and SIGTERM, and can be run with
`--no-alt-screen`. Color is controlled by `--color auto|always|never` and is
never required to understand the display.

## Mystic door mode

`ansiradar door` is a separate BBS profile for Mystic on Linux through
`DOOR32.SYS` descriptor/socket mode. It does not probe local terminal size or
use the alternate screen. The default is 80x24, CP437-compatible output, ANSI
color, CRLF line handling, and cursor reset on exit. Use `--width`, `--height`,
`--charset ascii|cp437|unicode`, and `--color always|never` for explicit safe
overrides. Unicode is opt-in and should only be used when the caller's client
supports it.
