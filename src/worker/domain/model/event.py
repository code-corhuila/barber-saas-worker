"""A domain event as a producer's outbox hands it over (EventEnvelope, _shared.yaml 1.2.0)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    """One pending outbox row. ``envelope`` is delivered to every consumer exactly as received."""

    id: str
    type: str
    envelope: dict[str, Any] = field(compare=False)

    @staticmethod
    def from_envelope(envelope: dict[str, Any]) -> "Event":
        event_id = envelope.get("id")
        event_type = envelope.get("type")
        if not isinstance(event_id, str) or not isinstance(event_type, str):
            raise ValueError("an envelope needs a string id and type")
        return Event(event_id, event_type, envelope)
