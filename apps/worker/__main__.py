"""Composition root of barber-saas-worker: reads the environment, wires the jobs, runs the scheduler.

    python -m apps.worker          (PYTHONPATH=src:.)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from datetime import time as clock_time

from worker.adapter.inbound.health import start_health
from worker.adapter.inbound.scheduler import Scheduler
from worker.adapter.outbound.http.client import HttpClient
from worker.adapter.outbound.http.services import HttpConsumer, HttpDailyCall, HttpProducer
from worker.application.port.inbound.job import Job
from worker.application.usecase.daily_job import DailyJob
from worker.application.usecase.interval_job import IntervalJob
from worker.application.usecase.relay_outbox import RelayOutbox
from worker.domain.model.routing import FINANCE, LOYALTY, NOTIFICATIONS


class MonotonicClock:
    def now(self) -> float:
        return time.monotonic()


def _at(value: str) -> clock_time:
    hours, minutes = value.split(":")
    return clock_time(int(hours), int(minutes))


def _names(value: str) -> list[str]:
    """A comma-separated list of service names, blanks ignored."""
    return [n.strip() for n in value.split(",") if n.strip()]


def build_jobs(env: dict[str, str]) -> list[Job]:
    """Every job the environment enables. A service without a URL is simply not called."""
    shared = env.get("SERVICE_TOKEN", "").strip()

    def client(var: str) -> HttpClient | None:
        """The service at URL `var`, called with its own token (`LOYALTY_API_URL` -> `LOYALTY_TOKEN`).

        Each token names that service as `aud` and carries only the scopes the worker needs there
        (docs#158, docs#159), so a token leaked from one call cannot be replayed on another service.
        SERVICE_TOKEN is the fallback while an environment still has a single token.
        """
        url = env.get(var, "").strip()
        if not url:
            return None
        token = env.get(var.replace("_API_URL", "_TOKEN"), "").strip() or shared
        if not token:
            raise SystemExit(f"{var.replace('_API_URL', '_TOKEN')} (or SERVICE_TOKEN) is required: "
                             "run barber-saas-infra-postgres/scripts/dev-keys.sh")
        return HttpClient(url, token)

    clock = MonotonicClock()
    offset = timezone(timedelta(hours=float(env.get("UTC_OFFSET_HOURS", "-5"))))  # Colombia: no DST

    def local_now() -> datetime:
        return datetime.now(offset)

    # A service can produce before it consumes (loyalty publishes stickers before it receives
    # AppointmentCompleted): CONSUMERS names the ones that already take POST /internal/v1/events.
    consumer_urls = {LOYALTY: "LOYALTY_API_URL", NOTIFICATIONS: "NOTIFICATIONS_API_URL",
                     FINANCE: "FINANCE_INVENTORY_API_URL"}
    consumers = {}
    for name in _names(env.get("CONSUMERS", f"{LOYALTY},{NOTIFICATIONS},{FINANCE}")):
        c = client(consumer_urls[name])
        if c:
            consumers[name] = HttpConsumer(name, c)

    jobs: list[Job] = []
    producer_urls = {"appointment": "APPOINTMENT_API_URL", "loyalty": "LOYALTY_API_URL",
                     "identity-auth": "IDENTITY_AUTH_API_URL", "platform-admin": "PLATFORM_ADMIN_API_URL"}
    for name in _names(env.get("PRODUCERS", "appointment")):
        c = client(producer_urls[name])
        if c:
            jobs.append(RelayOutbox(HttpProducer(name, c), consumers, clock))

    appointment, platform = client("APPOINTMENT_API_URL"), client("PLATFORM_ADMIN_API_URL")
    if appointment:
        jobs.append(DailyJob(HttpDailyCall("reminders-due", appointment,
                                           "/internal/v1/appointments/reminders-due?window=DAY_BEFORE"),
                             _at(env.get("REMINDERS_AT", "18:00")), clock, local_now))
        # The one-hour reminder (DEC-APPT-12). Off until appointment-api takes `window`: an older
        # appointment-api would treat every call as the day-before reminder.
        every = env.get("HOUR_REMINDERS_EVERY_SECONDS", "").strip()
        if every:
            jobs.append(IntervalJob(HttpDailyCall("hour-reminders-due", appointment,
                                                  "/internal/v1/appointments/reminders-due?window=HOUR_BEFORE"),
                                    float(every), clock))
        jobs.append(DailyJob(HttpDailyCall("no-shows", appointment, "/internal/v1/appointments/no-shows"),
                             _at(env.get("NO_SHOWS_AT", "01:00")), clock, local_now))
    if platform:
        jobs.append(DailyJob(HttpDailyCall("trials-expire", platform, "/internal/v1/trials/expire"),
                             _at(env.get("TRIALS_AT", "02:00")), clock, local_now))
        # DEC-PLAT-07: the paid month that ended, then the 7-day and 1-day notices.
        jobs.append(DailyJob(HttpDailyCall("subscriptions-expire", platform, "/internal/v1/subscriptions/expire"),
                             _at(env.get("SUBSCRIPTIONS_AT", "02:05")), clock, local_now))
        jobs.append(DailyJob(HttpDailyCall("subscription-notices", platform, "/internal/v1/subscriptions/notices"),
                             _at(env.get("NOTICES_AT", "09:00")), clock, local_now))
    return jobs


def main() -> None:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
    jobs = build_jobs(dict(os.environ))
    health = start_health(int(os.environ.get("HEALTH_PORT", "8080")))
    scheduler = Scheduler(jobs)
    # Graceful shutdown: the current job finishes its event, then the loop stops.
    signal.signal(signal.SIGTERM, lambda *_: scheduler.stop())
    signal.signal(signal.SIGINT, lambda *_: scheduler.stop())
    logging.getLogger("worker").info('{"started": %s}' % [j.name for j in jobs])
    scheduler.run_forever()
    health.shutdown()


if __name__ == "__main__":
    main()
