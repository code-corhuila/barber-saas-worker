"""The retry policy of norm 5.7.2 and ADR-016: bounded, exponential, with jitter, only for retryable errors."""

from __future__ import annotations

from dataclasses import dataclass

MAX_ATTEMPTS = 8


def is_retryable(status: int) -> bool:
    """Network errors (status 0), 429 and 5xx can be fixed by trying again; any other 4xx cannot."""
    return status == 0 or status == 429 or status >= 500


@dataclass(frozen=True)
class Backoff:
    """Seconds to wait before attempt n+1: base * 2^(n-1), capped, plus up to 50 % random jitter.

    Without jitter, many events that failed together are retried together and prolong the outage.
    """

    base_seconds: float = 5.0
    cap_seconds: float = 300.0

    def delay(self, attempts: int, random_fraction: float) -> float:
        if attempts < 1:
            return 0.0
        raw = min(self.cap_seconds, self.base_seconds * (2 ** (attempts - 1)))
        return raw * (1.0 + 0.5 * max(0.0, min(1.0, random_fraction)))
