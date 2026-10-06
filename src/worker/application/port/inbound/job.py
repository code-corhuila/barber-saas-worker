"""The inbound port of the worker (norm 5.7.a): every job the scheduler runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class JobReport:
    """What one run did, for the log line of the run."""

    job: str
    done: int = 0
    failed: int = 0
    waiting: int = 0
    notes: list[str] = field(default_factory=list)


class Job(Protocol):
    """One unit of work with a name; ``run`` must respect the deadline it receives (bounded runs)."""

    name: str

    def run(self, deadline: float) -> JobReport: ...
