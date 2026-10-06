"""Outbound ports: the producers' outbox operations, the consumers' event receivers and the daily calls."""

from __future__ import annotations

from typing import Protocol

from worker.domain.model.event import Event


class CallFailed(Exception):
    """A call to another service did not succeed. ``status`` is the HTTP status, 0 without an answer."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


class Producer(Protocol):
    """GET /internal/v1/outbox-events and its confirmations (DEC-APPT-07, DEC-LOY-04, DEC-AUTH-08)."""

    name: str

    def pending(self, limit: int) -> list[Event]: ...

    def published(self, event_id: str) -> None: ...

    def failed(self, event_id: str, reason: str) -> None: ...


class Consumer(Protocol):
    """POST /internal/v1/events of loyalty-api and notifications-api; raises CallFailed when not 200."""

    name: str

    def deliver(self, event: Event) -> None: ...


class DailyCall(Protocol):
    """A daily job of another service (reminders-due, no-shows, trials/expire): (processed, remaining)."""

    name: str

    def call(self, limit: int) -> tuple[int, bool]: ...


class Clock(Protocol):
    """Monotonic seconds for deadlines and backoff, so a clock change never breaks a run."""

    def now(self) -> float: ...
