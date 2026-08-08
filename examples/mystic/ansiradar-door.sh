#!/bin/sh
set -eu

DOOR32_PATH=${1:?missing DOOR32.SYS path}

exec /home/mystic/doors/ansiradar/venv/bin/ansiradar door \
  --door32 "$DOOR32_PATH" \
  --source url \
  --url http://127.0.0.1:8080/data/aircraft.json \
  --receiver-lat 58.3405 \
  --receiver-lon 6.2812 \
  --charset cp437 \
  --color always
