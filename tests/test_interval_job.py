from __future__ import annotations

from tests.test_daily_job import FakeCall, FakeClock
from worker.application.usecase.interval_job import IntervalJob


def test_it_runs_at_once_then_every_interval_while_there_is_more():
    clock = FakeClock()
    call = FakeCall((50, True), (2, False), (1, False))
    job = IntervalJob(call, 300.0, clock)
    assert job.run(10.0).done == 52 and call.calls == 2
    clock.t = 299.0
    assert job.run(400.0).done == 0                # not yet
    clock.t = 300.0
    assert job.run(400.0).done == 1 and call.calls == 3


def test_a_failed_call_waits_for_the_next_interval():
    clock = FakeClock()
    call = FakeCall(503, (4, False))
    job = IntervalJob(call, 300.0, clock)
    assert job.run(10.0).failed == 1
    assert not job.due()
    clock.t = 300.0
    assert job.run(400.0).done == 4


def test_the_deadline_stops_it():
    report = IntervalJob(FakeCall((50, True)), 300.0, FakeClock()).run(-1.0)
    assert report.done == 0 and report.notes
