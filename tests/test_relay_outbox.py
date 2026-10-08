from __future__ import annotations

from worker.application.port.outbound.services import CallFailed
from worker.application.usecase.relay_outbox import BATCH_LIMIT, RelayOutbox
from worker.domain.model.event import Event
from worker.domain.model.retry import MAX_ATTEMPTS, Backoff, is_retryable


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t


class FakeProducer:
    name = "appointment"

    def __init__(self, *events: Event) -> None:
        self.rows = list(events)
        self.published_ids: list[str] = []
        self.failed_ids: dict[str, str] = {}
        self.down = False

    def pending(self, limit: int) -> list[Event]:
        if self.down:
            raise CallFailed(0, "connection refused")
        done = set(self.published_ids) | set(self.failed_ids)
        return [e for e in self.rows if e.id not in done][:limit]

    def published(self, event_id: str) -> None:
        self.published_ids.append(event_id)

    def failed(self, event_id: str, reason: str) -> None:
        self.failed_ids[event_id] = reason


class FakeConsumer:
    def __init__(self, name: str, answers: list[int] | None = None) -> None:
        self.name = name
        self.answers = answers or []
        self.received: list[str] = []

    def deliver(self, event: Event) -> None:
        self.received.append(event.id)
        status = self.answers.pop(0) if self.answers else 200
        if status != 200:
            raise CallFailed(status, "UNKNOWN_EVENT_TYPE" if status == 422 else "unavailable")


def event(n: int, event_type: str = "AppointmentCompleted") -> Event:
    return Event.from_envelope({"id": f"e{n}", "type": event_type, "version": 1, "payload": {}})


def relay(producer: FakeProducer, clock: FakeClock, **consumers: FakeConsumer) -> RelayOutbox:
    return RelayOutbox(producer, consumers, clock, Backoff(base_seconds=5, cap_seconds=300), rand=lambda: 0.0)


def test_an_event_goes_to_every_consumer_and_is_confirmed_once():
    clock, producer = FakeClock(), FakeProducer(event(1))
    loyalty, notifications = FakeConsumer("loyalty"), FakeConsumer("notifications")
    report = relay(producer, clock, loyalty=loyalty, notifications=notifications).run(clock.t + 30)
    assert loyalty.received == ["e1"] and notifications.received == ["e1"]
    assert producer.published_ids == ["e1"] and report.done == 1


def test_an_event_nobody_consumes_is_confirmed_without_delivery():
    clock, producer = FakeClock(), FakeProducer(event(1, "AppointmentMarkedNoShow"))
    relay(producer, clock).run(clock.t + 30)
    assert producer.published_ids == ["e1"]


def test_a_4xx_fails_at_once_with_the_reason():
    clock, producer = FakeClock(), FakeProducer(event(1, "AppointmentConfirmed"))
    relay(producer, clock, notifications=FakeConsumer("notifications", [422])).run(clock.t + 30)
    assert producer.failed_ids["e1"].startswith("notifications 422")
    assert producer.published_ids == []


def test_a_5xx_is_retried_after_the_backoff_and_fails_after_the_last_attempt():
    clock, producer = FakeClock(), FakeProducer(event(1, "AppointmentConfirmed"))
    job = relay(producer, clock, notifications=FakeConsumer("notifications", [503] * MAX_ATTEMPTS))
    job.run(clock.t + 30)
    assert producer.failed_ids == {} and producer.published_ids == []
    job.run(clock.t + 30)                          # before the backoff: not even tried
    for _ in range(MAX_ATTEMPTS - 1):
        clock.t += 1000
        job.run(clock.t + 30)
    assert "after 8 attempts" in producer.failed_ids["e1"]


def test_a_retried_event_is_confirmed_once_the_consumer_recovers():
    clock, producer = FakeClock(), FakeProducer(event(1))
    loyalty, notifications = FakeConsumer("loyalty"), FakeConsumer("notifications", [500])
    job = relay(producer, clock, loyalty=loyalty, notifications=notifications)
    job.run(clock.t + 30)
    clock.t += 1000
    job.run(clock.t + 30)
    assert producer.published_ids == ["e1"]
    assert loyalty.received == ["e1", "e1"]        # delivered again: loyalty answers DUPLICATE


def test_an_event_waits_while_its_consumer_is_not_configured():
    clock, producer = FakeClock(), FakeProducer(event(1))
    report = relay(producer, clock, notifications=FakeConsumer("notifications")).run(clock.t + 30)
    assert producer.published_ids == [] and producer.failed_ids == {} and report.waiting == 1


def test_a_type_without_a_route_fails():
    clock, producer = FakeClock(), FakeProducer(event(1, "SomethingNew"))
    relay(producer, clock).run(clock.t + 30)
    assert "no route" in producer.failed_ids["e1"]


def test_a_run_is_bounded_by_the_batch_and_the_deadline():
    clock = FakeClock()
    producer = FakeProducer(*[event(n, "AppointmentMarkedNoShow") for n in range(BATCH_LIMIT + 10)])
    relay(producer, clock).run(clock.t + 30)
    assert len(producer.published_ids) == BATCH_LIMIT
    late = FakeProducer(event(1, "AppointmentMarkedNoShow"))
    report = relay(late, clock).run(clock.t)       # deadline already reached
    assert late.published_ids == [] and "deadline" in report.notes[0]


def test_a_producer_that_does_not_answer_is_asked_again_a_minute_later():
    clock, producer = FakeClock(), FakeProducer(event(1, "AppointmentMarkedNoShow"))
    producer.down = True
    job = relay(producer, clock)
    assert "pending: 0" in job.run(clock.t + 30).notes[0]
    producer.down = False
    assert job.run(clock.t + 30).notes == [] and producer.published_ids == []
    clock.t += 61
    job.run(clock.t + 30)
    assert producer.published_ids == ["e1"]


def test_retry_policy_of_the_norm():
    assert is_retryable(0) and is_retryable(429) and is_retryable(503)
    assert not is_retryable(400) and not is_retryable(404) and not is_retryable(422)
    backoff = Backoff(base_seconds=5, cap_seconds=300)
    assert backoff.delay(1, 0.0) == 5 and backoff.delay(3, 0.0) == 20
    assert backoff.delay(20, 0.0) == 300 and backoff.delay(1, 1.0) == 7.5


def test_appointment_created_goes_to_loyalty_for_the_coupon_applied_at_booking():
    clock, producer = FakeClock(), FakeProducer(event(1, "AppointmentCreated"))
    loyalty, notifications = FakeConsumer("loyalty"), FakeConsumer("notifications")
    relay(producer, clock, loyalty=loyalty, notifications=notifications).run(clock.t + 30)
    assert loyalty.received == ["e1"] and notifications.received == []
    assert producer.published_ids == ["e1"]
