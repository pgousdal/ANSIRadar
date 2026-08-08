# Mystic example

`ansiradar-door.sh` is a working-directory-independent wrapper for Mystic
Linux. Install the wheel at `/home/mystic/doors/ansiradar/venv`, ensure the BBS user can
execute it, and configure the Mystic menu entry to pass the node-specific
`DOOR32.SYS` path as its first argument.

The wrapper intentionally uses a localhost decoder endpoint and contains no
credentials. Adjust the absolute executable and receiver coordinates for the
installation. Do not share one fixed dropfile between simultaneous nodes.

See [`docs/mystic-door.md`](../../docs/mystic-door.md) for the DOOR32 assumptions,
testing procedure, exit codes, and troubleshooting guidance.
