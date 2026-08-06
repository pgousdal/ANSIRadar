# Radar command

```console
ansiradar radar --source url --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812 --refresh 2
```

`--source` selects `url`, `file`, or `replay`; the matching endpoint option is
`--url`, `--file`, or `--replay-file`. `--refresh` controls rendering and source
polling cadence. URL/file failures use bounded exponential backoff and retain
the most recent valid tracks. The status row reports source health, update age,
observation count, retry state, and parser skips without writing asynchronous
text over the radar.

`--once` renders a deterministic 80x24 frame without raw input or alternate
screen control. File snapshots and replays are suitable for screenshots,
offline tests, and BBS wrappers:

```console
ansiradar radar --source replay --replay-file capture.jsonl \
  --receiver-lat 58.3405 --receiver-lon 6.2812 \
  --once --color never --symbols ascii
```

The default range is 100 nautical miles and can be changed from 5 to 500 nm.
`--pos-stale` (30s), `--track-stale` (60s), `--removal-age` (120s), and
`--max-tracks` configure track aging and bounds. Pause freezes displayed state;
resize and terminal cleanup continue to work during source failures.
