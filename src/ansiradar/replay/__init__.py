"""Deterministic JSON-lines replay format for recorded snapshots.

Canonical schema
----------------

Each line is a single JSON object with one normalized snapshot::

    {"timestamp": 1720000000.0, "seq": 1, "source": "url", "messages": 123,
     "aircraft": [{
        "icao": "478ABC", "callsign": "SAS431", "latitude": 58.5,
        "longitude": 6.3, "altitude_baro_ft": 37000, "altitude_geom_ft": 37200,
        "on_ground": false, "ground_speed_kt": 451.2, "track_deg": 213,
        "vertical_rate_fpm": -64, "squawk": "1234", "category": "A3",
        "emergency": "none", "seen_seconds": 0.2, "seen_pos_seconds": 1.2,
        "message_count": 100, "rssi_dbfs": -18.5
     }]}

* ``timestamp`` (float, required): seconds used to reproduce appearance,
  movement, staleness, and disappearance deterministically.
* ``seq`` (int, optional): a monotonic sequence number for diagnostics.
* ``source`` (str, optional): data-source identity.
* ``messages`` (int, optional): decoder message counter.
* ``aircraft`` (array, required): canonical *normalized* observation records.

Only normalized fields are recorded; raw HTTP headers and credentials are never
written.
"""

import json
import os
from dataclasses import dataclass

from ansiradar.errors import InvalidSourceData, ReplayExhausted
from ansiradar.obs import (
    AircraftObservation,
    ObservationSnapshot,
    build_observation,
    parse_integer,
    parse_number,
)

MAX_LINE_BYTES = 64 * 1024
MAX_RECORDS_PER_LINE = 2000


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    timestamp: float
    seq: int | None
    source: str
    messages: int | None
    observations: tuple[AircraftObservation, ...]
    skipped: int


def parse_replay_line(line: str, *, index: int) -> ReplayRecord | None:
    """Parse one replay line; None for blanks, raises for malformed JSON."""
    if not line.strip():
        return None
    try:
        payload: object = json.loads(line)
    except json.JSONDecodeError as error:
        raise InvalidSourceData(
            f"replay line {index} is not valid JSON: {error.msg}"
        ) from error
    if not isinstance(payload, dict):
        raise InvalidSourceData(f"replay line {index} must be a JSON object")
    timestamp = parse_number(payload.get("timestamp"))
    if timestamp is None:
        raise InvalidSourceData(f"replay line {index} lacks a numeric timestamp")
    records = payload.get("aircraft")
    if not isinstance(records, list):
        raise InvalidSourceData(f"replay line {index} lacks an aircraft array")

    observations: list[AircraftObservation] = []
    skipped = 0
    for record in records[:MAX_RECORDS_PER_LINE]:
        if not isinstance(record, dict):
            skipped += 1
            continue
        observation = build_observation(
            icao=record.get("icao"),
            timestamp=timestamp,
            source=str(payload.get("source") or "replay"),
            callsign=record.get("callsign"),
            latitude=record.get("latitude"),
            longitude=record.get("longitude"),
            altitude_baro_ft=record.get("altitude_baro_ft"),
            altitude_geom_ft=record.get("altitude_geom_ft"),
            on_ground=bool(record.get("on_ground", False)),
            ground_speed_kt=record.get("ground_speed_kt"),
            track_deg=record.get("track_deg"),
            vertical_rate_fpm=record.get("vertical_rate_fpm"),
            squawk=record.get("squawk"),
            category=record.get("category"),
            emergency=record.get("emergency"),
            seen_seconds=record.get("seen_seconds"),
            seen_pos_seconds=record.get("seen_pos_seconds"),
            message_count=record.get("message_count"),
            rssi_dbfs=record.get("rssi_dbfs"),
        )
        if observation is None:
            skipped += 1
            continue
        observations.append(observation)

    return ReplayRecord(
        timestamp=timestamp,
        seq=parse_integer(payload.get("seq")),
        source=str(payload.get("source") or "replay"),
        messages=parse_integer(payload.get("messages")),
        observations=tuple(observations),
        skipped=skipped,
    )


def _observation_json(obs: AircraftObservation) -> dict[str, object]:
    return {
        "icao": obs.icao,
        "callsign": obs.callsign,
        "latitude": obs.latitude,
        "longitude": obs.longitude,
        "altitude_baro_ft": obs.altitude_baro_ft,
        "altitude_geom_ft": obs.altitude_geom_ft,
        "on_ground": obs.on_ground,
        "ground_speed_kt": obs.ground_speed_kt,
        "track_deg": obs.track_deg,
        "vertical_rate_fpm": obs.vertical_rate_fpm,
        "squawk": obs.squawk,
        "category": obs.category,
        "emergency": obs.emergency,
        "seen_seconds": obs.seen_seconds,
        "seen_pos_seconds": obs.seen_pos_seconds,
        "message_count": obs.message_count,
        "rssi_dbfs": obs.rssi_dbfs,
    }


def snapshot_to_line(
    snapshot: ObservationSnapshot,
    *,
    seq: int | None = None,
    timestamp: float | None = None,
) -> str:
    """Encode a normalized snapshot as one canonical replay line."""
    use_ts = timestamp if timestamp is not None else (snapshot.generated_at or 0.0)
    line: dict[str, object] = {
        "timestamp": use_ts,
        "source": snapshot.source,
        "aircraft": [_observation_json(obs) for obs in snapshot.observations],
    }
    if snapshot.messages is not None:
        line["messages"] = snapshot.messages
    if seq is not None:
        line["seq"] = seq
    return json.dumps(line, sort_keys=True, separators=(",", ":"))


class ReplaySource:
    """Deterministic, clock-stepped provider over a JSON-lines replay file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._records: list[ReplayRecord] = []
        self._load()
        self._position = 0

    def _load(self) -> None:
        if not os.path.exists(self.path):
            raise InvalidSourceData(f"replay file not found: {self.path}")
        try:
            with open(self.path, encoding="utf-8") as handle:
                for number, raw in enumerate(handle, start=1):
                    if len(raw.encode("utf-8")) > MAX_LINE_BYTES:
                        raise InvalidSourceData(
                            f"replay line {number} exceeds {MAX_LINE_BYTES} bytes"
                        )
                    record = parse_replay_line(raw, index=number)
                    if record is not None:
                        self._records.append(record)
        except OSError as error:
            raise InvalidSourceData(
                f"cannot read replay {self.path}: {error}"
            ) from error

    def peek_time(self) -> float | None:
        if self._position >= len(self._records):
            return None
        return self._records[self._position].timestamp

    def is_due(self, now: float) -> bool:
        next_time = self.peek_time()
        return next_time is not None and next_time <= now

    def poll(self) -> ObservationSnapshot:
        if self._position >= len(self._records):
            raise ReplayExhausted(f"replay exhausted: {self.path}")
        record = self._records[self._position]
        self._position += 1
        return ObservationSnapshot(
            generated_at=record.timestamp,
            source=record.source,
            observations=record.observations,
            messages=record.messages,
            skipped=record.skipped,
        )

    def records(self) -> tuple[ReplayRecord, ...]:
        return tuple(self._records)

    def record_count(self) -> int:
        return len(self._records)

    def observation_count(self) -> int:
        return sum(len(record.observations) for record in self._records)

    def last_timestamp(self) -> float | None:
        return self._records[-1].timestamp if self._records else None


class ReplayRecorder:
    """Append-only, crash-safe JSON-lines recorder.

    Lines are buffered and flushed after each record. Concurrent or repeated
    invocations are not expected; to append to an existing completed recording,
    pass ``append=True`` and the schema is validated before the first write.
    """

    def __init__(self, path: str, *, append: bool = False) -> None:
        self.path = path
        if append:
            if not os.path.exists(path) or not self._validate_existing():
                raise InvalidSourceData(
                    f"refusing to append to non-replay file: {path}"
                )
        elif os.path.exists(path) and os.path.getsize(path) > 0:
            raise InvalidSourceData(
                f"recording already exists; use append mode explicitly: {path}"
            )
        try:
            self._handle = open(path, "a", encoding="utf-8")
        except OSError as error:
            raise InvalidSourceData(f"cannot open recording {path}: {error}") from error

    def _validate_existing(self) -> bool:
        try:
            with open(self.path, encoding="utf-8") as handle:
                for number, raw in enumerate(handle, start=1):
                    if parse_replay_line(raw, index=number) is None:
                        continue
            return True
        except (OSError, InvalidSourceData):
            return False

    def write(self, line: str) -> None:
        self._handle.write(line + "\n")
        self._handle.flush()

    def close(self) -> None:
        try:
            self._handle.close()
        except OSError:
            pass

    def __enter__(self) -> "ReplayRecorder":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
