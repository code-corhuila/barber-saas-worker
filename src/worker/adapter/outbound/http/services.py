"""The producers, consumers and daily calls of ADR-016 over HttpClient."""

from __future__ import annotations

import urllib.parse

from worker.adapter.outbound.http.client import HttpClient, expect
from worker.application.port.outbound.services import CallFailed
from worker.domain.model.event import Event


class HttpProducer:
    """GET /internal/v1/outbox-events and its published/failed confirmations."""

    def __init__(self, name: str, client: HttpClient) -> None:
        self.name = name
        self._client = client

    def pending(self, limit: int) -> list[Event]:
        status, body = self._client.request("GET", f"/internal/v1/outbox-events?limit={limit}")
        data = expect(status, body, 200)
        events = []
        for envelope in (data or {}).get("data", []):
            try:
                events.append(Event.from_envelope(envelope))
            except ValueError as error:
                raise CallFailed(status, f"unreadable envelope: {error}") from error
        return events

    def published(self, event_id: str) -> None:
        status, body = self._client.request("POST", f"/internal/v1/outbox-events/{_id(event_id)}/published")
        expect(status, body, 204, 200)

    def failed(self, event_id: str, reason: str) -> None:
        status, body = self._client.request("POST", f"/internal/v1/outbox-events/{_id(event_id)}/failed",
                                            {"reason": reason[:500] or "undeliverable"})
        expect(status, body, 204, 200)


class HttpConsumer:
    """POST /internal/v1/events: 200 (PROCESSED, DUPLICATE or IGNORED) is a delivery."""

    def __init__(self, name: str, client: HttpClient) -> None:
        self.name = name
        self._client = client

    def deliver(self, event: Event) -> None:
        status, body = self._client.request("POST", "/internal/v1/events", event.envelope)
        expect(status, body, 200)


class HttpDailyCall:
    """A daily operation answering {processed, remaining} or {suspended, remaining}."""

    def __init__(self, name: str, client: HttpClient, path: str) -> None:
        self.name = name
        self._client = client
        self._path = path

    def call(self, limit: int) -> tuple[int, bool]:
        status, body = self._client.request("POST", f"{self._path}?limit={limit}")
        data = expect(status, body, 200) or {}
        processed = data.get("processed", data.get("suspended", 0))
        return int(processed), bool(data.get("remaining", False))


def _id(event_id: str) -> str:
    return urllib.parse.quote(event_id, safe="")
