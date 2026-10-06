"""The daily jobs of ADR-016: the rule lives in each service; the worker only calls at the right time."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Callable

from worker.application.port.inbound.job import JobReport
from worker.application.port.outbound.services import CallFailed, Clock, DailyCall

CALL_LIMIT = 50


class DailyJob:
    """Calls ``call`` once per local day, after ``at``, again while it answers ``remaining``.

    Bounded by the run's deadline: what is left is called in the next run of the same day. The
    services' operations are idempotent, so a restart that runs the job twice changes nothing.
    """

    def __init__(self, call: DailyCall, at: time, clock: Clock, local_now: Callable[[], datetime]) -> None:
        self.name = f"daily-{call.name}"
        self._call = call
        self._at = at
        self._clock = clock
        self._local_now = local_now
        self._done_on: date | None = None

    def due(self) -> bool:
        now = self._local_now()
        return now.time() >= self._at and self._done_on != now.date()

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
                return report                       # not done: the next run of the day tries again
            report.done += processed
            if not remaining:
                self._done_on = self._local_now().date()
                return report
        report.notes.append("deadline reached; the rest is called in the next run")
        return report
