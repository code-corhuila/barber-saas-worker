"""The HTTP adapters against a local server that plays the producer and the consumer."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import urlopen

import pytest

from apps.worker.__main__ import build_jobs
from worker.adapter.inbound.health import start_health
from worker.adapter.outbound.http.client import CORRELATION_ID, HttpClient
from worker.adapter.outbound.http.services import HttpConsumer, HttpDailyCall, HttpProducer
from worker.application.port.outbound.services import CallFailed
from worker.domain.model.event import Event

SEEN: list[tuple[str, str, dict | None, dict]] = []
ANSWERS: dict[tuple[str, str], tuple[int, dict | None]] = {}


class _Service(BaseHTTPRequestHandler):
    def _answer(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length)) if length else None
        SEEN.append((self.command, self.path, body, dict(self.headers)))
        status, answer = ANSWERS.get((self.command, self.path.split("?")[0]), (404, {"error": "NOT_FOUND"}))
        raw = b"" if answer is None else json.dumps(answer).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    do_GET = do_POST = _answer

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Service)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield HttpClient(f"http://127.0.0.1:{httpd.server_port}", "worker-token")
    httpd.shutdown()


@pytest.fixture(autouse=True)
def clean():
    SEEN.clear()
    ANSWERS.clear()


def test_the_producer_reads_envelopes_and_confirms_with_the_token_and_correlation_id(server):
    envelope = {"id": "e1", "type": "AppointmentCompleted", "version": 1, "payload": {"clientId": "c1"}}
    ANSWERS[("GET", "/internal/v1/outbox-events")] = (200, {"data": [envelope]})
    ANSWERS[("POST", "/internal/v1/outbox-events/e1/published")] = (204, None)
    producer = HttpProducer("appointment", server)
    token = CORRELATION_ID.set("run-123")
    try:
        events = producer.pending(50)
        producer.published("e1")
    finally:
        CORRELATION_ID.reset(token)
    assert events == [Event("e1", "AppointmentCompleted", envelope)]
    assert SEEN[0][1] == "/internal/v1/outbox-events?limit=50"
    assert SEEN[0][3]["Authorization"] == "Bearer worker-token"
    assert SEEN[1][3]["X-Correlation-Id"] == "run-123"


def test_the_consumer_sends_the_envelope_as_it_is_and_reports_the_status(server):
    envelope = {"id": "e2", "type": "AppointmentConfirmed", "version": 1, "payload": {}}
    ANSWERS[("POST", "/internal/v1/events")] = (200, {"eventId": "e2", "outcome": "DUPLICATE"})
    HttpConsumer("notifications", server).deliver(Event.from_envelope(envelope))
    assert SEEN[0][2] == envelope
    ANSWERS[("POST", "/internal/v1/events")] = (422, {"error": "BUSINESS_RULE_VIOLATION"})
    with pytest.raises(CallFailed) as failure:
        HttpConsumer("notifications", server).deliver(Event.from_envelope(envelope))
    assert failure.value.status == 422 and failure.value.reason == "BUSINESS_RULE_VIOLATION"


def test_a_failure_is_reported_with_its_reason(server):
    ANSWERS[("POST", "/internal/v1/outbox-events/e3/failed")] = (204, None)
    HttpProducer("appointment", server).failed("e3", "notifications 422 BUSINESS_RULE_VIOLATION")
    assert SEEN[0][2] == {"reason": "notifications 422 BUSINESS_RULE_VIOLATION"}


def test_a_daily_call_reads_processed_or_suspended(server):
    ANSWERS[("POST", "/internal/v1/trials/expire")] = (200, {"suspended": 2, "remaining": True})
    assert HttpDailyCall("trials-expire", server, "/internal/v1/trials/expire").call(50) == (2, True)


def test_no_answer_is_status_0():
    with pytest.raises(CallFailed) as failure:
        HttpClient("http://127.0.0.1:9", "t", timeout=1).request("GET", "/x")
    assert failure.value.status == 0


def test_health_answers_ok_and_nothing_else():
    httpd = start_health(0)
    port = httpd.server_address[1]
    with urlopen(f"http://127.0.0.1:{port}/health") as r:
        assert json.loads(r.read()) == {"status": "ok"}
    with pytest.raises(Exception):
        urlopen(f"http://127.0.0.1:{port}/other")
    httpd.shutdown()


def test_the_environment_enables_only_configured_services():
    jobs = build_jobs({"SERVICE_TOKEN": "t", "APPOINTMENT_API_URL": "http://appointment-api:8080"})
    assert [j.name for j in jobs] == ["relay-appointment", "daily-reminders-due", "daily-no-shows"]
    with pytest.raises(SystemExit):
        build_jobs({})
