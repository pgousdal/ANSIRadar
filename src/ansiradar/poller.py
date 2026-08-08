"""Polling controller with bounded retry/backoff and source-health status."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ansiradar.diag import shorten_message
from ansiradar.obs import ObservationSnapshot, now_clock

DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_MAX_BACKOFF = 30.0
MAX_STATUS_ERROR_LENGTH = 96


class _Pollable(Protocol):
    def poll(self) -> ObservationSnapshot: ...


@dataclass(frozen=True, slots=True)
class SourceStatus:
    """Compact, terminal-safe view of source health for the status area."""

    kind: str
    healthy: bool
    last_poll_time: float | None
    last_success_time: float | None
    last_error: str | None
    retry_in: float | None
    observations: int
    messages: int | None
    skipped: int
    exhausted: bool
    next_poll_time: float | None = None


class SourcePoller:
    """Drives a source on an interval, applies backoff, retains last good data."""

    def __init__(
        self,
        source: _Pollable,
        *,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        clock: Callable[[], float] = now_clock,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        logger: logging.Logger | None = None,
        max_status_errors: int = 1,
    ) -> None:
        self.source = source
        self.poll_interval = poll_interval
        self.clock = clock
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.logger = logger or logging.getLogger("ansiradar.poller")
        self.max_status_errors = max(1, max_status_errors)
        self._last_poll: float | None = None
        self._last_success: float | None = None
        self._backoff = 0.0
        self._next_poll: float | None = None
        self._last_snapshot: ObservationSnapshot | None = None
        self._last_error: str | None = None
        self._error_history: list[str] = []
        self._skipped = 0
        self._exhausted = False
        self._kind = getattr(source, "kind", type(source).__name__.lower())
        self._closed = False

    @property
    def kind(self) -> str:
        return self._kind

    def step(self) -> None:
        """Poll now if due, applying replay timing or poll interval plus backoff."""
        now = self.clock()
        if self._next_poll is not None and now < self._next_poll:
            return
        due = self._source_due(now)
        if not due:
            return
        self._last_poll = now
        try:
            snapshot = self.source.poll()
        except Exception as error:  # noqa: BLE001 - classify every source failure
            self._record_failure(now, error)
            return
        self._last_snapshot = snapshot
        self._last_success = now
        self._last_error = None
        self._backoff = 0.0
        self._exhausted = False
        self._skipped = getattr(snapshot, "skipped", 0) or 0
        self._next_poll = now + self.poll_interval

    def force_poll(self) -> None:
        """Schedule the next poll immediately (used by the manual refresh key)."""
        self._next_poll = 0.0

    def seed(self, snapshot: ObservationSnapshot) -> None:
        """Install a validated startup snapshot without counting a retry."""
        now = self.clock()
        self._last_snapshot = snapshot
        self._last_success = now
        self._last_poll = now
        self._last_error = None
        self._backoff = 0.0
        self._exhausted = False
        self._skipped = snapshot.skipped
        self._next_poll = now + self.poll_interval

    def _source_due(self, now: float) -> bool:
        if hasattr(self.source, "is_due"):
            due = self.source.is_due(now)
            return bool(due)
        return True

    def _record_failure(self, now: float, error: Exception) -> None:
        message = shorten_message(str(error) or error.__class__.__name__)
        self._error_history.append(message)
        if len(self._error_history) > self.max_status_errors:
            self._error_history = self._error_history[-self.max_status_errors :]
        self._last_error = message[:MAX_STATUS_ERROR_LENGTH]
        if isinstance(error, Exception):
            self.logger.info("source poll failed: %s", message)
        self._backoff = (
            self.initial_backoff
            if self._backoff <= 0
            else min(self.max_backoff, self._backoff * 2)
        )
        self._next_poll = now + self._backoff
        from ansiradar.errors import ReplayExhausted

        self._exhausted = isinstance(error, ReplayExhausted)

    def status(self) -> SourceStatus:
        now = self.clock()
        retry_in = (
            max(0.0, self._next_poll - now)
            if self._next_poll is not None and self._last_error
            else None
        )
        snapshot = self._last_snapshot
        return SourceStatus(
            kind=self._kind,
            healthy=self._last_error is None,
            last_poll_time=self._last_poll,
            last_success_time=self._last_success,
            last_error=self._last_error,
            retry_in=retry_in,
            observations=len(snapshot.observations) if snapshot else 0,
            messages=snapshot.messages if snapshot else None,
            skipped=self._skipped,
            exhausted=self._exhausted,
            next_poll_time=self._next_poll,
        )

    def last_snapshot(self) -> ObservationSnapshot | None:
        return self._last_snapshot

    def close(self) -> None:
        """Close the source owned by this poller, at most once."""
        if self._closed:
            return
        self._closed = True
        close = getattr(self.source, "close", None)
        if callable(close):
            close()
