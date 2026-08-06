# readsb, dump1090, and tar1090 sources

The common local endpoint is usually:

```console
ansiradar radar --source url \
  --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812
```

The same `aircraft.json` structure is used by readsb, dump1090-fa, and
tar1090-compatible local installations. A local file can be polled repeatedly:

```console
ansiradar radar --source file --file /run/readsb/aircraft.json \
  --receiver-lat 58.3405 --receiver-lon 6.2812
```

The document must be an object containing an `aircraft` array. `now` and the
top-level `messages` counter are optional. Unknown fields are ignored by the
normalizer; malformed individual records are skipped and counted. Missing
positions are retained as unpositioned records, never invented.

URL access is explicit only. HTTP and HTTPS are supported, TLS verification is
not disabled, redirects remain restricted to HTTP(S), response size and timeout
limits are enforced, and credentials are redacted from diagnostics. There is no
discovery or background internet activity.

ANSIRadar consumes decoded metadata. It does not control the SDR, decode raw RF,
transmit, or modify a decoder. Do not expose a receiver endpoint directly to the
public internet. Receiver coordinates and aircraft data may have privacy or
operational implications.
