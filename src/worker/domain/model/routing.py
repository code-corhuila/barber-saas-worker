"""Which service consumes each event type: the Event Summary Table of 02-domain/domain-events.md."""

from __future__ import annotations

LOYALTY = "loyalty"
NOTIFICATIONS = "notifications"

# One entry per event type the producers write (ADR-016). An empty tuple means nobody consumes it
# yet: the worker confirms it as published without delivering it.
ROUTES: dict[str, tuple[str, ...]] = {
    # The coupon applied at booking (DEC-LOY-06, barber-saas-docs 07-api/contracts/openapi/loyalty-service.yaml).
    "AppointmentCreated": (LOYALTY,),
    "AppointmentConfirmed": (NOTIFICATIONS,),
    "AppointmentCancelled": (NOTIFICATIONS,),
    "AppointmentReminderDue": (NOTIFICATIONS,),
    "AppointmentMarkedNoShow": (),
    "AppointmentCompleted": (LOYALTY, NOTIFICATIONS),
    "StickerGranted": (NOTIFICATIONS,),
    "RewardRedeemed": (NOTIFICATIONS,),
    "PasswordResetRequested": (NOTIFICATIONS,),
}


def consumers_of(event_type: str) -> tuple[str, ...] | None:
    """The consumers of a type, or None for a type the routing table does not know."""
    return ROUTES.get(event_type)
