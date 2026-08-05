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
