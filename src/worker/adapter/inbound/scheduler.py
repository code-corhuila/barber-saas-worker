"""The scheduler, the worker's inbound adapter: every few seconds, each job in a bounded run of its own."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid

from worker.adapter.outbound.http.client import CORRELATION_ID
from worker.application.port.inbound.job import Job

log = logging.getLogger("worker")

INTERVAL_SECONDS = 5.0
RUN_SECONDS = 30.0


class Scheduler:
    """Runs every job each INTERVAL_SECONDS, each with its own X-Correlation-Id and a RUN_SECONDS budget."""

    def __init__(self, jobs: list[Job], interval: float = INTERVAL_SECONDS, run_seconds: float = RUN_SECONDS) -> None:
        self._jobs = jobs
        self._interval = interval
        self._run_seconds = run_seconds
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> None:
        for job in self._jobs:
            if self._stop.is_set():
                return
            correlation_id = uuid.uuid4().hex
            token = CORRELATION_ID.set(correlation_id)
            try:
                report = job.run(time.monotonic() + self._run_seconds)
                if report.done or report.failed or report.notes:
                    log.info(json.dumps({"job": report.job, "correlationId": correlation_id, "done": report.done,
                                         "failed": report.failed, "waiting": report.waiting, "notes": report.notes}))
            except Exception:                         # one broken job never stops the others
                log.exception(json.dumps({"job": job.name, "correlationId": correlation_id}))
            finally:
                CORRELATION_ID.reset(token)

    def run_forever(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            self.tick()
            self._stop.wait(max(0.0, self._interval - (time.monotonic() - started)))
