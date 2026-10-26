"""A job that calls a service every few minutes instead of once a day (DEC-APPT-12: the one-hour reminder)."""

from __future__ import annotations

from worker.application.port.inbound.job import JobReport
from worker.application.port.outbound.services import CallFailed, Clock, DailyCall
from worker.application.usecase.daily_job import CALL_LIMIT


class IntervalJob:
    """Calls ``call`` every ``every_seconds``, again while it answers ``remaining``.

    Same rules as DailyJob: the rule lives in the service, the call is idempotent, and a failure
    waits for the next interval instead of retrying on every tick of the scheduler.
    """

    def __init__(self, call: DailyCall, every_seconds: float, clock: Clock) -> None:
        self.name = f"every-{call.name}"
        self._call = call
        self._every = every_seconds
        self._clock = clock
        self._next_at = 0.0

    def due(self) -> bool:
        return self._clock.now() >= self._next_at

    def run(self, deadline: float) -> JobReport:
        report = JobReport(self.name)
        if not self.due():
            return report
        while self._clock.now() < deadline:
            try:
                processed, remaining = self._call.call(CALL_LIMIT)
            except CallFailed as failure:
                report.failed += 1
                report.notes.append(f"{self._call.name}: {failure.status} {failure.reason}")
                self._next_at = self._clock.now() + self._every
                return report
            report.done += processed
            if not remaining:
                self._next_at = self._clock.now() + self._every
                return report
        report.notes.append("deadline reached; the rest is called in the next run")
        return report
