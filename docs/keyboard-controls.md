# Keyboard controls

`q` quits; Up/`k` and Down/`j` move selection; `Esc` closes help. `+`/`=` halves
the visible range and `-` doubles it; `1`/`2`/`3`/`4` select 25/50/100/200 nm.
`g` toggles ground aircraft, `s` cycles distance/callsign/altitude sorting, `l`
cycles callsign/ICAO/no labels, `p` pauses, `r` refreshes immediately, and `?`/`h`
toggle help. Enter has no action.

Door mode decodes these keys from transport bytes rather than termios. ANSI
arrow sequences may be fragmented across reads; bounded Telnet IAC negotiation
bytes are ignored defensively and are never rendered as keys.

The standalone C 80x25 edition uses the same BBS-oriented set where applicable:
arrows select, `+`/`-` zoom, Tab cycles sort, Space keeps the receiver-centered
view, Enter opens details, `L` toggles list mode, `H` opens help, `Esc` closes an
overlay, and `Q` quits.
