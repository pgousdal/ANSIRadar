# readsb/dump1090 source

ANSIRadar accepts a local path, a local `file://` URL, or an explicit `http://` or
`https://` URL containing the common `aircraft.json` object. The object must have
an `aircraft` array; `now` and the top-level `messages` counter are optional.

HTTP is contacted only when the user explicitly supplies an HTTP(S) source. Each
command performs one read: there is no polling, discovery, or background network
activity. Other URI schemes and remote `file://` authorities are rejected.

ANSIRadar consumes decoded metadata. It does not control the SDR, decode raw RF,
transmit, or modify readsb/dump1090. Secure access to a remotely exposed decoder
and consider receiver-location privacy.
