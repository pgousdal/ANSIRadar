# Radar command

`ansiradar radar` renders a north-up polar radar. It fetches immediately and
refreshes at `--refresh` seconds, retaining the last valid frame when a source
read fails. `--once` renders a deterministic 80x24 frame without raw input or
alternate-screen control and is suitable for screenshots and BBS wrappers.

The default range is 100 nautical miles and can be changed from 5 to 500 nm.
Aircraft outside the range are counted by the source but omitted from the plot.
Stale positions are omitted using `--max-age` while preserving the last source
snapshot and displaying an error status.
