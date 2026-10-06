from __future__ import annotations

from datetime import datetime, time

from worker.application.port.outbound.services import CallFailed
from worker.application.usecase.daily_job import DailyJob


class FakeClock:
    def now(self) -> float:
        return 0.0


class FakeCall:
    name = "reminders-due"

    def __init__(self, *answers: tuple[int, bool] | int) -> None:
        self.answers = list(answers)
        self.calls = 0

    def call(self, limit: int) -> tuple[int, bool]:
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, int):
            raise CallFailed(answer, "unavailable")
        return answer


def job(call: FakeCall, now: list[datetime]) -> DailyJob:
    return DailyJob(call, time(18, 0), FakeClock(), lambda: now[0])


def test_it_runs_after_its_time_once_a_day_while_there_is_more():
    now = [datetime(2026, 10, 6, 17, 59)]
    call = FakeCall((50, True), (3, False), (1, False))
    daily = job(call, now)
    assert daily.run(10.0).done == 0 and call.calls == 0
    now[0] = datetime(2026, 10, 6, 18, 0)
    assert daily.run(10.0).done == 53 and call.calls == 2
    assert daily.run(10.0).done == 0               # already done today
    now[0] = datetime(2026, 10, 7, 18, 30)
    assert daily.run(10.0).done == 1


def test_a_failed_call_is_tried_again_in_the_next_run_of_the_day():
    now = [datetime(2026, 10, 6, 18, 5)]
    call = FakeCall(503, (2, False))
    daily = job(call, now)
    assert daily.run(10.0).failed == 1
    assert daily.due()
    assert daily.run(10.0).done == 2 and not daily.due()


def test_the_deadline_stops_it():
    now = [datetime(2026, 10, 6, 18, 5)]
    report = job(FakeCall((50, True)), now).run(-1.0)
    assert report.done == 0 and "deadline" in report.notes[0]
