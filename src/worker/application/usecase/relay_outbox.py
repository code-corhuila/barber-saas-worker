"""The outbox relay of ADR-016: read a producer's pending events, deliver them, confirm them."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

from worker.application.port.inbound.job import JobReport
from worker.application.port.outbound.services import CallFailed, Clock, Consumer, Producer
from worker.domain.model.event import Event
from worker.domain.model.retry import MAX_ATTEMPTS, Backoff, is_retryable
from worker.domain.model.routing import consumers_of

BATCH_LIMIT = 50


@dataclass
class _Attempts:
    count: int = 0
    next_at: float = 0.0


class DeliverEvent:
    """The job of one event type (norm 5.7.a): hands an event to each of its consumers.

    Returns None when every consumer answered 200 (PROCESSED, DUPLICATE or IGNORED), or the CallFailed
    of the first one that did not. A consumer that already took the event gets it again on the next
    attempt: the envelope id keeps that a no-op (``sourceEventId``, ``processed_event``).
    """

    def __init__(self, event_type: str, consumers: list[Consumer]) -> None:
        self.event_type = event_type
        self.consumers = consumers

    def deliver(self, event: Event) -> CallFailed | None:
        for consumer in self.consumers:
            try:
                consumer.deliver(event)
            except CallFailed as failure:
                return CallFailed(failure.status, f"{consumer.name} {failure.status} {failure.reason}"[:500])
        return None


class RelayOutbox:
    """The relay job of one producer. Bounded: at most BATCH_LIMIT events and the run's deadline.

    Attempts are counted across runs, with exponential backoff and jitter between them; after
    MAX_ATTEMPTS, or at once for a 4xx that is not 429, the event is confirmed as failed. An event
    routed to a consumer that is not configured waits in the outbox untouched.
    """

    def __init__(self, producer: Producer, consumers: dict[str, Consumer], clock: Clock,
                 backoff: Backoff = Backoff(), rand: Callable[[], float] = random.random) -> None:
        self.name = f"relay-{producer.name}"
        self._producer = producer
        self._consumers = consumers
        self._clock = clock
        self._backoff = backoff
        self._rand = rand
        self._attempts: dict[str, _Attempts] = {}
        self._handlers: dict[str, DeliverEvent] = {}

    def run(self, deadline: float) -> JobReport:
        report = JobReport(self.name)
        try:
            events = self._producer.pending(BATCH_LIMIT)
        except CallFailed as failure:
            report.notes.append(f"{self._producer.name} pending: {failure.status} {failure.reason}")
            return report
        for event in events:
            if self._clock.now() >= deadline:
                report.notes.append("deadline reached; the rest waits for the next run")
                break
            self._handle(event, report)
        return report

    def _handle(self, event: Event, report: JobReport) -> None:
        consumers = consumers_of(event.type)
        if consumers is None:
            self._fail(event, f"no route for event type {event.type}", report)
            return
        handler = self._handler(event.type, consumers)
        if handler is None:
            report.waiting += 1                     # a consumer is not configured yet
            return
        attempts = self._attempts.get(event.id)
        if attempts is not None and attempts.next_at > self._clock.now():
            report.waiting += 1
            return
        failure = handler.deliver(event)
        if failure is None:
            self._confirm(event, report)
        elif not is_retryable(failure.status):
            self._fail(event, failure.reason, report)
        else:
            self._retry_later(event, failure, report)

    def _handler(self, event_type: str, consumers: tuple[str, ...]) -> DeliverEvent | None:
        if any(name not in self._consumers for name in consumers):
            return None
        if event_type not in self._handlers:
            self._handlers[event_type] = DeliverEvent(event_type, [self._consumers[n] for n in consumers])
        return self._handlers[event_type]

    def _confirm(self, event: Event, report: JobReport) -> None:
        try:
            self._producer.published(event.id)
            self._attempts.pop(event.id, None)
            report.done += 1
        except CallFailed as failure:
            report.notes.append(f"{event.id} delivered but not confirmed: {failure.status}")

    def _fail(self, event: Event, reason: str, report: JobReport) -> None:
        try:
            self._producer.failed(event.id, reason[:500])
            self._attempts.pop(event.id, None)
            report.failed += 1
        except CallFailed as failure:
            report.notes.append(f"{event.id} not marked failed: {failure.status}")

    def _retry_later(self, event: Event, failure: CallFailed, report: JobReport) -> None:
        attempts = self._attempts.setdefault(event.id, _Attempts())
        attempts.count += 1
        if attempts.count >= MAX_ATTEMPTS:
            self._fail(event, f"after {MAX_ATTEMPTS} attempts: {failure.reason}", report)
            return
        attempts.next_at = self._clock.now() + self._backoff.delay(attempts.count, self._rand())
        report.waiting += 1
