"""HTTP with the standard library (ADR-012): explicit timeouts, the worker's token, the run's correlation id."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from contextvars import ContextVar
from typing import Any

from worker.application.port.outbound.services import CallFailed

# The X-Correlation-Id of the current run (norm 5.7.3): set by the scheduler, sent on every call.
CORRELATION_ID: ContextVar[str] = ContextVar("correlation_id", default="")

TIMEOUT_SECONDS = 5.0


class HttpClient:
    """One service: its base URL and the worker's service token (sub: barber-saas-worker)."""

    def __init__(self, base_url: str, service_token: str, timeout: float = TIMEOUT_SECONDS) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = service_token
        self._timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        """(status, parsed JSON or None). Raises CallFailed with status 0 when there is no answer."""
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        request.add_header("Authorization", f"Bearer {self._token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        correlation_id = CORRELATION_ID.get()
        if correlation_id:
            request.add_header("X-Correlation-Id", correlation_id)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return response.status, _json(response.read())
        except urllib.error.HTTPError as error:
            return error.code, _json(error.read())
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise CallFailed(0, f"{self.base_url} unreachable: {type(error).__name__}") from error


def _json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def expect(status: int, body: Any, *ok: int) -> Any:
    """The body when the status is one of ``ok``; otherwise CallFailed with the envelope's code."""
    if status in ok:
        return body
    code = body.get("error") if isinstance(body, dict) else None
    raise CallFailed(status, code or f"HTTP {status}")
